"""Pipeline de ingesta y recálculo.

1. Sincroniza el catálogo de empresas de la SMV (con clasificación sectorial).
2. Para cada empresa y año descarga los filings Q2 y Q4/anual, mapea cuentas
   y construye los periodos normalizados (S1, S2, anual) vía app.periods.
3. Recalcula y persiste KPIs y alertas (calculated_kpis / financial_alerts).

Los KPIs se recalculan cuando ingresa un estado nuevo, se corrige un periodo
o se ejecuta manualmente `python -m app.cli recalc`.
"""
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.kpis.alerts import evaluate_alerts
from app.kpis.engine import compute_kpis
from app.models import (
    CalculatedKPI,
    Company,
    FinancialAlert,
    FinancialStatement,
    IngestionLog,
    Sector,
    STATEMENT_FIELDS,
)
from app.periods import build_period
from app.smv.account_mapping import normalize_text
from app.smv.scraper import BASE as BASE_SMV, ROMAN, SMVScraper, parse_filing_statements
from app.smv.sectors_seed import classify_company

# Campos clave usados para medir la completitud de datos de un periodo
KEY_FIELDS = [
    "revenue", "operating_income", "net_income", "total_assets", "total_equity",
    "current_assets", "current_liabilities", "total_debt", "cash_and_equivalents",
    "operating_cash_flow", "capex", "financial_expenses", "income_before_tax",
    "income_tax", "depreciation_and_amortization",
]


def get_or_create_sector(db: Session, name: str, is_financial: bool) -> Sector:
    sector = db.scalar(select(Sector).where(Sector.name == name))
    if not sector:
        sector = Sector(name=name, is_financial=is_financial)
        db.add(sector)
        db.flush()
    return sector


def sync_companies(db: Session, scraper: SMVScraper) -> int:
    """Sincroniza el catálogo de empresas desde el combo de la SMV."""
    count = 0
    for item in scraper.list_companies():
        company = db.scalar(select(Company).where(Company.smv_id == item["smv_id"]))
        sector_name, is_fin = classify_company(item["name"])
        sector = get_or_create_sector(db, sector_name, is_fin)
        if not company:
            company = Company(smv_id=item["smv_id"], legal_name=item["name"],
                              normalized_name=normalize_text(item["name"]),
                              sector_id=sector.id)
            db.add(company)
            count += 1
        else:
            company.legal_name = item["name"]
            company.normalized_name = normalize_text(item["name"])
            if company.sector_id is None:
                company.sector_id = sector.id
    db.commit()
    return count


def _statement_fields(stmt: FinancialStatement) -> dict:
    return {f: getattr(stmt, f) for f in STATEMENT_FIELDS}


def _capture_company_meta(company: Company, xb) -> None:
    """Completa RUC, CIIU e industria de la empresa desde el XBRL, sin sobrescribir."""
    if xb.ruc and not company.ruc:
        company.ruc = xb.ruc
    if xb.ciiu and not company.industry:
        company.industry = f"CIIU {xb.ciiu}"


def upsert_statement(db: Session, company: Company, year: int, quarter: int | None,
                     semester: int | None, period_type: str, fields: dict,
                     **meta) -> FinancialStatement:
    q = select(FinancialStatement).where(
        FinancialStatement.company_id == company.id,
        FinancialStatement.year == year,
        FinancialStatement.quarter == quarter,
        FinancialStatement.semester == semester,
        FinancialStatement.period_type == period_type,
        FinancialStatement.is_consolidated == meta.get("is_consolidated", True),
    )
    stmt = db.scalar(q)
    if not stmt:
        stmt = FinancialStatement(company_id=company.id, year=year, quarter=quarter,
                                  semester=semester, period_type=period_type)
        db.add(stmt)
    for k, v in meta.items():
        setattr(stmt, k, v)
    for f in STATEMENT_FIELDS:
        if f in fields:
            setattr(stmt, f, fields[f])
    stmt.updated_at = datetime.utcnow()
    db.flush()
    return stmt


def ingest_company_year(db: Session, scraper: SMVScraper, company: Company,
                        year: int) -> int:
    """Descarga e ingesta los estados de una empresa para un año.

    Usa los filings acumulados de Q2 (semestre 1) y Q4 (año) y deriva S1, S2 y
    anual con la capa de periodos. Devuelve el nº de periodos almacenados.
    """
    from app.smv.account_mapping import derive_fields

    filings = scraper.search_filings(company.smv_id, company.legal_name, year)
    ef = [f for f in filings if normalize_text(f.doc_type).startswith("estados financieros")]

    # Agrupar candidatos por trimestre (puede haber consolidado + individual)
    candidates: dict[int, list] = {}
    for f in ef:
        qn = ROMAN.get(f.quarter.strip().upper())
        if qn is not None:
            candidates.setdefault(qn, []).append(f)

    by_quarter: dict[int, dict] = {}
    prev_balance_by_quarter: dict[int, dict] = {}
    meta_by_quarter: dict[int, dict] = {}

    for qn, group in candidates.items():
        chosen = None  # (fields, prev_balance, meta, is_consolidated)
        for f in group:
            fields, prev_balance = {}, {}
            source_url = f.xbrl_url or f.detail_url
            currency, consolidated = "PEN", True
            if f.xbrl_url:
                try:
                    xb, prev_balance = scraper.fetch_xbrl(f.xbrl_url)
                    fields = derive_fields(xb.fields)
                    prev_balance = derive_fields(prev_balance) if prev_balance else {}
                    currency = xb.currency or "PEN"
                    consolidated = xb.is_consolidated if xb.is_consolidated is not None else True
                    _capture_company_meta(company, xb)
                except Exception:  # noqa: BLE001 — si falla el XBRL, se intenta el HTML
                    fields = {}
            if not fields and f.detail_url:
                statements, source_url = scraper.fetch_statements(f.detail_url)
                if statements:
                    fields = derive_fields(parse_filing_statements(statements))
                    currency = statements[0].currency or "PEN"
                    consolidated = statements[0].is_consolidated \
                        if statements[0].is_consolidated is not None else True
            if not fields:
                continue
            cand = (fields, prev_balance, {
                "currency": currency, "is_consolidated": consolidated,
                "source_url": source_url, "filing_number": f.filing_number}, consolidated)
            # Priorizar el estado consolidado; si no, quedarse con el primero válido
            if chosen is None or (consolidated and not chosen[3]):
                chosen = cand
                if consolidated:
                    break
        if chosen:
            by_quarter[qn] = chosen[0]
            prev_balance_by_quarter[qn] = chosen[1]
            meta_by_quarter[qn] = chosen[2]

    stored = 0
    q2, q4 = by_quarter.get(2), by_quarter.get(4)

    # Balance al cierre del año anterior (comparativo del propio XBRL): se
    # guarda como statement anual Y-1 solo si aún no existe uno real, para que
    # los promedios de ROIC/ROA/ROE del S1 dispongan del periodo previo.
    prev_bal = prev_balance_by_quarter.get(2) or prev_balance_by_quarter.get(4)
    if prev_bal:
        existing = db.scalar(select(FinancialStatement).where(
            FinancialStatement.company_id == company.id,
            FinancialStatement.year == year - 1,
            FinancialStatement.period_type == "annual"))
        if not existing:
            m = meta_by_quarter.get(2) or meta_by_quarter.get(4) or {}
            upsert_statement(db, company, year - 1, None, None, "annual", prev_bal,
                             flow_basis="discrete", is_derived=True,
                             period_end=f"{year - 1}-12-31", **m)

    # Guardar los acumulados originales (trazabilidad, sin duplicar en KPIs)
    for qn, fields in by_quarter.items():
        m = meta_by_quarter[qn]
        upsert_statement(db, company, year, qn, None, "quarter_ytd", fields,
                         flow_basis="ytd", is_derived=False, **m)

    # Derivar periodos normalizados
    for target, quarter_src in (("s1", 2), ("s2", 4), ("annual", 4)):
        pd = build_period(year, target, q2_ytd=q2, q4_ytd=q4)
        if pd is None:
            continue
        m = meta_by_quarter.get(quarter_src) or next(iter(meta_by_quarter.values()), {})
        upsert_statement(db, company, year, None, pd.semester, pd.period_type,
                         pd.fields, flow_basis="discrete", is_derived=pd.is_derived,
                         period_start=pd.period_start, period_end=pd.period_end, **m)
        stored += 1
    db.commit()
    return stored


# ---------------------------------------------------------------------------
# Recálculo de KPIs y alertas
# ---------------------------------------------------------------------------
def data_completeness(fields: dict) -> float:
    present = sum(1 for f in KEY_FIELDS if fields.get(f) is not None)
    return present / len(KEY_FIELDS)


def recalc_company(db: Session, company: Company) -> int:
    """Recalcula KPIs y alertas de todos los periodos semestrales y anuales."""
    stmts = db.scalars(select(FinancialStatement).where(
        FinancialStatement.company_id == company.id,
        FinancialStatement.period_type.in_(["semester", "annual"]),
    ).order_by(FinancialStatement.year, FinancialStatement.semester)).all()

    is_financial = bool(company.sector_rel and company.sector_rel.is_financial)
    # índice (year, semester, period_type, consolidated) -> fields
    index = {}
    for s in stmts:
        index[(s.year, s.semester, s.period_type, s.is_consolidated)] = _statement_fields(s)

    def prev_balance_of(s):
        """Balance del periodo inmediatamente anterior (para promedios)."""
        if s.period_type == "annual":
            return index.get((s.year - 1, None, "annual", s.is_consolidated))
        if s.semester == 2:
            return index.get((s.year, 1, "semester", s.is_consolidated))
        return (index.get((s.year - 1, None, "annual", s.is_consolidated))
                or index.get((s.year - 1, 2, "semester", s.is_consolidated)))

    count = 0
    for s in stmts:
        cur = index[(s.year, s.semester, s.period_type, s.is_consolidated)]
        prev_year_same = index.get((s.year - 1, s.semester, s.period_type, s.is_consolidated))
        kpis = compute_kpis(cur, prev_balance_of(s), prev_year_same, s.period_type)

        for kpi_name, res in kpis.items():
            row = db.scalar(select(CalculatedKPI).where(
                CalculatedKPI.company_id == company.id,
                CalculatedKPI.year == s.year,
                CalculatedKPI.semester == s.semester,
                CalculatedKPI.period_type == s.period_type,
                CalculatedKPI.is_consolidated == s.is_consolidated,
                CalculatedKPI.kpi == kpi_name,
            ))
            if not row:
                row = CalculatedKPI(company_id=company.id, year=s.year, semester=s.semester,
                                    period_type=s.period_type, is_consolidated=s.is_consolidated,
                                    kpi=kpi_name)
                db.add(row)
            row.value = res.value
            row.is_available = res.value is not None
            row.is_estimated = res.estimated
            row.unavailable_reason = res.reason
            row.updated_at = datetime.utcnow()
            count += 1

        db.flush()  # materializar las filas recién creadas antes de actualizarlas
        # previous_value: mismo semestre del año anterior (para tendencia)
        if prev_year_same is not None:
            prev_kpis = compute_kpis(prev_year_same,
                                     index.get((s.year - 2, None, "annual", s.is_consolidated))
                                     or index.get((s.year - 1, 1, "semester", s.is_consolidated)),
                                     None, s.period_type)
            for kpi_name, res in prev_kpis.items():
                row = db.scalar(select(CalculatedKPI).where(
                    CalculatedKPI.company_id == company.id,
                    CalculatedKPI.year == s.year,
                    CalculatedKPI.semester == s.semester,
                    CalculatedKPI.period_type == s.period_type,
                    CalculatedKPI.is_consolidated == s.is_consolidated,
                    CalculatedKPI.kpi == kpi_name,
                ))
                if row:
                    row.previous_value = res.value

        # Alertas (solo sobre periodos semestrales para no duplicar)
        if s.period_type == "semester":
            kpi_values = {k: r.value for k, r in kpis.items()}
            prev_kpi_values = {}
            if prev_year_same is not None:
                prev_kpi_values = {k: r.value for k, r in compute_kpis(
                    prev_year_same, None, None, s.period_type).items()}
            db.query(FinancialAlert).filter_by(company_id=company.id, year=s.year,
                                               semester=s.semester).delete()
            for a in evaluate_alerts(cur, kpi_values, prev_year_same, prev_kpi_values,
                                     is_financial):
                db.add(FinancialAlert(company_id=company.id, year=s.year, semester=s.semester,
                                      code=a.code, severity=a.severity, title=a.title,
                                      description=a.description, kpi=a.kpi,
                                      observed_value=a.observed_value, threshold=a.threshold))
    db.commit()
    return count


def run_ingestion(db: Session, smv_ids: list[str] | None, years: list[int],
                  limit: int | None = None) -> IngestionLog:
    """Orquesta una corrida completa de ingesta + recálculo."""
    log = IngestionLog(scope=f"{'todas' if not smv_ids else ','.join(smv_ids)} {years}")
    db.add(log)
    db.commit()

    scraper = SMVScraper()
    errors = []
    try:
        sync_companies(db, scraper)
        q = select(Company)
        if smv_ids:
            q = q.where(Company.smv_id.in_(smv_ids))
        companies = db.scalars(q).all()
        if limit:
            companies = companies[:limit]

        for company in companies:
            for year in years:
                try:
                    log.statements_ingested += ingest_company_year(db, scraper, company, year)
                except Exception as e:  # noqa: BLE001 — un fallo no detiene la corrida
                    errors.append(f"{company.legal_name} {year}: {e}")
            try:
                log.kpis_calculated += recalc_company(db, company)
            except Exception as e:  # noqa: BLE001
                errors.append(f"recalc {company.legal_name}: {e}")
        log.status = "partial" if errors else "ok"
    except Exception as e:  # noqa: BLE001
        log.status = "error"
        errors.append(str(e))
    finally:
        scraper.close()
        log.finished_at = datetime.utcnow()
        log.detail = "\n".join(errors[:50]) or None
        db.commit()
    return log

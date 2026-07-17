"""API REST del MVP de análisis fundamental (SMV Perú).

Plataforma educativa y analítica: no emite recomendaciones de compra o venta.
"""
import os
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, joinedload

from app.database import get_db, init_db
from app.kpis.meta import KPI_META, KPI_SECTIONS
from app.models import (
    CalculatedKPI,
    Company,
    FinancialAlert,
    FinancialStatement,
    Sector,
    STATEMENT_FIELDS,
)
from app.services import analytics
from app.services.analytics import (
    auto_summary,
    build_ranking,
    cash_flow_ranking,
    company_score,
    format_value,
    highlight_kpis,
    kpi_payload,
    load_period_kpis,
    market_summary,
    sector_stats,
)
from app.smv.account_mapping import normalize_text

STATIC_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "static")


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    # Sincroniza el catálogo de empresas de la SMV en segundo plano (no bloquea
    # el arranque). Solo se ejecuta si está activado el modo scrape-en-vivo.
    if os.environ.get("LIVE_SCRAPE", "1") == "1":
        import threading

        from app.database import SessionLocal
        from app.services.live import ensure_catalog

        def _sync():
            db = SessionLocal()
            try:
                ensure_catalog(db)
            finally:
                db.close()

        threading.Thread(target=_sync, daemon=True).start()
    yield


app = FastAPI(title="Análisis Fundamental SMV Perú", version="1.0", lifespan=lifespan)

LIVE_SCRAPE = os.environ.get("LIVE_SCRAPE", "1") == "1"


def _company_or_404(db: Session, company_id: int) -> Company:
    company = db.scalar(select(Company).options(joinedload(Company.sector_rel))
                        .where(Company.id == company_id))
    if not company:
        raise HTTPException(404, "Empresa no encontrada")
    return company


def _company_brief(c: Company) -> dict:
    return {
        "id": c.id, "name": c.legal_name, "commercialName": c.commercial_name,
        "ticker": c.ticker, "ruc": c.ruc,
        "sector": c.sector_rel.name if c.sector_rel else "Sin clasificar",
        "isFinancial": bool(c.sector_rel and c.sector_rel.is_financial),
        "industry": c.industry,
    }


def _latest_period(db: Session) -> tuple[int, int] | None:
    row = db.execute(select(CalculatedKPI.year, CalculatedKPI.semester)
                     .where(CalculatedKPI.period_type == "semester",
                            CalculatedKPI.semester.isnot(None))
                     .order_by(CalculatedKPI.year.desc(), CalculatedKPI.semester.desc())
                     .limit(1)).first()
    return (row.year, row.semester) if row else None


def _resolve_period(db, year, semester):
    if year is None or semester is None:
        latest = _latest_period(db)
        if latest:
            year = year or latest[0]
            semester = semester or latest[1]
    return year, semester


# ---------------------------------------------------------------------------
# Empresas
# ---------------------------------------------------------------------------
@app.get("/api/companies")
def list_companies(
    db: Session = Depends(get_db),
    search: str | None = None,
    sector: str | None = None,
    year: int | None = None,
    semester: int | None = Query(None, ge=1, le=2),
    consolidated: bool | None = None,
    data_complete: bool = False,
    profitable: bool = False,
    positive_fcf: bool = False,
    low_debt: bool = False,
    positive_growth: bool = False,
    kpi: str | None = None,
    kpi_min: float | None = None,
    limit: int = Query(50, le=250),
):
    q = select(Company).options(joinedload(Company.sector_rel))
    if search:
        term = f"%{normalize_text(search)}%"
        q = q.where(or_(Company.normalized_name.like(term),
                        Company.ticker.ilike(f"%{search}%"),
                        Company.ruc.like(f"%{search}%")))
    if sector:
        q = q.join(Sector, Company.sector_id == Sector.id).where(Sector.name == sector)
    companies = db.scalars(q.limit(500)).all()

    needs_kpis = any([data_complete, profitable, positive_fcf, low_debt,
                      positive_growth, kpi, year, semester])
    results = []
    period_kpis = {}
    if needs_kpis:
        year, semester = _resolve_period(db, year, semester)
        if year is not None:
            period_kpis = load_period_kpis(db, year, semester)

    for c in companies:
        item = _company_brief(c)
        if needs_kpis:
            kpis = period_kpis.get(c.id)
            item["hasData"] = kpis is not None
            if kpis:
                def v(name):
                    r = kpis.get(name)
                    return r.value if r else None
                if profitable and not (v("net_income") or 0) > 0:
                    continue
                if positive_fcf and not (v("free_cash_flow") or 0) > 0:
                    continue
                if low_debt:
                    ndte = v("net_debt_to_ebitda")
                    if ndte is None or ndte >= 1.5:
                        continue
                if positive_growth and not (v("revenue_growth_yoy") or 0) > 0:
                    continue
                if data_complete and any(v(k) is None for k in ("revenue", "net_income", "roe")):
                    continue
                if kpi:
                    kv = v(kpi)
                    if kv is None or (kpi_min is not None and kv < kpi_min):
                        continue
                    item["kpiValue"] = {"kpi": kpi, "value": kv,
                                        "displayValue": format_value(kpi, kv)}
            elif any([data_complete, profitable, positive_fcf, low_debt, positive_growth, kpi]):
                continue
        results.append(item)

    # relevancia: prefijo primero, luego alfabético
    if search:
        s = normalize_text(search)
        results.sort(key=lambda r: (0 if normalize_text(r["name"]).startswith(s) else 1, r["name"]))
    else:
        results.sort(key=lambda r: r["name"])
    return {"companies": results[:limit], "total": len(results),
            "period": {"year": year, "semester": semester} if needs_kpis else None}


@app.post("/api/companies/{company_id}/ensure-data")
def ensure_company_data_endpoint(company_id: int, db: Session = Depends(get_db),
                                 force: bool = False):
    """Garantiza que la empresa tenga datos: si no los tiene (o force=True), la
    scrapea de la SMV en vivo y cachea. El frontend llama esto antes de mostrar
    la ficha y muestra una pantalla de carga mientras dura el scrape."""
    c = _company_or_404(db, company_id)
    if not LIVE_SCRAPE:
        from app.services.live import company_has_data
        return {"status": "cached" if company_has_data(db, company_id) else "empty",
                "periods": 0, "company": _company_brief(c)}
    from app.services.live import ensure_company_data
    result = ensure_company_data(db, c, force=force)
    result["company"] = _company_brief(c)
    return result


@app.get("/api/live-years")
def live_years():
    """Años que la app scrapea bajo demanda (para que el frontend los pida uno a uno)."""
    from app.services.live import LIVE_YEARS
    return {"years": sorted(LIVE_YEARS, reverse=True), "liveScrape": LIVE_SCRAPE}


@app.post("/api/companies/{company_id}/ensure-year")
def ensure_company_year_endpoint(company_id: int, year: int,
                                 db: Session = Depends(get_db), force: bool = False):
    """Scrapea UN año de la empresa. Petición corta que no supera el timeout de
    hosting gratuito; el frontend llama esto por cada año, secuencialmente."""
    c = _company_or_404(db, company_id)
    if not LIVE_SCRAPE:
        from app.services.live import year_has_data
        return {"status": "cached" if year_has_data(db, company_id, year) else "empty",
                "periods": 0, "year": year}
    from app.services.live import ensure_company_year
    return ensure_company_year(db, c, year, force=force)


@app.get("/api/companies/{company_id}")
def get_company(company_id: int, db: Session = Depends(get_db)):
    c = _company_or_404(db, company_id)
    periods = db.execute(
        select(FinancialStatement.year, FinancialStatement.semester,
               FinancialStatement.period_type, FinancialStatement.is_consolidated,
               FinancialStatement.currency, FinancialStatement.source_url,
               FinancialStatement.updated_at)
        .where(FinancialStatement.company_id == company_id,
               FinancialStatement.period_type.in_(["semester", "annual"]))
        .order_by(FinancialStatement.year.desc(), FinancialStatement.semester.desc())
    ).all()
    return {
        "company": _company_brief(c),
        "availablePeriods": [
            {"year": p.year, "semester": p.semester, "periodType": p.period_type,
             "isConsolidated": p.is_consolidated, "currency": p.currency,
             "sourceUrl": p.source_url, "updatedAt": p.updated_at.isoformat() if p.updated_at else None}
            for p in periods
        ],
    }


@app.get("/api/companies/{company_id}/kpis")
def get_company_kpis(
    company_id: int,
    db: Session = Depends(get_db),
    year: int | None = None,
    semester: int | None = Query(None, ge=1, le=2),
    period_type: str = Query("semester", pattern="^(semester|annual)$"),
):
    c = _company_or_404(db, company_id)
    if period_type == "annual":
        semester = None
        if year is None:
            row = db.execute(select(CalculatedKPI.year).where(
                CalculatedKPI.company_id == company_id,
                CalculatedKPI.period_type == "annual")
                .order_by(CalculatedKPI.year.desc()).limit(1)).first()
            year = row.year if row else None
    else:
        year, semester = _resolve_period(db, year, semester)
    if year is None:
        raise HTTPException(404, "La empresa no tiene periodos calculados")

    is_fin = bool(c.sector_rel and c.sector_rel.is_financial)
    period_kpis = load_period_kpis(db, year, semester, period_type)
    mine = period_kpis.get(company_id)
    if not mine:
        raise HTTPException(404, f"Sin KPIs para {year} semestre {semester}")

    companies = {x.id: x for x in db.scalars(
        select(Company).options(joinedload(Company.sector_rel))).all()}

    kpis = {}
    for kpi_name in KPI_META:
        row = mine.get(kpi_name)
        stats = sector_stats(period_kpis, companies, kpi_name).get(company_id) \
            if row and row.value is not None else None
        kpis[kpi_name] = kpi_payload(kpi_name, row, is_fin, stats)

    alerts = db.scalars(select(FinancialAlert).where(
        FinancialAlert.company_id == company_id, FinancialAlert.year == year,
        FinancialAlert.semester == semester)).all()
    alerts_json = [{
        "code": a.code, "severity": a.severity, "title": a.title,
        "description": a.description, "kpi": a.kpi,
        "observedValue": a.observed_value, "threshold": a.threshold,
        "period": {"year": a.year, "semester": a.semester},
    } for a in alerts]

    stmt = db.scalar(select(FinancialStatement).where(
        FinancialStatement.company_id == company_id,
        FinancialStatement.year == year,
        FinancialStatement.semester == semester,
        FinancialStatement.period_type == period_type))

    from app.services.ingestion import KEY_FIELDS
    missing = [f for f in KEY_FIELDS if stmt and getattr(stmt, f, None) is None]

    return {
        "company": _company_brief(c),
        "period": {
            "year": year, "semester": semester, "periodType": period_type,
            "isConsolidated": stmt.is_consolidated if stmt else None,
            "currency": stmt.currency if stmt else None,
            "sourceUrl": stmt.source_url if stmt else None,
            "updatedAt": stmt.updated_at.isoformat() if stmt and stmt.updated_at else None,
            "isDerived": stmt.is_derived if stmt else None,
        },
        "highlightKpis": highlight_kpis(is_fin),
        "sections": KPI_SECTIONS,
        "kpis": kpis,
        "alerts": alerts_json,
        "score": company_score(db, c, year, semester, period_type),
        "summary": auto_summary(kpis, is_fin, alerts_json),
        "dataQuality": {
            "score": round((1 - len(missing) / len(KEY_FIELDS)) * 100) if stmt else 0,
            "missingFields": missing,
        },
    }


@app.get("/api/companies/{company_id}/history")
def get_company_history(
    company_id: int,
    db: Session = Depends(get_db),
    metric: str = "revenue",
    from_year: int | None = None,
    to_year: int | None = None,
    period_type: str = Query("semester", pattern="^(semester|annual)$"),
):
    _company_or_404(db, company_id)
    if metric not in KPI_META:
        raise HTTPException(400, f"Métrica desconocida: {metric}")
    q = select(CalculatedKPI).where(
        CalculatedKPI.company_id == company_id,
        CalculatedKPI.kpi == metric,
        CalculatedKPI.period_type == period_type,
    ).order_by(CalculatedKPI.year, CalculatedKPI.semester)
    if from_year:
        q = q.where(CalculatedKPI.year >= from_year)
    if to_year:
        q = q.where(CalculatedKPI.year <= to_year)
    rows = db.scalars(q).all()
    meta = KPI_META[metric]
    return {
        "metric": metric, "label": meta["label"],
        "unit": analytics.KPI_UNITS.get(metric, "ratio"),
        "periodType": period_type,
        "series": [{
            "year": r.year, "semester": r.semester,
            "label": f"{r.year}" + (f"-S{r.semester}" if r.semester else ""),
            "value": r.value, "displayValue": format_value(metric, r.value),
            "isEstimated": r.is_estimated,
        } for r in rows],
    }


@app.get("/api/companies/{company_id}/statements")
def get_company_statements(
    company_id: int,
    db: Session = Depends(get_db),
    year: int | None = None,
    semester: int | None = None,
    period_type: str = "semester",
):
    _company_or_404(db, company_id)
    year, semester = _resolve_period(db, year, semester)
    stmt = db.scalar(select(FinancialStatement).where(
        FinancialStatement.company_id == company_id,
        FinancialStatement.year == year,
        FinancialStatement.semester == semester,
        FinancialStatement.period_type == period_type))
    if not stmt:
        raise HTTPException(404, "Sin estados para el periodo")
    return {
        "period": {"year": stmt.year, "semester": stmt.semester,
                   "periodType": stmt.period_type, "isConsolidated": stmt.is_consolidated,
                   "currency": stmt.currency, "flowBasis": stmt.flow_basis,
                   "isDerived": stmt.is_derived, "sourceUrl": stmt.source_url,
                   "periodStart": stmt.period_start, "periodEnd": stmt.period_end},
        "fields": {f: getattr(stmt, f) for f in STATEMENT_FIELDS},
        "unitNote": "Cifras en miles, según reporte SMV",
    }


# ---------------------------------------------------------------------------
# Rankings
# ---------------------------------------------------------------------------
@app.get("/api/rankings/profitability")
def ranking_profitability(
    db: Session = Depends(get_db),
    year: int | None = None,
    semester: int | None = Query(None, ge=1, le=2),
    sector: str | None = None,
    metric: str | None = None,
    financial: bool | None = None,
    limit: int = Query(20, ge=5, le=20),
):
    year, semester = _resolve_period(db, year, semester)
    if year is None:
        return {"ranking": [], "period": None}
    # Por defecto: no financieras por ROIC; financieras por ROE
    explicit = metric is not None
    if metric is None:
        metric = "roe" if financial else "roic"
    if financial is None:
        financial = False
    rows = build_ranking(db, year, semester, metric, sector, financial, limit,
                         require_positive=None)
    # Fallback: si el ROIC no reúne el mínimo de empresas (falta deuda para el
    # capital invertido en varias), caer a ROE, que requiere menos campos.
    if not rows and not explicit and metric == "roic":
        rows = build_ranking(db, year, semester, "roe", sector, financial, limit)
        if rows:
            metric = "roe"
    return {"ranking": rows, "metric": metric,
            "period": {"year": year, "semester": semester, "periodType": "semester"}}


@app.get("/api/rankings/growth")
def ranking_growth(
    db: Session = Depends(get_db),
    year: int | None = None,
    semester: int | None = Query(None, ge=1, le=2),
    sector: str | None = None,
    limit: int = Query(20, ge=5, le=20),
):
    year, semester = _resolve_period(db, year, semester)
    if year is None:
        return {"ranking": [], "period": None}
    rows = build_ranking(db, year, semester, "revenue_growth_yoy", sector, None, limit)
    return {"ranking": rows, "metric": "revenue_growth_yoy",
            "period": {"year": year, "semester": semester, "periodType": "semester"}}


@app.get("/api/rankings/cash-flow")
def ranking_cash_flow(
    db: Session = Depends(get_db),
    year: int | None = None,
    semester: int | None = Query(None, ge=1, le=2),
    limit: int = Query(20, ge=5, le=20),
):
    year, semester = _resolve_period(db, year, semester)
    if year is None:
        return {"ranking": [], "period": None}
    return {"ranking": cash_flow_ranking(db, year, semester, limit),
            "period": {"year": year, "semester": semester, "periodType": "semester"}}


@app.get("/api/rankings/alerts")
def ranking_alerts(
    db: Session = Depends(get_db),
    year: int | None = None,
    semester: int | None = Query(None, ge=1, le=2),
    severity: str | None = None,
):
    year, semester = _resolve_period(db, year, semester)
    if year is None:
        return {"companies": [], "period": None}
    q = (select(FinancialAlert, Company)
         .join(Company, FinancialAlert.company_id == Company.id)
         .where(FinancialAlert.year == year, FinancialAlert.semester == semester))
    if severity:
        q = q.where(FinancialAlert.severity == severity)
    rows = db.execute(q.options(joinedload(Company.sector_rel))).all()
    grouped: dict[int, dict] = {}
    for alert, company in rows:
        g = grouped.setdefault(company.id, {
            **_company_brief(company), "alerts": [], "highCount": 0})
        g["alerts"].append({"code": alert.code, "severity": alert.severity,
                            "title": alert.title, "description": alert.description,
                            "kpi": alert.kpi, "observedValue": alert.observed_value,
                            "threshold": alert.threshold})
        if alert.severity == "alta":
            g["highCount"] += 1
    companies = sorted(grouped.values(), key=lambda g: (-g["highCount"], -len(g["alerts"])))
    return {"companies": companies,
            "period": {"year": year, "semester": semester, "periodType": "semester"}}


# ---------------------------------------------------------------------------
# Catálogos
# ---------------------------------------------------------------------------
@app.get("/api/sectors")
def list_sectors(db: Session = Depends(get_db)):
    rows = db.execute(
        select(Sector, func.count(Company.id).label("n"))
        .outerjoin(Company, Company.sector_id == Sector.id)
        .group_by(Sector.id).order_by(Sector.name)).all()
    return {"sectors": [{"id": s.id, "name": s.name, "isFinancial": s.is_financial,
                         "companies": n} for s, n in rows]}


@app.get("/api/periods")
def list_periods(db: Session = Depends(get_db)):
    rows = db.execute(
        select(CalculatedKPI.year, CalculatedKPI.semester, CalculatedKPI.period_type,
               func.count(func.distinct(CalculatedKPI.company_id)).label("companies"))
        .group_by(CalculatedKPI.year, CalculatedKPI.semester, CalculatedKPI.period_type)
        .order_by(CalculatedKPI.year.desc(), CalculatedKPI.semester.desc())).all()
    return {"periods": [{"year": r.year, "semester": r.semester,
                         "periodType": r.period_type, "companies": r.companies}
                        for r in rows]}


@app.get("/api/summary")
def get_summary(
    db: Session = Depends(get_db),
    year: int | None = None,
    semester: int | None = Query(None, ge=1, le=2),
):
    year, semester = _resolve_period(db, year, semester)
    if year is None:
        total = db.scalar(select(func.count(Company.id))) or 0
        return {"totalCompanies": total, "companiesWithData": 0,
                "companiesWithCompleteData": 0, "sectors": 0, "period": None,
                "profitablePct": None, "positiveFcfPct": None, "lastUpdate": None}
    return market_summary(db, year, semester)


@app.get("/api/kpi-meta")
def get_kpi_meta():
    return {"kpis": KPI_META, "sections": KPI_SECTIONS}


# ---------------------------------------------------------------------------
# Frontend estático
# ---------------------------------------------------------------------------
@app.get("/", include_in_schema=False)
def index():
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))


@app.get("/empresas/{company_id}", include_in_schema=False)
def company_page(company_id: int):
    return FileResponse(os.path.join(STATIC_DIR, "empresa.html"))


if os.path.isdir(STATIC_DIR):
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

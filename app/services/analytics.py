"""Servicios de analítica: comparación sectorial, payloads de KPIs, rankings,
resumen de mercado, score y conclusión automática determinística.

Todas las consultas leen de calculated_kpis (precalculado); no se recalculan
fórmulas en cada request y se evitan consultas N+1 cargando por lote.
"""
import statistics
from collections import defaultdict

from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.config import (
    HIGHLIGHT_KPIS_FINANCIAL,
    HIGHLIGHT_KPIS_NON_FINANCIAL,
    RANKING_MAX_COMPANIES,
    RANKING_MIN_COMPANIES,
)
from app.kpis.engine import KPI_UNITS
from app.kpis.meta import KPI_META
from app.kpis.score import compute_score
from app.kpis.status import (
    LOWER_IS_BETTER,
    NOT_FOR_FINANCIALS,
    STATUS_LABELS,
    TREND_LABELS,
    kpi_status,
    kpi_trend,
)
from app.models import CalculatedKPI, Company, FinancialAlert, FinancialStatement, Sector


# ---------------------------------------------------------------------------
# Formato
# ---------------------------------------------------------------------------
def format_value(kpi: str, value: float | None) -> str:
    if value is None:
        return "No disponible"
    unit = KPI_UNITS.get(kpi, "ratio")
    if unit == "percent":
        return f"{value * 100:.1f}%"
    if unit == "money":
        return f"S/ {value * 1000:,.0f}"  # los estados de la SMV vienen en miles
    if unit == "days":
        return f"{value:.0f} días"
    return f"{value:.2f}x"


# ---------------------------------------------------------------------------
# Carga por lote de KPIs de un periodo
# ---------------------------------------------------------------------------
def load_period_kpis(db: Session, year: int, semester: int | None,
                     period_type: str = "semester") -> dict[int, dict[str, CalculatedKPI]]:
    """company_id -> {kpi -> fila} para un periodo (una sola consulta)."""
    rows = db.scalars(select(CalculatedKPI).where(
        CalculatedKPI.year == year,
        CalculatedKPI.semester == semester,
        CalculatedKPI.period_type == period_type,
    )).all()
    out: dict[int, dict[str, CalculatedKPI]] = defaultdict(dict)
    for r in rows:
        out[r.company_id][r.kpi] = r
    return out


def sector_stats(period_kpis: dict[int, dict], companies: dict[int, Company],
                 kpi: str) -> dict[int, dict]:
    """Mediana, promedio, percentil y posición por sector para un KPI.

    Devuelve company_id -> {median, mean, percentile, rank, n}. Solo compara
    empresas del mismo sector, mismo periodo y mismo tipo de estado.
    """
    by_sector: dict[int | None, list[tuple[int, float]]] = defaultdict(list)
    for cid, kpis in period_kpis.items():
        row = kpis.get(kpi)
        c = companies.get(cid)
        if row and row.value is not None and c:
            by_sector[c.sector_id].append((cid, row.value))

    result = {}
    reverse = kpi not in LOWER_IS_BETTER
    for sector_id, pairs in by_sector.items():
        values = [v for _, v in pairs]
        med = statistics.median(values)
        mean = statistics.fmean(values)
        ordered = sorted(pairs, key=lambda p: p[1], reverse=reverse)
        n = len(values)
        for rank, (cid, v) in enumerate(ordered, start=1):
            worse = sum(1 for x in values if (x < v if reverse else x > v))
            result[cid] = {
                "median": med, "mean": mean, "n": n, "rank": rank,
                "percentile": round(worse / n * 100) if n > 1 else None,
            }
    return result


# ---------------------------------------------------------------------------
# Payload de un KPI (formato consistente de la API)
# ---------------------------------------------------------------------------
def kpi_payload(kpi: str, row: CalculatedKPI | None, is_financial: bool,
                sector: dict | None = None) -> dict:
    meta = KPI_META.get(kpi, {})
    if row is None or row.value is None:
        return {
            "value": None, "displayValue": "No disponible", "isAvailable": False,
            "reason": (row.unavailable_reason if row else "Sin datos para el periodo"),
            "label": meta.get("label", kpi), "formula": meta.get("formula"),
            "explain": meta.get("explain"), "unit": KPI_UNITS.get(kpi, "ratio"),
        }
    trend = kpi_trend(kpi, row.value, row.previous_value)
    status = kpi_status(kpi, row.value, is_financial)
    change = (row.value - row.previous_value) if row.previous_value is not None else None
    payload = {
        "value": round(row.value, 6),
        "displayValue": format_value(kpi, row.value),
        "previousValue": round(row.previous_value, 6) if row.previous_value is not None else None,
        "change": round(change, 6) if change is not None else None,
        "trend": trend, "trendLabel": TREND_LABELS.get(trend),
        "status": status, "statusLabel": STATUS_LABELS.get(status),
        "isAvailable": True, "isEstimated": row.is_estimated,
        "estimationNote": row.unavailable_reason if row.is_estimated else None,
        "label": meta.get("label", kpi), "formula": meta.get("formula"),
        "explain": meta.get("explain"), "unit": KPI_UNITS.get(kpi, "ratio"),
    }
    if sector:
        payload["sectorMedian"] = round(sector["median"], 6)
        payload["sectorMean"] = round(sector["mean"], 6)
        payload["percentile"] = sector["percentile"]
        payload["sectorRank"] = sector["rank"]
        payload["sectorCompanies"] = sector["n"]
    return payload


def highlight_kpis(is_financial: bool) -> list[str]:
    return HIGHLIGHT_KPIS_FINANCIAL if is_financial else HIGHLIGHT_KPIS_NON_FINANCIAL


# ---------------------------------------------------------------------------
# Rankings
# ---------------------------------------------------------------------------
RANKING_COLUMNS = ["operating_margin", "revenue_growth_yoy", "free_cash_flow",
                   "net_debt_to_ebitda"]


def build_ranking(db: Session, year: int, semester: int | None, metric: str,
                  sector_name: str | None = None, financial: bool | None = None,
                  limit: int = RANKING_MAX_COMPANIES, period_type: str = "semester",
                  require_positive: list[str] | None = None) -> list[dict]:
    """Ranking de empresas por un KPI, exigiendo datos completos del KPI y
    excluyendo ratios inválidos. Separa financieras de no financieras."""
    period_kpis = load_period_kpis(db, year, semester, period_type)
    companies = {c.id: c for c in db.scalars(
        select(Company).options(joinedload(Company.sector_rel))).all()}

    rows = []
    for cid, kpis in period_kpis.items():
        c = companies.get(cid)
        if not c:
            continue
        is_fin = bool(c.sector_rel and c.sector_rel.is_financial)
        if financial is not None and is_fin != financial:
            continue
        if sector_name and (not c.sector_rel or c.sector_rel.name != sector_name):
            continue
        if is_fin and metric in NOT_FOR_FINANCIALS:
            continue
        row = kpis.get(metric)
        if not row or row.value is None:
            continue
        if require_positive and any(
                (kpis.get(k) is None or kpis[k].value is None or kpis[k].value <= 0)
                for k in require_positive):
            continue
        entry = {
            "companyId": c.id, "company": c.legal_name, "ticker": c.ticker,
            "sector": c.sector_rel.name if c.sector_rel else "Sin clasificar",
            "isFinancial": is_fin,
            "metric": metric, "value": row.value,
            "displayValue": format_value(metric, row.value),
            "trend": kpi_trend(metric, row.value, row.previous_value),
        }
        for col in RANKING_COLUMNS:
            if col == metric:
                continue
            colrow = kpis.get(col)
            v = colrow.value if colrow and not (is_fin and col in NOT_FOR_FINANCIALS) else None
            entry[col] = {"value": v, "displayValue": format_value(col, v) if v is not None else "No disponible"}
        rows.append(entry)

    reverse = metric not in LOWER_IS_BETTER
    rows.sort(key=lambda r: r["value"], reverse=reverse)
    if len(rows) < RANKING_MIN_COMPANIES:
        return []  # el frontend muestra "datos insuficientes"
    rows = rows[:limit]
    for i, r in enumerate(rows, start=1):
        r["position"] = i
    return rows


def cash_flow_ranking(db: Session, year: int, semester: int | None,
                      limit: int = RANKING_MAX_COMPANIES) -> list[dict]:
    """Mejor generación de caja: FCF positivo, luego margen FCF y conversión."""
    period_kpis = load_period_kpis(db, year, semester)
    companies = {c.id: c for c in db.scalars(
        select(Company).options(joinedload(Company.sector_rel))).all()}
    rows = []
    for cid, kpis in period_kpis.items():
        c = companies.get(cid)
        if not c or (c.sector_rel and c.sector_rel.is_financial):
            continue
        fcf = kpis.get("free_cash_flow")
        margin = kpis.get("fcf_margin")
        conv = kpis.get("cash_conversion")
        if not fcf or fcf.value is None or fcf.value <= 0 or not margin or margin.value is None:
            continue
        rows.append({
            "companyId": c.id, "company": c.legal_name,
            "sector": c.sector_rel.name if c.sector_rel else "Sin clasificar",
            "fcf": {"value": fcf.value, "displayValue": format_value("free_cash_flow", fcf.value)},
            "fcfMargin": {"value": margin.value, "displayValue": format_value("fcf_margin", margin.value)},
            "cashConversion": {"value": conv.value if conv else None,
                               "displayValue": format_value("cash_conversion", conv.value) if conv and conv.value is not None else "No disponible"},
            "sortKey": (margin.value, conv.value if conv and conv.value is not None else -999),
        })
    rows.sort(key=lambda r: r.pop("sortKey"), reverse=True)
    if len(rows) < RANKING_MIN_COMPANIES:
        return []
    rows = rows[:limit]
    for i, r in enumerate(rows, start=1):
        r["position"] = i
    return rows


# ---------------------------------------------------------------------------
# Resumen del mercado
# ---------------------------------------------------------------------------
def market_summary(db: Session, year: int, semester: int | None,
                   period_type: str = "semester") -> dict:
    period_kpis = load_period_kpis(db, year, semester, period_type)
    total_companies = db.scalar(select(func.count(Company.id))) or 0
    sectors = db.scalar(select(func.count(Sector.id))) or 0
    with_data = len(period_kpis)
    complete = profitable = fcf_pos = 0
    for kpis in period_kpis.values():
        ni = kpis.get("net_income")
        fcf = kpis.get("free_cash_flow")
        core = ["revenue", "net_income", "roe"]
        if all(kpis.get(k) and kpis[k].value is not None for k in core):
            complete += 1
        if ni and ni.value is not None and ni.value > 0:
            profitable += 1
        if fcf and fcf.value is not None and fcf.value > 0:
            fcf_pos += 1
    last_update = db.scalar(select(func.max(FinancialStatement.updated_at)))
    return {
        "totalCompanies": total_companies,
        "companiesWithData": with_data,
        "companiesWithCompleteData": complete,
        "sectors": sectors,
        "period": {"year": year, "semester": semester, "periodType": period_type},
        "profitablePct": round(profitable / with_data * 100) if with_data else None,
        "positiveFcfPct": round(fcf_pos / with_data * 100) if with_data else None,
        "lastUpdate": last_update.isoformat() if last_update else None,
    }


# ---------------------------------------------------------------------------
# Score y conclusión automática de una empresa
# ---------------------------------------------------------------------------
def company_score(db: Session, company: Company, year: int, semester: int | None,
                  period_type: str = "semester") -> dict | None:
    is_fin = bool(company.sector_rel and company.sector_rel.is_financial)
    if is_fin:
        return None  # el score 0-100 solo aplica a no financieras

    period_kpis = load_period_kpis(db, year, semester, period_type)
    companies = {c.id: c for c in db.scalars(
        select(Company).options(joinedload(Company.sector_rel))).all()}
    mine = period_kpis.get(company.id)
    if not mine:
        return None

    om_stats = sector_stats(period_kpis, companies, "operating_margin").get(company.id)
    values = {k: (r.value if r else None) for k, r in mine.items()}
    om = mine.get("operating_margin")
    values["operating_margin_percentile"] = om_stats["percentile"] if om_stats else None
    values["operating_margin_change"] = (
        om.value - om.previous_value if om and om.value is not None
        and om.previous_value is not None else None)
    values["total_equity"] = _statement_value(db, company.id, year, semester, period_type, "total_equity")

    alerts_high = db.scalar(select(func.count(FinancialAlert.id)).where(
        FinancialAlert.company_id == company.id, FinancialAlert.year == year,
        FinancialAlert.semester == semester, FinancialAlert.severity == "alta")) or 0

    streak = _positive_streak(db, company.id, year, semester)
    completeness = _completeness(db, company.id, year, semester, period_type)
    s = compute_score(values, alerts_high, streak, completeness)
    return {
        "score": s.score, "level": s.level,
        "dataQualityScore": s.data_quality_score, "confidence": s.confidence,
        "effectiveWeight": round(s.max_points_used, 1),
        "kpisUsed": s.kpis_used, "kpisMissing": s.kpis_missing,
        "components": s.components,
    }


def _statement_value(db, company_id, year, semester, period_type, field):
    stmt = db.scalar(select(FinancialStatement).where(
        FinancialStatement.company_id == company_id,
        FinancialStatement.year == year,
        FinancialStatement.semester == semester,
        FinancialStatement.period_type == period_type))
    return getattr(stmt, field, None) if stmt else None


def _positive_streak(db, company_id, year, semester, max_periods=4):
    """Nº de semestres consecutivos (hacia atrás) con utilidad y FCF positivos."""
    rows = db.scalars(select(CalculatedKPI).where(
        CalculatedKPI.company_id == company_id,
        CalculatedKPI.period_type == "semester",
        CalculatedKPI.kpi.in_(["net_income", "free_cash_flow"]),
    )).all()
    by_period = defaultdict(dict)
    for r in rows:
        by_period[(r.year, r.semester)][r.kpi] = r.value
    periods = sorted(by_period, reverse=True)
    periods = [p for p in periods if p <= (year, semester or 2)][:max_periods]
    if not periods:
        return None
    streak = 0
    for p in periods:
        vals = by_period[p]
        ni, fcf = vals.get("net_income"), vals.get("free_cash_flow")
        if ni is not None and ni > 0 and (fcf is None or fcf > 0):
            streak += 1
        else:
            break
    return streak


def _completeness(db, company_id, year, semester, period_type):
    from app.models import STATEMENT_FIELDS
    from app.services.ingestion import KEY_FIELDS
    stmt = db.scalar(select(FinancialStatement).where(
        FinancialStatement.company_id == company_id,
        FinancialStatement.year == year,
        FinancialStatement.semester == semester,
        FinancialStatement.period_type == period_type))
    if not stmt:
        return 0.0
    present = sum(1 for f in KEY_FIELDS if getattr(stmt, f, None) is not None)
    return present / len(KEY_FIELDS)


def auto_summary(kpis: dict[str, dict], is_financial: bool, alerts: list) -> str:
    """Conclusión automática determinística basada solo en datos disponibles."""
    parts = []

    def val(k):
        p = kpis.get(k) or {}
        return p.get("value") if p.get("isAvailable") else None

    roic, roe, om = val("roic"), val("roe"), val("operating_margin")
    if is_financial:
        if roe is not None:
            nivel = "alta" if roe >= 0.15 else ("moderada" if roe >= 0.08 else "baja")
            parts.append(f"Entidad financiera con rentabilidad patrimonial {nivel} (ROE {roe:.1%})")
    else:
        if roic is not None:
            nivel = "alta" if roic >= 0.12 else ("moderada" if roic >= 0.08 else "baja")
            parts.append(f"Empresa con rentabilidad {nivel} sobre el capital invertido (ROIC {roic:.1%})")
        elif om is not None:
            parts.append(f"Margen operativo de {om:.1%}")
        fcf = val("free_cash_flow")
        if fcf is not None:
            parts.append("flujo de caja libre positivo" if fcf > 0 else "flujo de caja libre negativo")
        ndte = val("net_debt_to_ebitda")
        if ndte is not None:
            nivel = "bajo" if ndte < 1.5 else ("moderado" if ndte <= 3 else "elevado")
            parts.append(f"endeudamiento {nivel} (deuda neta {ndte:.1f}x EBITDA)")
        elif val("net_debt") is not None and val("net_debt") < 0:
            parts.append("caja neta positiva (más efectivo que deuda)")

    trends = []
    for k, nombre in (("roic", "el ROIC"), ("roe", "el ROE"), ("operating_margin", "el margen operativo"),
                      ("interest_coverage", "la cobertura de intereses")):
        p = kpis.get(k) or {}
        if p.get("trend") == "improving":
            trends.append(f"{nombre} mejoró frente al mismo semestre del año anterior")
            break
    for k, nombre in (("interest_coverage", "la cobertura de intereses"),
                      ("operating_margin", "el margen operativo"), ("roe", "el ROE")):
        p = kpis.get(k) or {}
        if p.get("trend") == "worsening":
            trends.append(f"{nombre} se redujo frente al año anterior")
            break

    high_alerts = [a for a in alerts if a.get("severity") == "alta"]
    sentence = ""
    if parts:
        sentence = parts[0]
        if len(parts) > 1:
            sentence += ", " + " y ".join(parts[1:])
        sentence += "."
    if trends:
        sentence += " " + "; aunque ".join(trends) + "."
    if high_alerts:
        sentence += f" Presenta {len(high_alerts)} alerta(s) de severidad alta que conviene revisar."
    return sentence or "No hay datos suficientes para generar una conclusión automática."

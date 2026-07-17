"""Semáforos (estado bueno/intermedio/riesgoso) y tendencias de KPIs.

Los umbrales viven en app/config.py. Las empresas financieras no se evalúan
con umbrales de deuda ni de flujo de caja (ver config.FINANCIAL_*).
"""
from app.config import THRESHOLDS, TREND_TOLERANCE

# KPIs donde un valor MENOR es mejor (afecta el cálculo de tendencia)
LOWER_IS_BETTER = {"net_debt_to_ebitda", "debt_to_equity", "debt_to_assets",
                   "days_sales_outstanding", "days_inventory", "net_debt"}

# KPIs de deuda/flujo que NO se aplican a empresas financieras
NOT_FOR_FINANCIALS = {"net_debt_to_ebitda", "ebitda", "free_cash_flow", "fcf_margin",
                      "fcf_growth_yoy", "fcf_cagr_3y", "dividend_coverage",
                      "debt_to_equity", "debt_to_assets", "net_debt", "total_debt",
                      "interest_coverage", "current_ratio", "quick_ratio",
                      "working_capital", "days_inventory", "cash_conversion",
                      "operating_cash_flow_growth_yoy"}


def kpi_status(kpi: str, value: float | None, is_financial: bool = False) -> str | None:
    """Devuelve 'good' | 'medium' | 'risky' | 'not_significant' | None.

    None = el KPI no tiene semáforo definido (p.ej. márgenes, que se comparan
    contra el sector y el histórico, no contra un umbral universal).
    """
    if value is None:
        return None
    if is_financial and kpi in NOT_FOR_FINANCIALS:
        return None
    t = THRESHOLDS.get(kpi)
    if not t:
        return None

    if kpi == "net_debt_to_ebitda":
        if value < t["good_lt"]:
            return "good"
        return "medium" if value <= t["medium_lte"] else "risky"

    if kpi == "interest_coverage":
        if value > t["good_gt"]:
            return "good"
        return "medium" if value >= t["medium_gte"] else "risky"

    if kpi == "current_ratio":
        lo, hi = t["good_range"]
        if lo <= value <= hi:
            return "good"
        mlo, mhi = t["medium_range"]
        if mlo <= value < mhi or value > hi:
            return "medium"  # exceso de liquidez también es subóptimo, no riesgoso
        return "risky"

    # Regla genérica "mayor es mejor"
    if value >= t["good_gte"]:
        return "good"
    return "medium" if value >= t["medium_gte"] else "risky"


def kpi_trend(kpi: str, current: float | None, previous: float | None) -> str | None:
    """'improving' | 'stable' | 'worsening' comparando contra el mismo
    semestre del año anterior. None si falta algún dato."""
    if current is None or previous is None:
        return None
    base = max(abs(previous), 1e-9)
    delta = (current - previous) / base
    if kpi in LOWER_IS_BETTER:
        delta = -delta
    if delta > TREND_TOLERANCE:
        return "improving"
    if delta < -TREND_TOLERANCE:
        return "worsening"
    return "stable"


STATUS_LABELS = {"good": "Bueno", "medium": "Intermedio", "risky": "Riesgoso",
                 "not_significant": "No significativo"}
TREND_LABELS = {"improving": "Mejorando", "stable": "Estable", "worsening": "Empeorando"}

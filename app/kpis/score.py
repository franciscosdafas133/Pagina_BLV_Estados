"""Score financiero 0-100 para empresas NO financieras.

El score se reescala según los KPIs realmente disponibles (peso efectivo) y
se acompaña de un data_quality_score y un nivel de confianza para evitar que
una empresa con pocos datos obtenga una puntuación engañosa.
"""
from dataclasses import dataclass, field

from app.config import SCORE_LEVELS, SCORE_WEIGHTS


@dataclass
class ScoreResult:
    score: int | None
    level: str | None
    raw_points: float
    max_points_used: float          # peso efectivo aplicado
    kpis_used: list = field(default_factory=list)
    kpis_missing: list = field(default_factory=list)
    data_quality_score: int = 0
    confidence: str = "baja"        # alta | media | baja
    components: dict = field(default_factory=dict)


def _frac(value, lo, hi) -> float:
    """Fracción 0..1 de un valor dentro de un rango (lineal, acotada)."""
    if hi == lo:
        return 1.0 if value >= hi else 0.0
    return max(0.0, min(1.0, (value - lo) / (hi - lo)))


def compute_score(k: dict, alerts_high: int = 0, positive_streak: int | None = None,
                  data_completeness: float = 0.0) -> ScoreResult:
    """k: dict kpi -> valor (float o None). Solo empresas no financieras.

    positive_streak: nº de periodos consecutivos con utilidad y FCF positivos
    (None si no hay historia suficiente).
    data_completeness: fracción 0..1 de campos financieros clave disponibles.
    """
    W = SCORE_WEIGHTS
    pts, used_w = 0.0, 0.0
    used, missing = [], []
    comp: dict[str, float] = {}

    def add(name: str, weight: float, value, scorer):
        nonlocal pts, used_w
        if value is None:
            missing.append(name)
            return
        p = scorer(value) * weight
        pts += p
        used_w += weight
        used.append(name)
        comp[name] = round(p, 2)

    # Rentabilidad (25)
    add("roic", W["profitability"]["roic"], k.get("roic"), lambda v: _frac(v, 0.0, 0.15))
    add("roe", W["profitability"]["roe"], k.get("roe"), lambda v: _frac(v, 0.0, 0.18))
    add("operating_margin_vs_sector", W["profitability"]["operating_margin_vs_sector"],
        k.get("operating_margin_percentile"), lambda v: v / 100.0)
    add("margin_trend", W["profitability"]["margin_trend"], k.get("operating_margin_change"),
        lambda v: 1.0 if v > 0.005 else (0.5 if v >= -0.005 else 0.0))

    # Flujo de caja (25)
    add("fcf_positive", W["cash_flow"]["fcf_positive"], k.get("free_cash_flow"),
        lambda v: 1.0 if v > 0 else 0.0)
    add("cash_conversion", W["cash_flow"]["cash_conversion"], k.get("cash_conversion"),
        lambda v: _frac(v, 0.4, 1.0))
    add("fcf_margin", W["cash_flow"]["fcf_margin"], k.get("fcf_margin"),
        lambda v: _frac(v, 0.0, 0.12))
    add("fcf_growth", W["cash_flow"]["fcf_growth"], k.get("fcf_growth_yoy"),
        lambda v: 1.0 if v > 0 else 0.0)

    # Solidez (25)
    add("net_debt_to_ebitda", W["solvency"]["net_debt_to_ebitda"], k.get("net_debt_to_ebitda"),
        lambda v: 1.0 - _frac(v, 1.5, 4.0))
    add("interest_coverage", W["solvency"]["interest_coverage"], k.get("interest_coverage"),
        lambda v: _frac(v, 1.0, 6.0))
    add("current_ratio", W["solvency"]["current_ratio"], k.get("current_ratio"),
        lambda v: _frac(v, 0.8, 1.2) if v <= 2.5 else 0.75)
    add("positive_equity", W["solvency"]["positive_equity"], k.get("total_equity"),
        lambda v: 1.0 if v > 0 else 0.0)

    # Crecimiento (15)
    add("revenue_growth", W["growth"]["revenue_growth"], k.get("revenue_growth_yoy"),
        lambda v: _frac(v, -0.05, 0.15))
    add("operating_income_growth", W["growth"]["operating_income_growth"],
        k.get("operating_income_growth_yoy"), lambda v: _frac(v, -0.05, 0.20))
    add("net_income_growth", W["growth"]["net_income_growth"],
        k.get("net_income_growth_yoy"), lambda v: _frac(v, -0.05, 0.20))

    # Consistencia (10)
    add("positive_kpi_streak", W["consistency"]["positive_kpi_streak"], positive_streak,
        lambda v: _frac(v, 0, 4))
    add("no_severe_alerts", W["consistency"]["no_severe_alerts"], alerts_high,
        lambda v: 1.0 if v == 0 else (0.4 if v == 1 else 0.0))
    add("data_completeness", W["consistency"]["data_completeness"], data_completeness,
        lambda v: v)

    total_w = sum(sum(g.values()) for g in W.values())
    dq = int(round(data_completeness * 100))

    if used_w < total_w * 0.4:
        # Muy pocos KPIs disponibles: no se emite score
        return ScoreResult(None, None, pts, used_w, used, missing, dq, "baja", comp)

    score = int(round(pts / used_w * 100))
    level = next(label for floor, label in SCORE_LEVELS if score >= floor)
    coverage = used_w / total_w
    confidence = "alta" if coverage >= 0.85 and dq >= 80 else ("media" if coverage >= 0.6 else "baja")
    return ScoreResult(score, level, round(pts, 2), used_w, used, missing, dq, confidence, comp)

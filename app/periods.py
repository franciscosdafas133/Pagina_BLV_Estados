"""Capa de normalización de periodos.

La SMV entrega estados intermedios trimestrales cuyas cifras de resultados y
flujos suelen venir ACUMULADAS desde enero (YTD), además de estados anuales
auditados. El balance general siempre es una foto al cierre.

Construcción de periodos (función central `build_period`):

- Primer semestre  (S1): flujos = acumulado al Q2 (ene-jun); balance = cierre Q2.
- Segundo semestre (S2): flujos = acumulado Q4 (o anual) - acumulado Q2
                         (jul-dic); balance = cierre Q4 / anual.
- Año completo:          flujos = acumulado Q4 o estado anual; balance = cierre.
- TTM (últimos 12 meses) al cierre de S1 del año Y:
                         flujos = anual(Y-1) - S1(Y-1) + S1(Y).

Nunca se suman valores acumulados dos veces: los semestres se derivan por
diferencia de acumulados, no por suma de trimestres.
"""
from dataclasses import dataclass

# Campos de flujo (resultados + efectivo): se acumulan a lo largo del año y
# deben diferenciarse para obtener un semestre. Los campos de balance y
# accionarios son puntuales (foto al cierre) y se toman del último filing.
FLOW_FIELDS = [
    "revenue", "cost_of_sales", "gross_profit", "operating_income", "ebit",
    "financial_expenses", "income_before_tax", "income_tax", "net_income",
    "net_income_attributable", "depreciation_and_amortization",
    "operating_cash_flow", "investing_cash_flow", "financing_cash_flow",
    "capex", "dividends_paid", "interest_paid",
]
STOCK_FIELDS = [
    "cash_and_equivalents", "current_assets", "total_assets",
    "accounts_receivable", "inventory", "current_liabilities",
    "total_liabilities", "short_term_debt", "long_term_debt", "total_debt",
    "total_equity", "equity_attributable",
    "shares_outstanding", "weighted_average_shares", "diluted_shares",
    "market_price", "market_cap",
]

SEMESTER_BOUNDS = {
    1: ("01-01", "06-30"),  # enero a junio
    2: ("07-01", "12-31"),  # julio a diciembre
}

QUARTER_TO_SEMESTER = {1: 1, 2: 1, 3: 2, 4: 2}


@dataclass
class PeriodData:
    """Resultado de la normalización: un dict de campos financieros más metadatos."""
    year: int
    semester: int | None       # None = anual / TTM
    period_type: str           # 'semester' | 'annual' | 'ttm'
    period_start: str | None
    period_end: str | None
    fields: dict               # campo -> float | None
    is_derived: bool = False
    notes: str = ""


def semester_of_quarter(quarter: int) -> int:
    """Trimestres I-II -> primer semestre; III-IV -> segundo semestre."""
    if quarter not in QUARTER_TO_SEMESTER:
        raise ValueError(f"Trimestre inválido: {quarter}")
    return QUARTER_TO_SEMESTER[quarter]


def period_dates(year: int, semester: int | None) -> tuple[str, str]:
    if semester is None:
        return f"{year}-01-01", f"{year}-12-31"
    s, e = SEMESTER_BOUNDS[semester]
    return f"{year}-{s}", f"{year}-{e}"


def _diff(a: float | None, b: float | None) -> float | None:
    """a - b respetando nulls: si falta cualquiera, el resultado es None."""
    if a is None or b is None:
        return None
    return a - b


def build_period(
    year: int,
    target: str,
    q2_ytd: dict | None = None,
    q4_ytd: dict | None = None,
    annual: dict | None = None,
    prev_annual: dict | None = None,
    prev_q2_ytd: dict | None = None,
) -> PeriodData | None:
    """Función central de construcción de periodos.

    target: 's1' | 's2' | 'annual' | 'ttm'
    Cada dict de entrada contiene los campos financieros de un filing
    (flujos en base YTD acumulada). Devuelve None si faltan los insumos.
    """
    full_year = annual or q4_ytd  # el anual auditado tiene prioridad

    if target == "s1":
        if not q2_ytd:
            return None
        start, end = period_dates(year, 1)
        return PeriodData(year, 1, "semester", start, end, dict(q2_ytd),
                          is_derived=False,
                          notes="Flujos = acumulado enero-junio (filing Q2)")

    if target == "s2":
        if not full_year:
            return None
        start, end = period_dates(year, 2)
        fields = {}
        for f in FLOW_FIELDS:
            if q2_ytd:
                fields[f] = _diff(full_year.get(f), q2_ytd.get(f))
            else:
                fields[f] = None  # sin Q2 no se puede aislar el semestre
        for f in STOCK_FIELDS:
            fields[f] = full_year.get(f)  # balance = foto al cierre del año
        return PeriodData(year, 2, "semester", start, end, fields,
                          is_derived=True,
                          notes="Flujos = acumulado anual - acumulado junio; balance al cierre")

    if target == "annual":
        if not full_year:
            return None
        start, end = period_dates(year, None)
        return PeriodData(year, None, "annual", start, end, dict(full_year),
                          is_derived=annual is None,
                          notes="Estado anual" if annual else "Acumulado al Q4")

    if target == "ttm":
        # TTM al cierre de junio del año `year`
        if not (q2_ytd and prev_annual and prev_q2_ytd):
            return None
        fields = {}
        for f in FLOW_FIELDS:
            prev_h2 = _diff(prev_annual.get(f), prev_q2_ytd.get(f))
            cur_h1 = q2_ytd.get(f)
            fields[f] = None if (prev_h2 is None or cur_h1 is None) else prev_h2 + cur_h1
        for f in STOCK_FIELDS:
            fields[f] = q2_ytd.get(f)
        return PeriodData(year, 1, "ttm", f"{year - 1}-07-01", f"{year}-06-30",
                          fields, is_derived=True,
                          notes="TTM = S2 del año anterior + S1 actual")

    raise ValueError(f"Periodo objetivo desconocido: {target}")

"""Funciones puras de cálculo de KPIs.

Reglas globales:
- None significa "dato no disponible": cualquier operación con None -> None.
- División entre cero o denominador None -> None (nunca Infinity/NaN).
- Los resultados van acompañados, cuando corresponde, de una marca
  `estimated` (aproximaciones documentadas) vía KPIResult.
"""
import math
from dataclasses import dataclass, field

from app.config import (
    EFFECTIVE_TAX_RATE_FALLBACK,
    EFFECTIVE_TAX_RATE_MAX,
    EFFECTIVE_TAX_RATE_MIN,
)


@dataclass
class KPIResult:
    value: float | None
    estimated: bool = False
    reason: str | None = None  # por qué no está disponible o por qué es estimado
    meta: dict = field(default_factory=dict)


def _ok(x) -> bool:
    return x is not None and isinstance(x, (int, float)) and math.isfinite(x)


def safe_div(num, den) -> float | None:
    """División segura: None si falta un operando o el denominador es 0."""
    if not _ok(num) or not _ok(den) or den == 0:
        return None
    v = num / den
    return v if math.isfinite(v) else None


def average(current, previous) -> float | None:
    """Promedio de dos periodos; None si falta cualquiera."""
    if not _ok(current) or not _ok(previous):
        return None
    return (current + previous) / 2


# ---------------------------------------------------------------------------
# A. Rentabilidad
# ---------------------------------------------------------------------------
def gross_margin(gross_profit, revenue) -> float | None:
    return safe_div(gross_profit, revenue)


def operating_margin(operating_income, revenue) -> float | None:
    return safe_div(operating_income, revenue)


def net_margin(net_income_attributable, revenue) -> float | None:
    return safe_div(net_income_attributable, revenue)


def roa(net_income, assets_current, assets_previous=None) -> KPIResult:
    """ROA sobre activos promedio; si falta el periodo anterior usa el actual
    como aproximación (marcada como estimada)."""
    avg = average(assets_current, assets_previous)
    if avg is None and _ok(assets_current):
        v = safe_div(net_income, assets_current)
        return KPIResult(v, estimated=v is not None,
                         reason="Sin balance del periodo anterior: se usó el activo final")
    return KPIResult(safe_div(net_income, avg))


def roe(net_income_attributable, equity_current, equity_previous=None) -> KPIResult:
    avg = average(equity_current, equity_previous)
    if avg is None and _ok(equity_current):
        v = safe_div(net_income_attributable, equity_current)
        return KPIResult(v, estimated=v is not None,
                         reason="Sin balance del periodo anterior: se usó el patrimonio final")
    if _ok(avg) and avg <= 0:
        return KPIResult(None, reason="Patrimonio promedio negativo o cero: ROE no significativo")
    return KPIResult(safe_div(net_income_attributable, avg))


def effective_tax_rate(income_tax, income_before_tax) -> KPIResult:
    """Tasa efectiva acotada; con base imponible <= 0 usa la tasa estatutaria."""
    if not _ok(income_before_tax) or income_before_tax <= 0:
        return KPIResult(EFFECTIVE_TAX_RATE_FALLBACK, estimated=True,
                         reason="Resultado antes de impuestos <= 0: se usó tasa estatutaria 29.5%")
    rate = safe_div(abs(income_tax) if _ok(income_tax) else None, income_before_tax)
    if rate is None:
        return KPIResult(EFFECTIVE_TAX_RATE_FALLBACK, estimated=True,
                         reason="Sin gasto por impuesto: se usó tasa estatutaria 29.5%")
    if rate < EFFECTIVE_TAX_RATE_MIN or rate > EFFECTIVE_TAX_RATE_MAX:
        return KPIResult(EFFECTIVE_TAX_RATE_FALLBACK, estimated=True,
                         reason=f"Tasa efectiva anómala ({rate:.0%}): se acotó a la estatutaria")
    return KPIResult(rate)


def invested_capital(total_equity, total_debt, cash_and_equivalents) -> float | None:
    if not _ok(total_equity) or not _ok(total_debt):
        return None
    cash = cash_and_equivalents if _ok(cash_and_equivalents) else 0.0
    return total_equity + total_debt - cash


def roic(ebit, income_tax, income_before_tax,
         equity_cur, debt_cur, cash_cur,
         equity_prev=None, debt_prev=None, cash_prev=None) -> KPIResult:
    """ROIC = NOPAT / capital invertido promedio."""
    if not _ok(ebit):
        return KPIResult(None, reason="Falta EBIT / utilidad operativa")
    tax = effective_tax_rate(income_tax, income_before_tax)
    nopat = ebit * (1 - tax.value)

    ic_cur = invested_capital(equity_cur, debt_cur, cash_cur)
    ic_prev = invested_capital(equity_prev, debt_prev, cash_prev)
    if ic_cur is None:
        return KPIResult(None, reason="Falta patrimonio o deuda total para el capital invertido")

    avg_ic = average(ic_cur, ic_prev)
    estimated = tax.estimated
    reason = tax.reason
    if avg_ic is None:
        avg_ic = ic_cur
        estimated = True
        reason = (reason + "; " if reason else "") + "Capital invertido promedio aproximado con el saldo final"
    if avg_ic <= 0:
        return KPIResult(None, reason="Capital invertido promedio <= 0: ROIC no significativo")
    return KPIResult(safe_div(nopat, avg_ic), estimated=estimated, reason=reason,
                     meta={"nopat": nopat, "invested_capital": avg_ic, "tax_rate": tax.value})


# ---------------------------------------------------------------------------
# B. Crecimiento
# ---------------------------------------------------------------------------
def growth_yoy(current, previous) -> float | None:
    """Crecimiento interanual. Sin periodo previo o con base 0 -> None.
    Con base negativa el % es engañoso: se devuelve None (no comparable)."""
    if not _ok(current) or not _ok(previous) or previous == 0:
        return None
    if previous < 0:
        return None
    return (current - previous) / previous


def cagr(final, initial, years) -> float | None:
    """CAGR; requiere valores positivos en ambos extremos."""
    if not _ok(final) or not _ok(initial) or initial <= 0 or final <= 0 or years <= 0:
        return None
    return (final / initial) ** (1 / years) - 1


# ---------------------------------------------------------------------------
# C. Flujo de caja
# ---------------------------------------------------------------------------
def free_cash_flow(operating_cash_flow, capex) -> float | None:
    """FCF = flujo operativo - CAPEX. El CAPEX debe llegar normalizado a
    positivo (magnitud); se usa abs() como defensa extra para no restarlo
    dos veces si viniera negativo."""
    if not _ok(operating_cash_flow) or not _ok(capex):
        return None
    return operating_cash_flow - abs(capex)


def fcf_margin(fcf, revenue) -> float | None:
    return safe_div(fcf, revenue)


def cash_conversion(operating_cash_flow, net_income) -> float | None:
    """Conversión de utilidad en caja; con utilidad <= 0 no es significativa."""
    if not _ok(net_income) or net_income <= 0:
        return None
    return safe_div(operating_cash_flow, net_income)


def dividend_coverage(fcf, dividends_paid) -> KPIResult:
    if not _ok(dividends_paid) or dividends_paid == 0:
        return KPIResult(None, reason="No aplica: sin dividendos pagados en el periodo")
    return KPIResult(safe_div(fcf, abs(dividends_paid)))


# ---------------------------------------------------------------------------
# D. Endeudamiento
# ---------------------------------------------------------------------------
def net_debt(total_debt, cash_and_equivalents) -> float | None:
    if not _ok(total_debt) or not _ok(cash_and_equivalents):
        return None
    return total_debt - cash_and_equivalents


def debt_to_equity(total_debt, total_equity) -> float | None:
    if _ok(total_equity) and total_equity <= 0:
        return None  # patrimonio negativo: el ratio pierde sentido (hay alerta aparte)
    return safe_div(total_debt, total_equity)


def debt_to_assets(total_debt, total_assets) -> float | None:
    return safe_div(total_debt, total_assets)


def liabilities_to_equity(total_liabilities, total_equity) -> float | None:
    """Apalancamiento total = pasivo total / patrimonio. Es el indicador que la
    BVL/SMV reporta como 'Deuda/Patrimonio'. Distinto de debt_to_equity, que usa
    solo la deuda financiera."""
    if _ok(total_equity) and total_equity <= 0:
        return None
    return safe_div(total_liabilities, total_equity)


def ebitda(ebit_value, depreciation_and_amortization) -> KPIResult:
    """EBITDA aproximado = EBIT + D&A. Nunca se inventa: si falta D&A, no hay EBITDA."""
    if not _ok(ebit_value):
        return KPIResult(None, reason="Falta EBIT")
    if not _ok(depreciation_and_amortization):
        return KPIResult(None, reason="Falta depreciación y amortización para aproximar EBITDA")
    return KPIResult(ebit_value + abs(depreciation_and_amortization), estimated=True,
                     reason="EBITDA aproximado como EBIT + depreciación y amortización")


def net_debt_to_ebitda(net_debt_value, ebitda_value) -> KPIResult:
    if not _ok(ebitda_value):
        return KPIResult(None, reason="EBITDA no disponible")
    if ebitda_value <= 0:
        return KPIResult(None, reason="No significativo: EBITDA menor o igual a cero")
    if not _ok(net_debt_value):
        return KPIResult(None, reason="Deuda neta no disponible")
    return KPIResult(net_debt_value / ebitda_value)


def interest_coverage(ebit_value, financial_expenses) -> KPIResult:
    if not _ok(ebit_value):
        return KPIResult(None, reason="Falta EBIT")
    if not _ok(financial_expenses) or financial_expenses == 0:
        return KPIResult(None, reason="Sin gasto financiero reportado: cobertura no aplicable")
    return KPIResult(ebit_value / abs(financial_expenses))


# ---------------------------------------------------------------------------
# E. Liquidez
# ---------------------------------------------------------------------------
def current_ratio(current_assets, current_liabilities) -> float | None:
    return safe_div(current_assets, current_liabilities)


def quick_ratio(current_assets, inventory, current_liabilities) -> float | None:
    if not _ok(current_assets):
        return None
    inv = inventory if _ok(inventory) else 0.0
    return safe_div(current_assets - inv, current_liabilities)


def working_capital(current_assets, current_liabilities) -> float | None:
    if not _ok(current_assets) or not _ok(current_liabilities):
        return None
    return current_assets - current_liabilities


# ---------------------------------------------------------------------------
# F. Eficiencia
# ---------------------------------------------------------------------------
def asset_turnover(revenue, assets_current, assets_previous=None) -> float | None:
    avg = average(assets_current, assets_previous)
    if avg is None:
        avg = assets_current if _ok(assets_current) else None
    return safe_div(revenue, avg)


def days_sales_outstanding(receivables_cur, receivables_prev, revenue, days_in_period) -> float | None:
    avg = average(receivables_cur, receivables_prev)
    if avg is None:
        avg = receivables_cur if _ok(receivables_cur) else None
    ratio = safe_div(avg, revenue)
    return ratio * days_in_period if ratio is not None else None


def days_inventory(inventory_cur, inventory_prev, cost_of_sales, days_in_period) -> float | None:
    avg = average(inventory_cur, inventory_prev)
    if avg is None:
        avg = inventory_cur if _ok(inventory_cur) else None
    cost = abs(cost_of_sales) if _ok(cost_of_sales) else None
    ratio = safe_div(avg, cost)
    return ratio * days_in_period if ratio is not None else None


def equity_to_assets(total_equity, total_assets) -> float | None:
    """Patrimonio sobre activos (solidez, clave en financieras)."""
    return safe_div(total_equity, total_assets)

"""Motor de KPIs: calcula todos los indicadores de un periodo a partir de los
campos normalizados del periodo actual, del balance del periodo anterior y del
mismo periodo del año anterior (para crecimientos interanuales).
"""
from app.config import DAYS_PER_PERIOD
from app.kpis import formulas as F
from app.kpis.formulas import KPIResult

# KPI -> unidad de presentación
KPI_UNITS = {
    "gross_margin": "percent", "operating_margin": "percent", "net_margin": "percent",
    "roa": "percent", "roe": "percent", "roic": "percent",
    "revenue_growth_yoy": "percent", "operating_income_growth_yoy": "percent",
    "net_income_growth_yoy": "percent", "total_assets_growth_yoy": "percent",
    "equity_growth_yoy": "percent", "operating_cash_flow_growth_yoy": "percent",
    "fcf_growth_yoy": "percent", "revenue_cagr_3y": "percent",
    "net_income_cagr_3y": "percent", "fcf_cagr_3y": "percent",
    "free_cash_flow": "money", "fcf_margin": "percent", "cash_conversion": "ratio",
    "dividend_coverage": "ratio", "net_debt": "money", "total_debt": "money",
    "debt_to_equity": "ratio", "debt_to_assets": "percent", "liabilities_to_equity": "ratio",
    "net_debt_to_ebitda": "ratio", "interest_coverage": "ratio", "ebitda": "money",
    "current_ratio": "ratio", "quick_ratio": "ratio", "working_capital": "money",
    "asset_turnover": "ratio", "days_sales_outstanding": "days", "days_inventory": "days",
    "equity_to_assets": "percent",
    "revenue": "money", "operating_income": "money", "net_income": "money",
    "operating_cash_flow": "money",
}


def _as_result(x) -> KPIResult:
    return x if isinstance(x, KPIResult) else KPIResult(x)


def compute_kpis(cur: dict, prev_balance: dict | None = None,
                 prev_year_same: dict | None = None,
                 period_type: str = "semester") -> dict[str, KPIResult]:
    """Calcula todos los KPIs de un periodo.

    cur            : campos del periodo actual (flujos del periodo + balance al cierre)
    prev_balance   : balance al cierre del periodo inmediatamente anterior
                     (para promedios de activos/patrimonio/capital invertido)
    prev_year_same : mismo periodo (mismo semestre) del año anterior
                     (para crecimientos interanuales — nunca semestres distintos)
    """
    pb = prev_balance or {}
    py = prev_year_same or {}
    days = DAYS_PER_PERIOD.get(period_type, 182)
    g = cur.get

    out: dict[str, KPIResult] = {}

    # Valores base (para gráficos y rankings de magnitud)
    for base in ("revenue", "operating_income", "net_income", "operating_cash_flow"):
        out[base] = KPIResult(g(base))

    # A. Rentabilidad
    out["gross_margin"] = _as_result(F.gross_margin(g("gross_profit"), g("revenue")))
    out["operating_margin"] = _as_result(F.operating_margin(g("operating_income"), g("revenue")))
    out["net_margin"] = _as_result(F.net_margin(g("net_income_attributable"), g("revenue")))
    out["roa"] = F.roa(g("net_income"), g("total_assets"), pb.get("total_assets"))
    out["roe"] = F.roe(g("net_income_attributable"), g("equity_attributable"), pb.get("equity_attributable"))
    out["roic"] = F.roic(
        g("ebit"), g("income_tax"), g("income_before_tax"),
        g("total_equity"), g("total_debt"), g("cash_and_equivalents"),
        pb.get("total_equity"), pb.get("total_debt"), pb.get("cash_and_equivalents"),
    )

    # C. Flujo de caja
    fcf = F.free_cash_flow(g("operating_cash_flow"), g("capex"))
    out["free_cash_flow"] = KPIResult(fcf) if fcf is not None else KPIResult(
        None, reason="Falta flujo operativo o CAPEX")
    out["fcf_margin"] = _as_result(F.fcf_margin(fcf, g("revenue")))
    out["cash_conversion"] = _as_result(F.cash_conversion(g("operating_cash_flow"), g("net_income")))
    out["dividend_coverage"] = F.dividend_coverage(fcf, g("dividends_paid"))

    # D. Endeudamiento
    out["total_debt"] = KPIResult(g("total_debt"))
    nd = F.net_debt(g("total_debt"), g("cash_and_equivalents"))
    out["net_debt"] = KPIResult(nd)
    out["debt_to_equity"] = _as_result(F.debt_to_equity(g("total_debt"), g("total_equity")))
    out["debt_to_assets"] = _as_result(F.debt_to_assets(g("total_debt"), g("total_assets")))
    out["liabilities_to_equity"] = _as_result(F.liabilities_to_equity(
        g("total_liabilities"), g("total_equity")))
    ebitda_r = F.ebitda(g("ebit"), g("depreciation_and_amortization"))
    out["ebitda"] = ebitda_r
    # Deuda neta/EBITDA se evalúa siempre en base anualizada cuando el periodo
    # es semestral: comparar deuda (stock) contra EBITDA de solo 6 meses la
    # duplicaría artificialmente.
    ebitda_annualized = ebitda_r.value * 2 if (ebitda_r.value is not None and period_type == "semester") else ebitda_r.value
    ndte = F.net_debt_to_ebitda(nd, ebitda_annualized)
    if ndte.value is not None and period_type == "semester":
        ndte = KPIResult(ndte.value, estimated=True,
                         reason="EBITDA semestral anualizado (x2) para comparar contra el stock de deuda")
    out["net_debt_to_ebitda"] = ndte
    out["interest_coverage"] = F.interest_coverage(g("ebit"), g("financial_expenses"))

    # E. Liquidez
    out["current_ratio"] = _as_result(F.current_ratio(g("current_assets"), g("current_liabilities")))
    out["quick_ratio"] = _as_result(F.quick_ratio(g("current_assets"), g("inventory"), g("current_liabilities")))
    out["working_capital"] = _as_result(F.working_capital(g("current_assets"), g("current_liabilities")))

    # F. Eficiencia
    out["asset_turnover"] = _as_result(F.asset_turnover(g("revenue"), g("total_assets"), pb.get("total_assets")))
    out["days_sales_outstanding"] = _as_result(F.days_sales_outstanding(
        g("accounts_receivable"), pb.get("accounts_receivable"), g("revenue"), days))
    out["days_inventory"] = _as_result(F.days_inventory(
        g("inventory"), pb.get("inventory"), g("cost_of_sales"), days))
    out["equity_to_assets"] = _as_result(F.equity_to_assets(g("total_equity"), g("total_assets")))

    # B. Crecimiento interanual (mismo semestre vs mismo semestre)
    prev_fcf = F.free_cash_flow(py.get("operating_cash_flow"), py.get("capex")) if py else None
    growth_defs = {
        "revenue_growth_yoy": ("revenue", g("revenue"), py.get("revenue")),
        "operating_income_growth_yoy": ("operating_income", g("operating_income"), py.get("operating_income")),
        "net_income_growth_yoy": ("net_income", g("net_income"), py.get("net_income")),
        "total_assets_growth_yoy": ("total_assets", g("total_assets"), py.get("total_assets")),
        "equity_growth_yoy": ("total_equity", g("total_equity"), py.get("total_equity")),
        "operating_cash_flow_growth_yoy": ("operating_cash_flow", g("operating_cash_flow"), py.get("operating_cash_flow")),
        "fcf_growth_yoy": ("free_cash_flow", fcf, prev_fcf),
    }
    for kpi, (_, cur_v, prev_v) in growth_defs.items():
        v = F.growth_yoy(cur_v, prev_v)
        if v is None:
            reason = ("Sin dato del mismo periodo del año anterior"
                      if (prev_v is None) else "Base del año anterior <= 0: variación no comparable")
            out[kpi] = KPIResult(None, reason=reason)
        else:
            out[kpi] = KPIResult(v)

    return out


def compute_cagr_kpis(series: dict[int, dict]) -> dict[str, KPIResult]:
    """CAGR a 3 años a partir de una serie anual {año: campos}."""
    out = {}
    years = sorted(series)
    defs = {
        "revenue_cagr_3y": "revenue",
        "net_income_cagr_3y": "net_income",
        "fcf_cagr_3y": None,  # se calcula aparte
    }
    if len(years) >= 4:
        y_final, y_init = years[-1], years[-4]
        span = y_final - y_init
        fin, ini = series[y_final], series[y_init]
        out["revenue_cagr_3y"] = KPIResult(F.cagr(fin.get("revenue"), ini.get("revenue"), span))
        out["net_income_cagr_3y"] = KPIResult(F.cagr(fin.get("net_income"), ini.get("net_income"), span))
        fcf_f = F.free_cash_flow(fin.get("operating_cash_flow"), fin.get("capex"))
        fcf_i = F.free_cash_flow(ini.get("operating_cash_flow"), ini.get("capex"))
        out["fcf_cagr_3y"] = KPIResult(F.cagr(fcf_f, fcf_i, span))
    else:
        for k in defs:
            out[k] = KPIResult(None, reason="Se requieren al menos 4 años de datos anuales")
    return out

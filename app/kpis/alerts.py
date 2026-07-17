"""Motor de alertas automáticas (reglas determinísticas).

Cada alerta: código, severidad, título, descripción, KPI, valor observado y
umbral. Solo se emite una alerta cuando TODOS los datos que la sustentan
existen (no se alerta sobre datos faltantes).
"""
from dataclasses import dataclass

from app.config import ALERT_THRESHOLDS as T


@dataclass
class Alert:
    code: str
    severity: str  # alta | media | baja
    title: str
    description: str
    kpi: str | None = None
    observed_value: float | None = None
    threshold: str | None = None


def _ok(x):
    return x is not None


def evaluate_alerts(cur: dict, kpis: dict, prev: dict | None = None,
                    prev_kpis: dict | None = None, is_financial: bool = False) -> list[Alert]:
    """cur/prev: campos financieros del periodo actual y del mismo periodo del
    año anterior. kpis/prev_kpis: valores de KPIs ya calculados (floats o None)."""
    alerts: list[Alert] = []
    prev = prev or {}
    prev_kpis = prev_kpis or {}
    add = alerts.append

    ni = cur.get("net_income")
    ocf = cur.get("operating_cash_flow")
    fcf = kpis.get("free_cash_flow")
    cc = kpis.get("cash_conversion")

    # --- Calidad de utilidades ---
    if _ok(ni) and _ok(ocf) and ni > 0 and ocf < 0:
        add(Alert("EARNINGS_NO_CASH", "alta", "Utilidad positiva con flujo operativo negativo",
                  "La empresa reporta utilidad neta positiva pero su operación consume caja; "
                  "las ganancias contables no se están convirtiendo en efectivo.",
                  "operating_cash_flow", ocf, "flujo operativo < 0 con utilidad > 0"))
    if _ok(cc) and cc < T["cash_conversion_low"]:
        add(Alert("LOW_CASH_CONVERSION", "media", "Baja conversión de utilidad en caja",
                  f"Solo {cc:.0%} de la utilidad neta se convierte en flujo operativo.",
                  "cash_conversion", cc, f"< {T['cash_conversion_low']}"))
    if (_ok(ocf) and _ok(prev.get("operating_cash_flow")) and _ok(ni) and _ok(prev.get("net_income"))
            and ocf < prev["operating_cash_flow"] and ni > prev["net_income"]):
        add(Alert("EARNINGS_UP_CASH_DOWN", "media", "La utilidad sube pero el flujo operativo cae",
                  "Divergencia entre resultado contable y generación de caja frente al mismo "
                  "periodo del año anterior.", "operating_cash_flow", ocf,
                  "flujo operativo decreciente con utilidad creciente"))

    # --- Endeudamiento (no aplica a financieras) ---
    if not is_financial:
        ndte = kpis.get("net_debt_to_ebitda")
        if _ok(ndte) and ndte > T["net_debt_to_ebitda_high"]:
            add(Alert("HIGH_LEVERAGE", "alta", "Apalancamiento elevado",
                      f"La deuda neta equivale a {ndte:.1f} veces el EBITDA anualizado.",
                      "net_debt_to_ebitda", ndte, f"> {T['net_debt_to_ebitda_high']}"))
        ic = kpis.get("interest_coverage")
        if _ok(ic) and ic < T["interest_coverage_low"]:
            add(Alert("LOW_INTEREST_COVERAGE", "alta", "Cobertura de intereses baja",
                      f"La utilidad operativa cubre solo {ic:.1f} veces el gasto financiero.",
                      "interest_coverage", ic, f"< {T['interest_coverage_low']}"))
        debt_g = _growth(cur.get("total_debt"), prev.get("total_debt"))
        ebitda_cur, ebitda_prev = kpis.get("ebitda"), prev_kpis.get("ebitda")
        if (_ok(debt_g) and debt_g > T["debt_growth_high"] and _ok(ebitda_cur)
                and _ok(ebitda_prev) and ebitda_cur < ebitda_prev):
            add(Alert("DEBT_UP_EBITDA_DOWN", "alta", "Deuda creciente con EBITDA decreciente",
                      f"La deuda total creció {debt_g:.0%} mientras el EBITDA se redujo.",
                      "total_debt", debt_g, f"deuda > +{T['debt_growth_high']:.0%} y EBITDA a la baja"))

    eq = cur.get("total_equity")
    if _ok(eq) and eq < 0:
        add(Alert("NEGATIVE_EQUITY", "alta", "Patrimonio negativo",
                  "Los pasivos superan a los activos: situación patrimonial crítica.",
                  "total_equity", eq, "< 0"))

    # --- Crecimiento problemático ---
    rev_g = _growth(cur.get("revenue"), prev.get("revenue"))
    om_cur, om_prev = kpis.get("operating_margin"), prev_kpis.get("operating_margin")
    if _ok(rev_g) and rev_g > 0 and _ok(om_cur) and _ok(om_prev) and om_cur < om_prev - 0.005:
        add(Alert("GROWTH_MARGIN_DECLINE", "media", "Ingresos crecen pero el margen operativo cae",
                  f"Las ventas crecieron {rev_g:.0%} pero el margen operativo pasó de "
                  f"{om_prev:.1%} a {om_cur:.1%}.", "operating_margin", om_cur,
                  "margen operativo decreciente con ventas crecientes"))
    ar_g = _growth(cur.get("accounts_receivable"), prev.get("accounts_receivable"))
    if _ok(ar_g) and _ok(rev_g) and ar_g - rev_g >= T["receivables_vs_sales_gap"]:
        add(Alert("RECEIVABLES_OUTPACE_SALES", "media", "Cuentas por cobrar crecen mucho más que las ventas",
                  f"Las cuentas por cobrar crecieron {ar_g:.0%} frente a {rev_g:.0%} de las ventas; "
                  "posible relajamiento de cobranzas o ventas de baja calidad.",
                  "accounts_receivable", ar_g, f"brecha >= {T['receivables_vs_sales_gap']:.0%}"))
    inv_g = _growth(cur.get("inventory"), prev.get("inventory"))
    if _ok(inv_g) and _ok(rev_g) and inv_g - rev_g >= T["inventory_vs_sales_gap"]:
        add(Alert("INVENTORY_OUTPACE_SALES", "media", "Inventarios crecen mucho más que las ventas",
                  f"Los inventarios crecieron {inv_g:.0%} frente a {rev_g:.0%} de las ventas; "
                  "riesgo de sobrestock u obsolescencia.",
                  "inventory", inv_g, f"brecha >= {T['inventory_vs_sales_gap']:.0%}"))

    # --- Liquidez (no aplica a financieras) ---
    if not is_financial:
        cr = kpis.get("current_ratio")
        if _ok(cr) and cr < T["current_ratio_low"]:
            add(Alert("LOW_CURRENT_RATIO", "media", "Ratio corriente menor a 1",
                      "Los pasivos corrientes superan a los activos corrientes.",
                      "current_ratio", cr, "< 1"))
        wc = kpis.get("working_capital")
        if _ok(wc) and wc < 0 and not any(a.code == "LOW_CURRENT_RATIO" for a in alerts):
            add(Alert("NEGATIVE_WORKING_CAPITAL", "media", "Capital de trabajo negativo",
                      "El capital de trabajo es negativo.", "working_capital", wc, "< 0"))

        # --- Flujo de caja ---
        prev_fcf = prev_kpis.get("free_cash_flow")
        if _ok(fcf) and fcf < 0:
            if _ok(prev_fcf) and prev_fcf < 0:
                add(Alert("FCF_NEGATIVE_STREAK", "alta", "FCF negativo dos periodos consecutivos",
                          "El flujo de caja libre fue negativo en este periodo y en el mismo "
                          "periodo del año anterior.", "free_cash_flow", fcf, "< 0 en 2 periodos"))
            else:
                add(Alert("FCF_NEGATIVE", "media", "Flujo de caja libre negativo",
                          "La empresa no genera caja después de inversiones.",
                          "free_cash_flow", fcf, "< 0"))
        div = cur.get("dividends_paid")
        if _ok(div) and div > 0 and _ok(fcf) and abs(div) > max(fcf, 0):
            add(Alert("DIVIDENDS_EXCEED_FCF", "media", "Dividendos superiores al FCF",
                      "Los dividendos pagados exceden el flujo de caja libre generado; "
                      "se financian con deuda o caja acumulada.",
                      "dividend_coverage", kpis.get("dividend_coverage"), "dividendos > FCF"))
        capex, ocf_v = cur.get("capex"), cur.get("operating_cash_flow")
        if _ok(capex) and _ok(ocf_v) and ocf_v > 0 and abs(capex) > T["capex_vs_ocf_high"] * ocf_v:
            add(Alert("CAPEX_EXCEEDS_OCF", "baja", "CAPEX muy superior al flujo operativo",
                      f"Las inversiones ({abs(capex):,.0f}) superan {T['capex_vs_ocf_high']}x "
                      "el flujo operativo: fase de expansión intensiva o presión sobre la caja.",
                      "capex", abs(capex), f"> {T['capex_vs_ocf_high']}x flujo operativo"))

    return alerts


def _growth(cur, prev):
    if cur is None or prev is None or prev <= 0:
        return None
    return (cur - prev) / prev

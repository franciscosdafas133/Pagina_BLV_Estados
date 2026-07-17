"""Pruebas del motor de KPIs, semáforos, score y alertas."""
from app.kpis.alerts import evaluate_alerts
from app.kpis.engine import compute_kpis
from app.kpis.score import compute_score
from app.kpis.status import kpi_status, kpi_trend


def _base():
    return {
        "revenue": 1000, "cost_of_sales": -600, "gross_profit": 400,
        "operating_income": 200, "ebit": 200, "financial_expenses": -20,
        "income_before_tax": 180, "income_tax": 53, "net_income": 127,
        "net_income_attributable": 127, "depreciation_and_amortization": 50,
        "cash_and_equivalents": 300, "current_assets": 800, "total_assets": 3000,
        "accounts_receivable": 200, "inventory": 150, "current_liabilities": 500,
        "total_liabilities": 1000, "short_term_debt": 100, "long_term_debt": 400,
        "total_debt": 500, "total_equity": 2000, "equity_attributable": 2000,
        "operating_cash_flow": 250, "capex": 80, "dividends_paid": 40,
    }


def test_compute_kpis_completo_sin_nan():
    k = compute_kpis(_base(), None, None, "semester")
    for name, res in k.items():
        assert res.value is None or isinstance(res.value, (int, float))
    assert k["operating_margin"].value == 0.2
    assert k["free_cash_flow"].value == 170  # 250 - 80


def test_net_debt_to_ebitda_anualizado_en_semestre():
    k = compute_kpis(_base(), None, None, "semester")
    # net_debt = 500 - 300 = 200 ; ebitda semestre = 250, anualizado = 500
    assert k["net_debt_to_ebitda"].value == 0.4
    assert k["net_debt_to_ebitda"].estimated  # marcado por anualización


def test_crecimiento_mismo_semestre():
    cur = _base()
    prev = dict(_base(), revenue=800, net_income=100)
    k = compute_kpis(cur, None, prev, "semester")
    assert k["revenue_growth_yoy"].value == 0.25  # 1000 vs 800
    assert k["net_income_growth_yoy"].value == 0.27


def test_crecimiento_sin_previo_reporta_razon():
    k = compute_kpis(_base(), None, None, "semester")
    assert k["revenue_growth_yoy"].value is None
    assert "año anterior" in k["revenue_growth_yoy"].reason


# --- Semáforos ---
def test_status_roic():
    assert kpi_status("roic", 0.15) == "good"
    assert kpi_status("roic", 0.10) == "medium"
    assert kpi_status("roic", 0.05) == "risky"


def test_status_net_debt_to_ebitda_menor_es_mejor():
    assert kpi_status("net_debt_to_ebitda", 1.0) == "good"
    assert kpi_status("net_debt_to_ebitda", 2.0) == "medium"
    assert kpi_status("net_debt_to_ebitda", 4.0) == "risky"


def test_status_current_ratio_rango():
    assert kpi_status("current_ratio", 1.5) == "good"
    assert kpi_status("current_ratio", 1.1) == "medium"
    assert kpi_status("current_ratio", 0.9) == "risky"


def test_status_no_aplica_a_financieras_para_deuda():
    assert kpi_status("net_debt_to_ebitda", 4.0, is_financial=True) is None


def test_trend_direccion():
    assert kpi_trend("roe", 0.20, 0.15) == "improving"
    assert kpi_trend("roe", 0.15, 0.15) == "stable"
    assert kpi_trend("roe", 0.10, 0.15) == "worsening"
    # deuda: bajar es mejorar
    assert kpi_trend("net_debt_to_ebitda", 1.0, 2.0) == "improving"


def test_trend_sin_previo_es_none():
    assert kpi_trend("roe", 0.2, None) is None


# --- Alertas ---
def test_alerta_utilidad_positiva_flujo_negativo():
    cur = dict(_base(), net_income=100, operating_cash_flow=-50)
    k = {kk: r.value for kk, r in compute_kpis(cur, None, None, "semester").items()}
    alerts = evaluate_alerts(cur, k)
    assert any(a.code == "EARNINGS_NO_CASH" for a in alerts)


def test_alerta_patrimonio_negativo():
    cur = dict(_base(), total_equity=-100)
    k = {kk: r.value for kk, r in compute_kpis(cur, None, None, "semester").items()}
    alerts = evaluate_alerts(cur, k)
    assert any(a.code == "NEGATIVE_EQUITY" and a.severity == "alta" for a in alerts)


def test_alerta_apalancamiento_alto():
    # net_debt alto y ebitda bajo -> ndte > 3
    cur = dict(_base(), total_debt=5000, cash_and_equivalents=100,
               depreciation_and_amortization=10, operating_income=100, ebit=100)
    k = {kk: r.value for kk, r in compute_kpis(cur, None, None, "semester").items()}
    alerts = evaluate_alerts(cur, k)
    assert any(a.code == "HIGH_LEVERAGE" for a in alerts)


def test_alertas_deuda_no_aplican_a_financieras():
    cur = dict(_base(), total_debt=5000, cash_and_equivalents=100, ebit=50,
               depreciation_and_amortization=5)
    k = {kk: r.value for kk, r in compute_kpis(cur, None, None, "semester").items()}
    alerts = evaluate_alerts(cur, k, is_financial=True)
    assert not any(a.code == "HIGH_LEVERAGE" for a in alerts)


def test_alerta_cuentas_por_cobrar_supera_ventas():
    cur = dict(_base(), revenue=1100, accounts_receivable=300)
    prev = dict(_base(), revenue=1000, accounts_receivable=200)  # AR +50% vs ventas +10%
    k = {kk: r.value for kk, r in compute_kpis(cur, None, prev, "semester").items()}
    alerts = evaluate_alerts(cur, k, prev)
    assert any(a.code == "RECEIVABLES_OUTPACE_SALES" for a in alerts)


# --- Score ---
def test_score_empresa_solida_alto():
    values = {
        "roic": 0.16, "roe": 0.20, "operating_margin_percentile": 80,
        "operating_margin_change": 0.02, "free_cash_flow": 170,
        "cash_conversion": 1.2, "fcf_margin": 0.15, "fcf_growth_yoy": 0.1,
        "net_debt_to_ebitda": 0.5, "interest_coverage": 10, "current_ratio": 1.5,
        "total_equity": 2000, "revenue_growth_yoy": 0.12,
        "operating_income_growth_yoy": 0.15, "net_income_growth_yoy": 0.15,
    }
    s = compute_score(values, alerts_high=0, positive_streak=4, data_completeness=0.95)
    assert s.score is not None and s.score >= 70
    assert s.confidence == "alta"


def test_score_pocos_datos_no_emite_puntuacion():
    s = compute_score({"roic": 0.1}, data_completeness=0.1)
    assert s.score is None
    assert s.confidence == "baja"


def test_score_reporta_kpis_faltantes():
    values = {"roic": 0.16, "roe": 0.20, "free_cash_flow": 100,
              "cash_conversion": 1.1, "current_ratio": 1.5, "total_equity": 2000,
              "revenue_growth_yoy": 0.1}
    s = compute_score(values, data_completeness=0.6)
    assert "interest_coverage" in s.kpis_missing

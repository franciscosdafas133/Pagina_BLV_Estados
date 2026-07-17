"""Pruebas unitarias de las fórmulas puras de KPIs.

Cubre los casos obligatorios: denominador cero, nulls, utilidad negativa,
EBITDA negativo, deuda neta negativa, patrimonio negativo, CAPEX negativo,
primer periodo sin comparación.
"""
import math

import pytest

from app.kpis import formulas as F


# --- Márgenes y división segura ---
def test_gross_margin_basico():
    assert F.gross_margin(300, 1000) == 0.3


def test_margen_denominador_cero_es_none():
    assert F.operating_margin(100, 0) is None


def test_margen_con_null_es_none():
    assert F.net_margin(None, 1000) is None
    assert F.gross_margin(300, None) is None


def test_safe_div_no_devuelve_infinito():
    assert F.safe_div(1, 0) is None
    assert F.safe_div(0, 0) is None
    r = F.safe_div(1e308, 1e-308)
    assert r is None or math.isfinite(r)


# --- ROA / ROE ---
def test_roa_usa_promedio_de_activos():
    r = F.roa(100, 2000, 1800)
    assert r.value == pytest.approx(100 / 1900)
    assert not r.estimated


def test_roa_sin_periodo_previo_es_estimado():
    r = F.roa(100, 2000, None)
    assert r.value == pytest.approx(0.05)
    assert r.estimated


def test_roe_patrimonio_negativo_no_significativo():
    r = F.roe(100, -500, -400)
    assert r.value is None
    assert "Patrimonio" in r.reason


# --- Tasa efectiva y ROIC ---
def test_effective_tax_rate_normal():
    r = F.effective_tax_rate(295, 1000)
    assert r.value == pytest.approx(0.295)
    assert not r.estimated


def test_effective_tax_rate_base_negativa_usa_estatutaria():
    r = F.effective_tax_rate(50, -100)
    assert r.value == pytest.approx(0.295)
    assert r.estimated


def test_effective_tax_rate_anomala_se_acota():
    r = F.effective_tax_rate(900, 1000)  # 90% -> anómala
    assert r.value == pytest.approx(0.295)
    assert r.estimated


def test_roic_calculo_completo():
    r = F.roic(ebit=1000, income_tax=295, income_before_tax=1000,
               equity_cur=3000, debt_cur=2000, cash_cur=500,
               equity_prev=2800, debt_prev=2100, cash_prev=400)
    # NOPAT = 1000 * (1 - 0.295) = 705
    # IC_cur = 3000+2000-500 = 4500 ; IC_prev = 2800+2100-400 = 4500 ; prom 4500
    assert r.value == pytest.approx(705 / 4500)
    assert not r.estimated


def test_roic_sin_periodo_previo_es_estimado():
    r = F.roic(1000, 295, 1000, 3000, 2000, 500)
    assert r.estimated
    assert r.value is not None


def test_roic_capital_invertido_negativo_no_significativo():
    r = F.roic(1000, 295, 1000, equity_cur=100, debt_cur=0, cash_cur=5000)
    assert r.value is None


def test_roic_sin_ebit_es_none():
    r = F.roic(None, 295, 1000, 3000, 2000, 500)
    assert r.value is None


# --- Crecimiento ---
def test_growth_yoy_normal():
    assert F.growth_yoy(120, 100) == pytest.approx(0.2)


def test_growth_yoy_sin_previo_es_none():
    assert F.growth_yoy(120, None) is None


def test_growth_yoy_base_cero_es_none():
    assert F.growth_yoy(120, 0) is None


def test_growth_yoy_base_negativa_no_comparable():
    assert F.growth_yoy(50, -100) is None


def test_cagr_valores_positivos():
    assert F.cagr(200, 100, 3) == pytest.approx(2 ** (1 / 3) - 1)


def test_cagr_con_inicial_no_positivo_es_none():
    assert F.cagr(200, 0, 3) is None
    assert F.cagr(200, -50, 3) is None


# --- Flujo de caja ---
def test_fcf_capex_positivo():
    assert F.free_cash_flow(500, 200) == 300


def test_fcf_capex_negativo_no_se_resta_dos_veces():
    # CAPEX almacenado como negativo: abs() evita restar dos veces
    assert F.free_cash_flow(500, -200) == 300


def test_fcf_con_null_es_none():
    assert F.free_cash_flow(500, None) is None
    assert F.free_cash_flow(None, 200) is None


def test_cash_conversion_utilidad_negativa_es_none():
    assert F.cash_conversion(300, -100) is None


def test_cash_conversion_normal():
    assert F.cash_conversion(300, 200) == pytest.approx(1.5)


def test_dividend_coverage_sin_dividendos_no_aplica():
    r = F.dividend_coverage(300, 0)
    assert r.value is None
    assert "No aplica" in r.reason


# --- Endeudamiento ---
def test_net_debt_negativa_valida():
    # más caja que deuda: deuda neta negativa es un resultado válido
    assert F.net_debt(500, 800) == -300


def test_ebitda_aproximado_marcado_estimado():
    r = F.ebitda(1000, 200)
    assert r.value == 1200
    assert r.estimated


def test_ebitda_sin_dya_no_se_inventa():
    r = F.ebitda(1000, None)
    assert r.value is None


def test_net_debt_to_ebitda_negativo_no_significativo():
    r = F.net_debt_to_ebitda(300, -100)
    assert r.value is None
    assert "significativo" in r.reason.lower()


def test_net_debt_to_ebitda_normal():
    r = F.net_debt_to_ebitda(300, 200)
    assert r.value == pytest.approx(1.5)


def test_interest_coverage_gasto_cero_no_infinito():
    r = F.interest_coverage(1000, 0)
    assert r.value is None


def test_interest_coverage_usa_magnitud_del_gasto():
    r = F.interest_coverage(1000, -200)
    assert r.value == pytest.approx(5.0)


def test_debt_to_equity_patrimonio_negativo_es_none():
    assert F.debt_to_equity(1000, -200) is None


# --- Liquidez ---
def test_current_ratio_normal():
    assert F.current_ratio(1500, 1000) == 1.5


def test_current_ratio_denominador_cero():
    assert F.current_ratio(1500, 0) is None


def test_quick_ratio_excluye_inventario():
    assert F.quick_ratio(1500, 500, 1000) == 1.0


def test_working_capital_negativo():
    assert F.working_capital(800, 1000) == -200


# --- Eficiencia ---
def test_days_sales_outstanding_semestre():
    r = F.days_sales_outstanding(100, 100, 1000, 182)
    assert r == pytest.approx(100 / 1000 * 182)


def test_days_inventory_usa_costo_positivo():
    r = F.days_inventory(200, 200, -1000, 365)  # costo negativo -> magnitud
    assert r == pytest.approx(200 / 1000 * 365)

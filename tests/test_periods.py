"""Pruebas de la capa de normalización de periodos.

Verifica que S2 se deriva por diferencia de acumulados (no por suma) y que el
balance se toma como foto al cierre.
"""
from app.periods import build_period, semester_of_quarter


def test_semester_of_quarter():
    assert semester_of_quarter(1) == 1
    assert semester_of_quarter(2) == 1
    assert semester_of_quarter(3) == 2
    assert semester_of_quarter(4) == 2


def test_s1_toma_acumulado_q2():
    q2 = {"revenue": 500, "total_assets": 3000, "operating_cash_flow": 120}
    pd = build_period(2025, "s1", q2_ytd=q2, q4_ytd={"revenue": 1100})
    assert pd.semester == 1
    assert pd.period_type == "semester"
    assert pd.fields["revenue"] == 500
    assert not pd.is_derived


def test_s2_es_diferencia_de_acumulados():
    # Flujos acumulados: Q2=500, Q4=1100 -> S2 = 600 (no se suma dos veces)
    q2 = {"revenue": 500, "net_income": 80, "total_assets": 3000, "total_equity": 2000}
    q4 = {"revenue": 1100, "net_income": 180, "total_assets": 3400, "total_equity": 2100}
    pd = build_period(2025, "s2", q2_ytd=q2, q4_ytd=q4)
    assert pd.semester == 2
    assert pd.fields["revenue"] == 600      # 1100 - 500 (flujo)
    assert pd.fields["net_income"] == 100   # 180 - 80
    assert pd.fields["total_assets"] == 3400  # balance = foto al cierre
    assert pd.fields["total_equity"] == 2100
    assert pd.is_derived


def test_s2_sin_q2_no_puede_aislar_flujos():
    q4 = {"revenue": 1100, "total_assets": 3400}
    pd = build_period(2025, "s2", q2_ytd=None, q4_ytd=q4)
    assert pd.fields["revenue"] is None       # sin Q2 no se aísla el flujo
    assert pd.fields["total_assets"] == 3400  # el balance sí


def test_annual_usa_acumulado_completo():
    q4 = {"revenue": 1100, "total_assets": 3400}
    pd = build_period(2025, "annual", q4_ytd=q4)
    assert pd.semester is None
    assert pd.period_type == "annual"
    assert pd.fields["revenue"] == 1100


def test_ttm_combina_semestres():
    prev_annual = {"revenue": 1000, "total_assets": 3000}
    prev_q2 = {"revenue": 450, "total_assets": 2800}
    cur_q2 = {"revenue": 520, "total_assets": 3100}
    pd = build_period(2025, "ttm", q2_ytd=cur_q2, prev_annual=prev_annual, prev_q2_ytd=prev_q2)
    # TTM = (1000 - 450) + 520 = 1070
    assert pd.fields["revenue"] == 1070
    assert pd.fields["total_assets"] == 3100  # balance = último cierre (junio actual)
    assert pd.period_type == "ttm"


def test_periodo_sin_insumos_devuelve_none():
    assert build_period(2025, "s1", q2_ytd=None) is None
    assert build_period(2025, "annual", q4_ytd=None, annual=None) is None

"""Pruebas del mapeo de cuentas SMV y del parser numérico del scraper."""
from app.smv.account_mapping import derive_fields, map_accounts, normalize_text
from app.smv.scraper import _parse_number
from app.smv.sectors_seed import classify_company


def test_normalize_text_sin_tildes_minusculas():
    assert normalize_text("Compañía  ELÉCTRICA") == "compania electrica"


def test_map_income_statement():
    rows = [
        ("Ingresos de actividades ordinarias", 1000),
        ("Costo de ventas", -600),
        ("Ganancia (Perdida) Operativa", 200),
        ("Gastos Financieros", -20),
    ]
    out = map_accounts("income", rows)
    assert out["revenue"] == 1000
    assert out["cost_of_sales"] == -600
    assert out["operating_income"] == 200


def test_map_respeta_prioridad_de_alias():
    rows = [("Total activos", 5000), ("Total de activos", 5001)]
    out = map_accounts("balance", rows)
    # "total de activos" tiene mayor prioridad en el mapeo
    assert out["total_assets"] == 5001


def test_derive_gross_profit_y_total_debt():
    f = derive_fields({"revenue": 1000, "cost_of_sales": -600,
                       "short_term_debt": 100, "long_term_debt": 400})
    assert f["gross_profit"] == 400
    assert f["total_debt"] == 500


def test_derive_capex_normaliza_signo():
    f = derive_fields({"capex": -80})
    assert f["capex"] == 80


def test_derive_ebit_desde_operating_income():
    f = derive_fields({"operating_income": 200})
    assert f["ebit"] == 200


def test_parse_number_formatos():
    assert _parse_number("1,234") == 1234
    assert _parse_number("(1,234)") == -1234
    assert _parse_number("-1,234.5") == -1234.5
    assert _parse_number("") is None
    assert _parse_number("-") is None
    assert _parse_number("0") == 0


def test_clasificacion_sectorial():
    assert classify_company("AENZA S.A.A.")[0] == "Construcción e ingeniería"
    sector, fin = classify_company("BANCO DE CREDITO DEL PERU")
    assert fin is True
    sector, fin = classify_company("MINSUR S.A.")
    assert sector == "Minería" and fin is False
    sector, fin = classify_company("AFP INTEGRA")
    assert fin is True

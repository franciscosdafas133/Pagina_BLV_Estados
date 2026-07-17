"""Pruebas del parser XBRL con una instancia sintética mínima (estilo SMV)."""
from app.smv.xbrl import parse_xbrl, prev_year_balance

XBRL = """<?xml version="1.0" encoding="utf-8"?>
<xbrli:xbrl xmlns:xbrli="http://www.xbrl.org/2003/instance"
  xmlns:ifrs-full="http://xbrl.ifrs.org/taxonomy/2015-03-11/ifrs-full"
  xmlns:smv="http://www.smv.gob.pe/2016-01-27/smv"
  xmlns:iso4217="http://www.xbrl.org/2003/iso4217">
  <xbrli:context id="dYTD"><xbrli:period>
    <xbrli:startDate>2024-01-01</xbrli:startDate><xbrli:endDate>2024-06-30</xbrli:endDate>
  </xbrli:period></xbrli:context>
  <xbrli:context id="dQ"><xbrli:period>
    <xbrli:startDate>2024-04-01</xbrli:startDate><xbrli:endDate>2024-06-30</xbrli:endDate>
  </xbrli:period></xbrli:context>
  <xbrli:context id="iClose"><xbrli:period>
    <xbrli:instant>2024-06-30</xbrli:instant></xbrli:period></xbrli:context>
  <xbrli:context id="iPrev"><xbrli:period>
    <xbrli:instant>2023-12-31</xbrli:instant></xbrli:period></xbrli:context>
  <xbrli:context id="dDim"><xbrli:period>
    <xbrli:startDate>2024-01-01</xbrli:startDate><xbrli:endDate>2024-06-30</xbrli:endDate>
  </xbrli:period><xbrli:entity><xbrli:segment>
    <xbrldi:explicitMember>seg</xbrldi:explicitMember></xbrli:segment></xbrli:entity></xbrli:context>

  <smv:RegistroUnicoDeContribuyente contextRef="dYTD">20332600592</smv:RegistroUnicoDeContribuyente>
  <smv:ClasificacionIndustrialInternacionalUniforme contextRef="dYTD">6719</smv:ClasificacionIndustrialInternacionalUniforme>

  <ifrs-full:Revenue contextRef="dYTD" unitRef="PEN">11767000</ifrs-full:Revenue>
  <ifrs-full:Revenue contextRef="dQ" unitRef="PEN">5819000</ifrs-full:Revenue>
  <ifrs-full:ProfitLossFromOperatingActivities contextRef="dYTD">-7337000</ifrs-full:ProfitLossFromOperatingActivities>
  <ifrs-full:ProfitLoss contextRef="dYTD">-67950000</ifrs-full:ProfitLoss>
  <ifrs-full:CashFlowsFromUsedInOperatingActivities contextRef="dYTD">-206869000</ifrs-full:CashFlowsFromUsedInOperatingActivities>
  <ifrs-full:Assets contextRef="iClose">2661442000</ifrs-full:Assets>
  <ifrs-full:Assets contextRef="iPrev">2418885000</ifrs-full:Assets>
  <ifrs-full:Equity contextRef="iClose">1190593000</ifrs-full:Equity>
  <ifrs-full:Equity contextRef="iPrev">1263107000</ifrs-full:Equity>
  <ifrs-full:CurrentAssets contextRef="iClose">570009000</ifrs-full:CurrentAssets>
</xbrli:xbrl>
"""


def test_parse_xbrl_periodo_y_meta():
    xb = parse_xbrl(XBRL)
    assert xb.year == 2024
    assert xb.period_start == "2024-01-01"
    assert xb.period_end == "2024-06-30"
    assert xb.ruc == "20332600592"
    assert xb.ciiu == "6719"


def test_flujos_toman_contexto_ytd_no_trimestre():
    xb = parse_xbrl(XBRL)
    # Revenue YTD = 11767000 en soles -> 11767 en miles (no el del trimestre 5819)
    assert xb.fields["revenue"] == 11767.0
    assert xb.fields["operating_income"] == -7337.0


def test_balance_toma_contexto_de_cierre():
    xb = parse_xbrl(XBRL)
    assert xb.fields["total_assets"] == 2661442.0   # cierre 2024-06-30, en miles
    assert xb.fields["current_assets"] == 570009.0


def test_escala_a_miles():
    xb = parse_xbrl(XBRL)
    # todas las cifras monetarias divididas entre 1000
    assert xb.fields["net_income"] == -67950.0
    assert xb.fields["operating_cash_flow"] == -206869.0


def test_ignora_contextos_dimensionales():
    # el hecho en 'dDim' no debe usarse; solo hechos sin dimensiones
    xb = parse_xbrl(XBRL)
    assert xb.fields["revenue"] == 11767.0


def test_balance_del_anio_anterior():
    prev = prev_year_balance(XBRL)
    assert prev["total_assets"] == 2418885.0   # cierre 2023-12-31, en miles
    assert prev["total_equity"] == 1263107.0


# Caso Gloria: total de pasivos reportado como 0 + deuda como *FinancialLiabilities
XBRL_GLORIA = """<?xml version="1.0"?>
<xbrli:xbrl xmlns:xbrli="http://www.xbrl.org/2003/instance"
  xmlns:ifrs-full="http://xbrl.ifrs.org/taxonomy/2015-03-11/ifrs-full">
  <xbrli:context id="i"><xbrli:period><xbrli:instant>2024-12-31</xbrli:instant></xbrli:period></xbrli:context>
  <ifrs-full:Liabilities contextRef="i">0</ifrs-full:Liabilities>
  <ifrs-full:CurrentLiabilities contextRef="i">1018035000</ifrs-full:CurrentLiabilities>
  <ifrs-full:NoncurrentLiabilities contextRef="i">1434437000</ifrs-full:NoncurrentLiabilities>
  <ifrs-full:OtherCurrentFinancialLiabilities contextRef="i">0</ifrs-full:OtherCurrentFinancialLiabilities>
  <ifrs-full:OtherNoncurrentFinancialLiabilities contextRef="i">1267500000</ifrs-full:OtherNoncurrentFinancialLiabilities>
  <ifrs-full:Equity contextRef="i">1623368000</ifrs-full:Equity>
</xbrli:xbrl>
"""


def test_total_pasivos_derivado_cuando_viene_cero():
    xb = parse_xbrl(XBRL_GLORIA)
    # Liabilities=0 pero corriente+no corriente sí -> se deriva el total
    assert xb.fields["total_liabilities"] == 1018035.0 + 1434437.0
    # apalancamiento total = 2452472 / 1623368 = 1.5107 (coincide con la BVL)
    ratio = xb.fields["total_liabilities"] / xb.fields["total_equity"]
    assert round(ratio, 4) == 1.5107


def test_deuda_desde_financial_liabilities():
    from app.smv.account_mapping import derive_fields
    xb = parse_xbrl(XBRL_GLORIA)
    f = derive_fields(xb.fields)
    assert f["long_term_debt"] == 1267500.0
    assert f["total_debt"] == 1267500.0  # sin deuda corriente (0)

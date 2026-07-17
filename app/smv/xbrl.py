"""Parser del XBRL de la SMV (taxonomía IFRS 2015 + extensión smv).

La SMV publica cada estado financiero como un archivo XBRL estructurado
(ifrs-full:*). Es la fuente preferida sobre el HTML: los conceptos son
estándar y las cifras no requieren heurística de parseo.

Estructura observada (filing intermedio, p.ej. AENZA Q2-2024):
  - Contextos de DURACIÓN acumulada (YTD): 2024-01-01..2024-06-30 -> flujos S1.
  - Contexto de duración solo-trimestre: 2024-04-01..2024-06-30 (se ignora).
  - Contextos INSTANTÁNEOS: balance al 2024-06-30 y al 2023-12-31.
  - Comparativos del año anterior en sus propios contextos (se ignoran aquí;
    el crecimiento interanual se calcula a nivel de KPIs entre filings).

Se selecciona, para las cifras de FLUJO, el contexto de duración cuyo rango
va del 1 de enero al cierre del periodo (YTD); para el BALANCE, el contexto
instantáneo en la fecha de cierre. Solo se toman hechos SIN dimensiones
(consolidado total), evitando desgloses por segmento/clase de acción.
"""
import re
from dataclasses import dataclass


@dataclass
class XBRLFacts:
    fields: dict           # campo interno -> valor (en unidades absolutas)
    year: int
    period_end: str        # yyyy-mm-dd (cierre del periodo)
    period_start: str      # yyyy-mm-dd (inicio del acumulado)
    currency: str | None
    is_consolidated: bool | None
    ruc: str | None
    ciiu: str | None
    unit_scale: int = 1    # el XBRL viene en unidades (soles), no en miles


# concepto ifrs-full -> campo interno (primer concepto presente gana)
CONCEPT_MAP = {
    "revenue": ["Revenue", "RevenueFromContractsWithCustomers"],
    "cost_of_sales": ["CostOfSales"],
    "gross_profit": ["GrossProfit"],
    "operating_income": ["ProfitLossFromOperatingActivities"],
    "financial_expenses": ["FinanceCosts"],
    "income_before_tax": ["ProfitLossBeforeTax"],
    "income_tax": ["IncomeTaxExpenseContinuingOperations"],
    "net_income": ["ProfitLoss"],
    "net_income_attributable": ["ProfitLossAttributableToOwnersOfParent"],
    "depreciation_and_amortization": [
        "DepreciationAndAmortisationExpense",
        "DepreciationAmortisationAndImpairmentLossReversalOfImpairmentLossRecognisedInProfitOrLoss",
    ],
    # Balance
    "cash_and_equivalents": ["CashAndCashEquivalents"],
    "current_assets": ["CurrentAssets"],
    "total_assets": ["Assets"],
    "accounts_receivable": ["TradeAndOtherCurrentReceivables", "CurrentTradeReceivables"],
    "inventory": ["Inventories"],
    "current_liabilities": ["CurrentLiabilities"],
    "noncurrent_liabilities": ["NoncurrentLiabilities"],  # auxiliar para derivar el total
    "total_liabilities": ["Liabilities"],
    "short_term_debt": ["CurrentPortionOfNoncurrentBorrowings", "ShorttermBorrowings",
                        "CurrentBorrowings", "OtherCurrentFinancialLiabilities"],
    "long_term_debt": ["NoncurrentPortionOfNoncurrentBorrowings", "NoncurrentBorrowings",
                      "LongtermBorrowings", "OtherNoncurrentFinancialLiabilities"],
    "total_equity": ["Equity"],
    "equity_attributable": ["EquityAttributableToOwnersOfParent"],
    # Flujo de efectivo
    "operating_cash_flow": ["CashFlowsFromUsedInOperatingActivities"],
    "investing_cash_flow": ["CashFlowsFromUsedInInvestingActivities"],
    "financing_cash_flow": ["CashFlowsFromUsedInFinancingActivities"],
    "capex": ["PurchaseOfPropertyPlantAndEquipmentClassifiedAsInvestingActivities",
              "PurchaseOfPropertyPlantAndEquipment"],
    "dividends_paid": ["DividendsPaidClassifiedAsFinancingActivities", "DividendsPaid"],
    "interest_paid": ["InterestPaidClassifiedAsOperatingActivities",
                      "InterestPaidClassifiedAsFinancingActivities", "InterestPaid"],
    "shares_outstanding": ["NumberOfSharesOutstanding"],
}

# Conceptos que son de FLUJO (contexto de duración YTD). El resto = balance (instant).
FLOW_CONCEPTS = {
    "revenue", "cost_of_sales", "gross_profit", "operating_income",
    "financial_expenses", "income_before_tax", "income_tax", "net_income",
    "net_income_attributable", "depreciation_and_amortization",
    "operating_cash_flow", "investing_cash_flow", "financing_cash_flow",
    "capex", "dividends_paid", "interest_paid",
}

_CTX = re.compile(r'<xbrli:context id="([^"]+)"[^>]*>(.*?)</xbrli:context>', re.S)


def _parse_contexts(xml: str):
    """Devuelve (duration_ytd_ctx, instant_close_ctx, instant_prev_ctx, meta).

    duration_ytd: contexto sin dimensiones que va del inicio de año al cierre.
    instant_close: contexto instantáneo (sin dims) en la fecha de cierre.
    instant_prev: contexto instantáneo (sin dims) del cierre del año anterior.
    """
    durations = {}   # (start,end) -> id  (solo sin dimensiones)
    instants = {}    # date -> id
    for m in _CTX.finditer(xml):
        cid, body = m.group(1), m.group(2)
        if "xbrldi:explicitMember" in body or "dimension=" in body:
            continue  # ignorar desgloses dimensionales
        inst = re.search(r"<xbrli:instant>([^<]+)", body)
        if inst:
            instants[inst.group(1).strip()] = cid
            continue
        sd = re.search(r"<xbrli:startDate>([^<]+)", body)
        ed = re.search(r"<xbrli:endDate>([^<]+)", body)
        if sd and ed:
            durations[(sd.group(1).strip(), ed.group(1).strip())] = cid

    # duración YTD: la que empieza el 1 de enero y termina más tarde
    ytd = None
    for (s, e), cid in durations.items():
        if s.endswith("-01-01"):
            if ytd is None or e > ytd[0]:
                ytd = (e, s, cid)
    close_date = ytd[0] if ytd else (max(instants) if instants else None)

    instant_close = instants.get(close_date)
    prev_dates = sorted(d for d in instants if d < (close_date or "9999"))
    instant_prev = instants.get(prev_dates[-1]) if prev_dates else None
    return (ytd[2] if ytd else None), instant_close, instant_prev, (ytd[1] if ytd else None), close_date


def _facts_by_context(xml: str) -> dict:
    """(concepto_local, contextRef) -> valor float. Solo hechos numéricos."""
    out = {}
    for m in re.finditer(
        r'<ifrs-full:([A-Za-z]+)[^>]*\bcontextRef="([^"]+)"[^>]*>(-?\d+(?:\.\d+)?)</ifrs-full:\1>', xml):
        out[(m.group(1), m.group(2))] = float(m.group(3))
    return out


def parse_xbrl(xml: str) -> XBRLFacts:
    ytd_ctx, close_ctx, prev_ctx, start_date, close_date = _parse_contexts(xml)
    facts = _facts_by_context(xml)
    year = int(close_date[:4]) if close_date else 0

    currency = None
    mcur = re.search(r"iso4217:(\w{3})", xml)
    if mcur:
        currency = mcur.group(1).upper()
    ruc = _smv_value(xml, "RegistroUnicoDeContribuyente")
    ciiu = _smv_value(xml, "ClasificacionIndustrialInternacionalUniforme")
    # El XBRL de la SMV no siempre marca el tipo de estado. Señal fiable:
    # si el patrimonio atribuible a la matriz difiere del patrimonio total,
    # hay participación no controladora -> estado consolidado. Si son iguales
    # (o no hay atribuible), se asume consolidado por defecto salvo mención
    # explícita de estado "individual"/"separado" en la cabecera del informe.
    consolidated = True
    hdr = _report_header(xml).lower()
    if "individual" in hdr or "separado" in hdr:
        consolidated = False

    # El XBRL reporta en unidades (soles). El resto del sistema trabaja en
    # miles (como el resto de reportes SMV), así que se normaliza dividiendo /1000.
    fields = {}
    for field, concepts in CONCEPT_MAP.items():
        ctx = ytd_ctx if field in FLOW_CONCEPTS else close_ctx
        if not ctx:
            continue
        for concept in concepts:
            if (concept, ctx) in facts:
                v = facts[(concept, ctx)]
                fields[field] = v if field == "shares_outstanding" else v / 1000.0
                break

    _fix_totals(fields)
    return XBRLFacts(fields=fields, year=year, period_end=close_date,
                     period_start=start_date, currency=currency,
                     is_consolidated=consolidated, ruc=ruc, ciiu=ciiu)


def _fix_totals(fields: dict) -> None:
    """La SMV a veces reporta el total de pasivos como 0 aunque haya corriente y
    no corriente. Se deriva total_liabilities = corriente + no corriente en ese
    caso. El campo auxiliar noncurrent_liabilities no pertenece al modelo y se
    descarta tras usarlo."""
    cur = fields.get("current_liabilities")
    non = fields.pop("noncurrent_liabilities", None)
    total = fields.get("total_liabilities")
    if (total is None or total == 0) and (cur is not None or non is not None):
        fields["total_liabilities"] = (cur or 0) + (non or 0)


def _report_header(xml: str) -> str:
    m = re.search(r"<smv:InformacionSobreElInforme[^>]*>(.*?)</smv:InformacionSobreElInforme>",
                  xml, re.S)
    return m.group(1) if m else ""


def _smv_value(xml: str, concept: str) -> str | None:
    m = re.search(r"<smv:" + concept + r"[^>]*>([^<]+)</smv:" + concept + ">", xml)
    return m.group(1).strip() if m else None


def prev_year_balance(xml: str) -> dict:
    """Balance del cierre del año anterior (comparativo del propio filing).

    Sirve como periodo previo para promedios (activos/patrimonio/capital) sin
    tener que descargar otro filing.
    """
    _, _, prev_ctx, _, _ = _parse_contexts(xml)
    if not prev_ctx:
        return {}
    facts = _facts_by_context(xml)
    out = {}
    for field, concepts in CONCEPT_MAP.items():
        if field in FLOW_CONCEPTS:
            continue
        for concept in concepts:
            if (concept, prev_ctx) in facts:
                v = facts[(concept, prev_ctx)]
                out[field] = v if field == "shares_outstanding" else v / 1000.0
                break
    return out

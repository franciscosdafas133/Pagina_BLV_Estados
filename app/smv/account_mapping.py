"""Mapeo de cuentas de la SMV (plan contable NIIF en español) a campos internos.

Los estados de la SMV usan la taxonomía XBRL de la SMV/IFRS con descripciones
en español. El mapeo es por descripción normalizada (sin tildes, minúsculas,
espacios colapsados). Cada campo interno lista sus posibles denominaciones,
ordenadas por prioridad: se usa la primera que aparezca en el estado.

Si una cuenta no aparece, el campo queda en None ("No disponible"); nunca en 0.
"""
import re
import unicodedata


def normalize_text(text: str) -> str:
    """minúsculas + sin tildes + espacios colapsados (clave del mapeo y del buscador)."""
    text = unicodedata.normalize("NFKD", text or "")
    text = "".join(c for c in text if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", text).strip().lower()


# --- Estado de resultados ---------------------------------------------------
INCOME_STATEMENT_MAP = {
    "revenue": [
        "ingresos de actividades ordinarias",
        "total de ingresos de actividades ordinarias",
        "total ingresos brutos",
        "ventas netas (ingresos operacionales)",
        "ingresos por intereses",  # bancos: cartera de créditos
        "total ingresos",
    ],
    "cost_of_sales": [
        "costo de ventas",
        "costo de ventas (operacionales)",
        "gastos por intereses",  # bancos
    ],
    "gross_profit": [
        "ganancia (perdida) bruta",
        "utilidad bruta",
        "margen financiero bruto",  # bancos
    ],
    "operating_income": [
        "ganancia (perdida) operativa",
        "ganancia (perdida) por actividades de operacion",
        "utilidad operativa",
        "resultado de operacion",
        "margen operacional",
    ],
    "financial_expenses": [
        "gastos financieros",
        "costos financieros",
    ],
    "income_before_tax": [
        "ganancia (perdida) antes de impuestos",
        "resultado antes de impuesto a las ganancias",
        "utilidad (perdida) antes de impuesto a la renta",
        "resultado antes del impuesto a la renta",
    ],
    "income_tax": [
        "ingreso (gasto) por impuesto",
        "gasto por impuesto a las ganancias",
        "impuesto a la renta",
        "participacion de los trabajadores e impuesto a la renta",
    ],
    "net_income": [
        "ganancia (perdida) neta del ejercicio",
        "utilidad (perdida) neta del ejercicio",
        "resultado neto del ejercicio",
    ],
    "net_income_attributable": [
        "ganancia (perdida) neta atribuible a propietarios de la controladora",
        "atribuible a: propietarios de la controladora",
        "utilidad neta atribuible a la matriz",
    ],
    "depreciation_and_amortization": [
        "depreciacion y amortizacion",
        "gasto por depreciacion y amortizacion",
        "depreciacion de activos fijos y amortizacion de intangibles",
    ],
}

# --- Balance general ---------------------------------------------------------
BALANCE_SHEET_MAP = {
    "cash_and_equivalents": [
        "efectivo y equivalentes al efectivo",
        "efectivo y equivalentes de efectivo",
        "caja y bancos",
        "fondos disponibles",  # bancos
        "disponible",
    ],
    "current_assets": [
        "total activos corrientes",
        "total activo corriente",
    ],
    "total_assets": [
        "total de activos",
        "total activos",
        "total activo",
    ],
    "accounts_receivable": [
        "cuentas por cobrar comerciales",
        "cuentas por cobrar comerciales y otras cuentas por cobrar",
        "cuentas por cobrar comerciales (neto)",
    ],
    "inventory": [
        "inventarios",
        "existencias",
        "existencias (neto)",
    ],
    "current_liabilities": [
        "total pasivos corrientes",
        "total pasivo corriente",
    ],
    "total_liabilities": [
        "total pasivos",
        "total pasivo",
        "total de pasivos",
    ],
    "short_term_debt": [
        "otros pasivos financieros corriente",
        "otros pasivos financieros corrientes",
        "obligaciones financieras corriente",
        "obligaciones financieras (corriente)",
        "parte corriente de las deudas a largo plazo",
        "sobregiros bancarios",
    ],
    "long_term_debt": [
        "otros pasivos financieros no corriente",
        "otros pasivos financieros no corrientes",
        "obligaciones financieras no corriente",
        "obligaciones financieras (no corriente)",
        "deudas a largo plazo",
    ],
    "total_equity": [
        "total patrimonio",
        "total patrimonio neto",
        "patrimonio total",
    ],
    "equity_attributable": [
        "patrimonio atribuible a los propietarios de la controladora",
        "patrimonio atribuible a la matriz",
    ],
}

# --- Flujo de efectivo --------------------------------------------------------
CASH_FLOW_MAP = {
    "operating_cash_flow": [
        "flujos de efectivo y equivalente al efectivo procedente de (utilizados en) actividades de operacion",
        "aumento (disminucion) neto de efectivo por actividades de operacion",
        "efectivo neto proveniente de actividades de operacion",
        "flujos de efectivo procedentes de (utilizados en) actividades de operacion",
    ],
    "investing_cash_flow": [
        "flujos de efectivo y equivalente al efectivo procedente de (utilizados en) actividades de inversion",
        "aumento (disminucion) neto de efectivo por actividades de inversion",
        "efectivo neto utilizado en actividades de inversion",
        "flujos de efectivo procedentes de (utilizados en) actividades de inversion",
    ],
    "financing_cash_flow": [
        "flujos de efectivo y equivalente al efectivo procedente de (utilizados en) actividades de financiacion",
        "aumento (disminucion) neto de efectivo por actividades de financiacion",
        "efectivo neto proveniente de actividades de financiamiento",
        "flujos de efectivo procedentes de (utilizados en) actividades de financiacion",
    ],
    "capex": [
        "compra de propiedades, planta y equipo",
        "compras de propiedades, planta y equipo",
        "adquisicion de propiedades, planta y equipo",
        "pagos por compras de propiedades, planta y equipo",
        "compra de inmuebles, maquinaria y equipo",
    ],
    "dividends_paid": [
        "dividendos pagados",
        "pago de dividendos",
        "dividendos pagados, clasificados como actividades de financiacion",
    ],
    "interest_paid": [
        "intereses pagados",
        "intereses pagados, clasificados como actividades de financiacion",
        "intereses pagados, clasificados como actividades de operacion",
    ],
}

STATEMENT_MAPS = {
    "income": INCOME_STATEMENT_MAP,
    "balance": BALANCE_SHEET_MAP,
    "cash_flow": CASH_FLOW_MAP,
}

# Nombres de los estados en la SMV -> tipo interno
STATEMENT_NAME_PATTERNS = [
    ("balance", ["estado de situacion financiera", "balance general"]),
    ("income", ["estado de resultados", "estado de ganancias y perdidas"]),
    ("cash_flow", ["estado de flujo de efectivo", "estado de flujos de efectivo"]),
]


def classify_statement(title: str) -> str | None:
    t = normalize_text(title)
    if "integral" in t or "cambios en el patrimonio" in t:
        return None  # resultado integral / cambios en patrimonio: no se mapean
    for kind, patterns in STATEMENT_NAME_PATTERNS:
        if any(p in t for p in patterns):
            return kind
    return None


def map_accounts(kind: str, rows: list[tuple[str, float | None]]) -> dict:
    """Convierte filas (descripción, valor) de un estado SMV a campos internos.

    Devuelve solo los campos encontrados; los ausentes no se incluyen (None
    implícito). Respeta la prioridad del mapeo: si dos denominaciones matchean
    el mismo campo, gana la de mayor prioridad.
    """
    mapping = STATEMENT_MAPS[kind]
    normalized = {}
    for desc, value in rows:
        key = normalize_text(desc)
        if key and key not in normalized and value is not None:
            normalized[key] = value

    out = {}
    for field, aliases in mapping.items():
        for alias in aliases:
            if alias in normalized:
                out[field] = normalized[alias]
                break
    return out


def derive_fields(fields: dict) -> dict:
    """Deriva campos calculables a partir de los mapeados, sin inventar datos.

    - gross_profit = revenue - cost_of_sales (si falta y ambos existen; el
      costo de ventas de la SMV llega con signo negativo).
    - ebit: se usa operating_income como aproximación estándar.
    - total_debt = short_term_debt + long_term_debt (si al menos uno existe,
      el otro se asume 0 SOLO si el balance reporta explícitamente el total
      de pasivos; en caso contrario queda None).
    - capex: se normaliza a positivo (la SMV lo reporta como salida negativa).
    """
    f = dict(fields)

    if f.get("gross_profit") is None and f.get("revenue") is not None and f.get("cost_of_sales") is not None:
        # la SMV reporta el costo de ventas con signo negativo; se usa la magnitud
        f["gross_profit"] = f["revenue"] - abs(f["cost_of_sales"])

    if f.get("ebit") is None and f.get("operating_income") is not None:
        f["ebit"] = f["operating_income"]

    st, lt = f.get("short_term_debt"), f.get("long_term_debt")
    if f.get("total_debt") is None and (st is not None or lt is not None):
        f["total_debt"] = (st or 0) + (lt or 0)

    # CAPEX: normalizar signo (evita restarlo dos veces en el FCF)
    if f.get("capex") is not None:
        f["capex"] = abs(f["capex"])

    # Gastos financieros y dividendos: trabajar con magnitud
    for k in ("financial_expenses", "dividends_paid"):
        if f.get(k) is not None:
            f[k] = abs(f[k])

    # net_income_attributable: si no hay minoritarios reportados, usar net_income
    if f.get("net_income_attributable") is None and f.get("net_income") is not None:
        f["net_income_attributable"] = f["net_income"]
    if f.get("equity_attributable") is None and f.get("total_equity") is not None:
        f["equity_attributable"] = f["total_equity"]

    return f

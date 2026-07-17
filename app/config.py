"""Configuración centralizada: umbrales de semáforos, sectores financieros,
pesos del score. Ningún componente debe definir umbrales propios.

Los umbrales aplican a empresas NO financieras salvo que se indique lo contrario.
"""

# ---------------------------------------------------------------------------
# Semáforos (status: "good" | "medium" | "risky" | "not_significant")
# Cada regla es (limite, estado) evaluada en orden.
# ---------------------------------------------------------------------------
THRESHOLDS = {
    "roic":              {"good_gte": 0.12, "medium_gte": 0.08},
    "roe":               {"good_gte": 0.15, "medium_gte": 0.08},
    "cash_conversion":   {"good_gte": 1.0,  "medium_gte": 0.7},
    "net_debt_to_ebitda": {"good_lt": 1.5, "medium_lte": 3.0},   # menor es mejor
    "interest_coverage": {"good_gt": 5.0,  "medium_gte": 2.5},
    "current_ratio":     {"good_range": (1.2, 2.5), "medium_range": (1.0, 1.2)},
}

# Umbrales usados por el motor de alertas
ALERT_THRESHOLDS = {
    "cash_conversion_low": 0.5,
    "net_debt_to_ebitda_high": 3.0,
    "interest_coverage_low": 2.0,
    "debt_growth_high": 0.20,
    "receivables_vs_sales_gap": 0.20,   # 20 puntos porcentuales
    "inventory_vs_sales_gap": 0.20,
    "current_ratio_low": 1.0,
    "capex_vs_ocf_high": 1.5,           # CAPEX > 1.5x flujo operativo
}

# Variación relativa mínima para considerar que un KPI "mejora"/"empeora"
TREND_TOLERANCE = 0.02

# ---------------------------------------------------------------------------
# Clasificación de sectores financieros (no se les aplica deuda/EBITDA ni FCF)
# ---------------------------------------------------------------------------
FINANCIAL_SECTOR_NAMES = {
    "bancos", "financieras", "seguros", "afp", "cajas",
    "administradoras de fondos", "servicios financieros",
}

# Palabras en el nombre de la empresa que delatan una entidad financiera
FINANCIAL_NAME_KEYWORDS = [
    "banco", "financiera", "seguros", "reaseguro", "afp ", " afp",
    "caja municipal", "caja rural", "fondo de pensiones", "leasing",
    "edpyme", "hipotecaria", "credi", "scotiabank", "interbank", "bbva",
    "mibanco", "prima afp", "profuturo", "habitat",
]

# KPIs prioritarios según tipo de empresa (orden de las tarjetas destacadas)
HIGHLIGHT_KPIS_NON_FINANCIAL = [
    "roic", "roe", "operating_margin", "revenue_growth_yoy",
    "free_cash_flow", "cash_conversion", "net_debt_to_ebitda", "interest_coverage",
]
HIGHLIGHT_KPIS_FINANCIAL = [
    "roe", "roa", "net_margin", "net_income_growth_yoy",
    "total_assets_growth_yoy", "equity_to_assets", "revenue_growth_yoy", "operating_margin",
]

# ---------------------------------------------------------------------------
# Score financiero (0-100) — solo empresas no financieras
# ---------------------------------------------------------------------------
SCORE_WEIGHTS = {
    "profitability": {  # 25
        "roic": 12, "roe": 5, "operating_margin_vs_sector": 5, "margin_trend": 3,
    },
    "cash_flow": {  # 25
        "fcf_positive": 8, "cash_conversion": 8, "fcf_margin": 5, "fcf_growth": 4,
    },
    "solvency": {  # 25
        "net_debt_to_ebitda": 10, "interest_coverage": 8, "current_ratio": 4,
        "positive_equity": 3,
    },
    "growth": {  # 15
        "revenue_growth": 6, "operating_income_growth": 5, "net_income_growth": 4,
    },
    "consistency": {  # 10
        "positive_kpi_streak": 4, "no_severe_alerts": 3, "data_completeness": 3,
    },
}

SCORE_LEVELS = [
    (85, "Fortaleza financiera alta"),
    (70, "Fortaleza financiera buena"),
    (55, "Situación financiera intermedia"),
    (40, "Riesgo financiero elevado"),
    (0,  "Riesgo financiero alto"),
]

# Tasa tributaria efectiva: límites para descartar valores anómalos en ROIC
EFFECTIVE_TAX_RATE_MIN = 0.0
EFFECTIVE_TAX_RATE_MAX = 0.60
EFFECTIVE_TAX_RATE_FALLBACK = 0.295  # tasa estatutaria peruana aprox. (29.5%)

# Días por periodo para ratios de eficiencia
DAYS_PER_PERIOD = {"semester": 182, "annual": 365}

# Rankings
RANKING_MIN_COMPANIES = 5
RANKING_MAX_COMPANIES = 20

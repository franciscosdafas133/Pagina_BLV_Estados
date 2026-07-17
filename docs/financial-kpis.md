# Diccionario de KPIs financieros

Documento de referencia de todos los indicadores calculados por la plataforma.
Todos los KPIs se calculan con funciones puras en [app/kpis/formulas.py](../app/kpis/formulas.py)
y se orquestan en [app/kpis/engine.py](../app/kpis/engine.py). Los umbrales viven
centralizados en [app/config.py](../app/config.py).

## Reglas transversales

- **`null` ≠ `0`.** Un campo no reportado es `null` y produce "No disponible".
  Nunca se rellena con cero ni se inventa.
- **Sin `Infinity`/`NaN`.** Toda división pasa por `safe_div`: denominador cero
  o `null` ⇒ `null`.
- **Signos normalizados.** El costo de ventas, el CAPEX, los gastos financieros
  y los dividendos de la SMV pueden llegar negativos; se toma su magnitud
  (`abs`) donde corresponde para no restar dos veces.
- **Aproximaciones marcadas.** Cuando falta el periodo anterior para un
  promedio, o el EBITDA se aproxima, el KPI se marca `isEstimated` con la razón.
- **Interanual = mismo semestre.** Los crecimientos comparan un semestre contra
  el **mismo semestre** del año anterior (S2-2025 vs S2-2024), nunca semestres
  distintos.

Unidades: `percent` (porcentaje), `money` (miles de soles), `ratio` (veces),
`days` (días).

---

## A. Rentabilidad

### gross_margin — Margen bruto
- **Fórmula:** `gross_profit / revenue`
- **Origen:** `gross_profit`, `revenue`
- **Interpretación:** porcentaje de ventas que queda tras el costo directo.
- **No aplica:** `revenue = 0` o nulo.

### operating_margin — Margen operativo
- **Fórmula:** `operating_income / revenue`
- **Origen:** `operating_income`, `revenue`
- **Interpretación:** eficiencia del negocio principal antes de intereses e impuestos.
- **Umbral:** no se usa umbral universal; se compara contra periodo anterior,
  histórico y **mediana del sector** (los sectores tienen márgenes estructurales
  muy distintos).

### net_margin — Margen neto
- **Fórmula:** `net_income_attributable / revenue`
- **Origen:** `net_income_attributable`, `revenue`

### roa — Rentabilidad sobre activos
- **Fórmula:** `net_income / average_total_assets`,
  `average_total_assets = (activos_actual + activos_previo) / 2`
- **Origen:** `net_income`, `total_assets` (actual y previo)
- **Aproximación:** sin balance previo se usa el activo final (marcado).

### roe — Rentabilidad sobre patrimonio
- **Fórmula:** `net_income_attributable / average_equity_attributable`
- **Origen:** `net_income_attributable`, `equity_attributable` (actual y previo)
- **No aplica:** patrimonio promedio ≤ 0 (no significativo).
- **Umbral:** Bueno ≥ 15% · Intermedio 8–15% · Riesgoso < 8%.

### roic — Rentabilidad sobre capital invertido
- **Fórmula:**
  `nopat = ebit × (1 − effective_tax_rate)`
  `effective_tax_rate = income_tax / income_before_tax`
  `invested_capital = total_equity + total_debt − cash_and_equivalents`
  `roic = nopat / average_invested_capital`
- **Origen:** `ebit`, `income_tax`, `income_before_tax`, `total_equity`,
  `total_debt`, `cash_and_equivalents` (actual y previo)
- **Validaciones:** la tasa efectiva se acota a [0%, 60%]; fuera de rango o con
  base imponible ≤ 0 se usa la tasa estatutaria peruana (29.5%) y se marca
  estimado. Capital invertido promedio ≤ 0 ⇒ no significativo.
- **Umbral:** Bueno ≥ 12% · Intermedio 8–12% · Riesgoso < 8%.
- **Limitación:** requiere `total_debt`; muchas empresas de la SMV no reportan
  la deuda con el concepto XBRL estándar, en cuyo caso el ROIC queda "No disponible".

---

## B. Crecimiento (interanual, mismo semestre)

`*_growth_yoy = (actual − mismo_semestre_año_anterior) / mismo_semestre_año_anterior`

- **KPIs:** `revenue_growth_yoy`, `operating_income_growth_yoy`,
  `net_income_growth_yoy`, `total_assets_growth_yoy`, `equity_growth_yoy`,
  `operating_cash_flow_growth_yoy`, `fcf_growth_yoy`.
- **No aplica:** sin el mismo periodo del año anterior, o base ≤ 0 (variación
  no comparable — no se muestra un porcentaje engañoso).

### CAGR a 3 años
`cagr = (valor_final / valor_inicial)^(1/años) − 1`
- **KPIs:** `revenue_cagr_3y`, `net_income_cagr_3y`, `fcf_cagr_3y`.
- **No aplica:** menos de 4 años anuales, o algún extremo ≤ 0.

---

## C. Flujo de caja

### free_cash_flow — Flujo de caja libre
- **Fórmula:** `operating_cash_flow − |capex|`
- **Nota:** el CAPEX se normaliza a positivo para no restarlo dos veces.

### fcf_margin — Margen de FCF
- **Fórmula:** `free_cash_flow / revenue`

### cash_conversion — Conversión de utilidad en caja
- **Fórmula:** `operating_cash_flow / net_income`
- **No aplica:** `net_income ≤ 0` (no significativo).
- **Umbral:** Bueno ≥ 1 · Intermedio 0.7–1 · Riesgoso < 0.7.

### dividend_coverage — Cobertura del dividendo
- **Fórmula:** `free_cash_flow / |dividends_paid|`
- **No aplica:** sin dividendos ("No aplica").

---

## D. Endeudamiento (no aplica a empresas financieras)

### total_debt / net_debt
- `total_debt = short_term_debt + long_term_debt`
- `net_debt = total_debt − cash_and_equivalents` (puede ser negativa = caja neta).

### debt_to_equity — Deuda financiera / Patrimonio
- **Fórmula:** `total_debt / total_equity` (solo deuda financiera: corto + largo plazo).
- **No aplica:** patrimonio ≤ 0.
- **Nota:** distinto de `liabilities_to_equity`. La deuda financiera se toma de
  `Borrowings` o, si no existen, de `Other*FinancialLiabilities` (así reportan
  emisores como Leche Gloria).

### liabilities_to_equity — Pasivo / Patrimonio (apalancamiento)
- **Fórmula:** `total_liabilities / total_equity`.
- **Interpretación:** apalancamiento total (todos los pasivos, no solo deuda).
  **Es el indicador que la BVL/SMV publica como "Deuda/Patrimonio"** en sus
  índices anuales; coincide al cuarto decimal.
- **No aplica:** patrimonio ≤ 0.

### debt_to_assets — Deuda / Activos
- `total_debt / total_assets`

### net_debt_to_ebitda — Deuda neta / EBITDA
- **EBITDA:** si no viene directo, `ebitda = ebit + |depreciation_and_amortization|`
  (marcado estimado; nunca se inventa: sin D&A no hay EBITDA).
- En periodos semestrales el EBITDA se **anualiza (×2)** para compararlo contra
  el stock de deuda (evita duplicar el ratio).
- **No significativo:** EBITDA ≤ 0.
- **Umbral:** Bueno < 1.5 · Intermedio 1.5–3 · Riesgoso > 3.

### interest_coverage — Cobertura de intereses
- **Fórmula:** `ebit / |financial_expenses|`
- **No aplica:** gasto financiero cero o nulo (sin infinitos).
- **Umbral:** Bueno > 5 · Intermedio 2.5–5 · Riesgoso < 2.5.

---

## E. Liquidez (no aplica a empresas financieras)

- **current_ratio:** `current_assets / current_liabilities`.
  Umbral: Bueno 1.2–2.5 · Intermedio 1–1.2 · Riesgoso < 1.
- **quick_ratio:** `(current_assets − inventory) / current_liabilities`.
- **working_capital:** `current_assets − current_liabilities`.

---

## F. Eficiencia

- **asset_turnover:** `revenue / average_total_assets`.
- **days_sales_outstanding:** `average_accounts_receivable / revenue × días`.
- **days_inventory:** `average_inventory / |cost_of_sales| × días`.
- **equity_to_assets:** `total_equity / total_assets` (clave en financieras).

Días por periodo: **182** (semestre), **365** (anual).

---

## Empresas financieras

Bancos, financieras, cajas, seguros, AFP y fondos **no** se evalúan con
deuda/EBITDA, cobertura de intereses, liquidez ni FCF (sus pasivos financieros
son inherentes al negocio). Se priorizan: ROE, ROA, margen neto, crecimiento de
utilidad y activos, y patrimonio/activos. En rankings se separan de las no
financieras. La clasificación está en
[app/smv/sectors_seed.py](../app/smv/sectors_seed.py) y
[app/config.py](../app/config.py).

---

## Semáforos y tendencias

- **Estado** (`good`/`medium`/`risky`/`not_significant`): según umbrales de
  `config.THRESHOLDS`. Se acompaña siempre de icono + texto (no solo color).
- **Tendencia** (`improving`/`stable`/`worsening`): variación vs. el mismo
  semestre del año anterior, con tolerancia del 2%. Para KPIs donde "menos es
  mejor" (deuda, días de cobranza) la dirección se invierte.

## Score financiero (0–100, solo no financieras)

Ponderación: Rentabilidad 25 · Flujo de caja 25 · Solidez 25 · Crecimiento 15 ·
Consistencia 10. El score se **reescala por el peso efectivo** de los KPIs
disponibles y se acompaña de `dataQualityScore` y nivel de confianza. Con menos
del 40% del peso disponible no se emite score. Detalle en
[app/kpis/score.py](../app/kpis/score.py).

## Diferencias con los índices publicados por la BVL/SMV

Los índices anuales que la BVL muestra en la ficha de cada empresa se calculan
con **saldos de cierre**; esta plataforma usa **saldos promedio** (inicio+fin)/2
en ROE, ROA y rotación de activos (metodología estándar para ratios que cruzan
un flujo del periodo con un stock del balance). Por eso esos ratios difieren en
décimas — no es un error de extracción. Validado contra Leche Gloria: liquidez
y pasivo/patrimonio coinciden al cuarto decimal; ROE y rotación difieren solo
por promedio vs. cierre.

## Limitaciones conocidas

- **Deuda desglosada:** algunas empresas no reportan `Borrowings` con el
  concepto XBRL estándar ⇒ `total_debt`, ROIC, deuda/EBITDA quedan "No
  disponible". No se aproximan.
- **Depreciación y amortización:** cuando el estado de resultados no la separa,
  el EBITDA (y por tanto deuda/EBITDA) no puede calcularse.
- **Atribuible a la matriz:** si el XBRL no lo reporta por separado, se usa el
  resultado/patrimonio total como aproximación.
- **Consolidado vs. individual:** el XBRL de la SMV no siempre marca el tipo;
  se asume consolidado salvo mención explícita de "individual/separado" en la
  cabecera del informe. Estados individuales se señalan visualmente.
- **Datos accionarios y de mercado** (precio, market cap, P/B) no están en los
  estados financieros de la SMV; los KPIs que dependen de ellos no se calculan.

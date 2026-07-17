# Análisis Fundamental — Empresas de la SMV (Perú)

MVP educativo de análisis fundamental de empresas peruanas registradas en la
Superintendencia del Mercado de Valores (SMV). Extrae estados financieros
reales, los normaliza, calcula KPIs, rankings, alertas y un score financiero, y
los presenta en una interfaz web. **Es una herramienta educativa y analítica: no
emite recomendaciones de compra o venta.**

---

## 1. Arquitectura

El repositorio original contenía un único archivo vacío (`hola.py`), sin
framework, base de datos ni scraper. Se construyó desde cero con un stack
ligero, sin dependencias pesadas de frontend:

| Capa | Tecnología |
|------|-----------|
| Backend / API | **FastAPI** (Python) |
| ORM / Base de datos | **SQLAlchemy 2.0** + **SQLite** (archivo `smv_analisis.db`) |
| Extracción SMV | **httpx** + **BeautifulSoup/lxml**, parseo de **XBRL** IFRS |
| Frontend | **HTML + CSS + JavaScript** (módulos ES nativos, sin build, sin librerías) |
| Gráficos | **SVG** dibujado a mano (sin dependencias) |
| Pruebas | **pytest** + `TestClient` de FastAPI |

### Cómo se extraen los datos de la SMV

La SMV publica cada estado financiero como un **archivo XBRL estructurado**
(taxonomía `ifrs-full` 2015 + extensión `smv`). Es la fuente preferida sobre el
HTML porque los conceptos son estándar y las cifras no requieren heurística:

1. `Frm_InformacionFinanciera` — formulario ASP.NET WebForms con el catálogo de
   ~200 emisores y filtros de año/trimestre.
2. POST del formulario (con `__VIEWSTATE`/`__EVENTVALIDATION`) ⇒ grilla de
   filings; se capturan los enlaces `documento.aspx?vidDoc=…` (XBRL) por trimestre.
3. Descarga y parseo del XBRL: contextos de duración YTD (flujos acumulados) e
   instantáneos (balance al cierre), solo hechos sin dimensiones.

Ver [app/smv/scraper.py](app/smv/scraper.py) y [app/smv/xbrl.py](app/smv/xbrl.py).

### Modelo de datos

Datos originales y KPIs calculados se mantienen **separados** ([app/models.py](app/models.py)):

- `companies`, `sectors` — catálogo y clasificación sectorial.
- `financial_statements` — estados normalizados por periodo (originales).
- `calculated_kpis` — KPIs precalculados (no se recalcula en cada request).
- `financial_alerts` — alertas automáticas.
- `ingestion_logs` — trazabilidad de las corridas de ingesta.

Índices para `company_id`, `year`, `semester`, `sector`, `is_consolidated` y los
KPIs usados en rankings. Las cargas evitan N+1 (KPIs de un periodo se traen en
una sola consulta y se agrupan en memoria).

### Normalización de periodos

La SMV entrega resultados intermedios **acumulados (YTD)**. La capa
[app/periods.py](app/periods.py) deriva:

- **S1** = acumulado a junio (filing Q2).
- **S2** = acumulado anual − acumulado junio (diferencia; nunca se suman
  acumulados dos veces). El balance es la foto al cierre.
- **Anual** = acumulado a diciembre.
- **TTM** = S2 del año anterior + S1 actual (cuando hay insumos).

---

## 2. Requisitos e instalación

```bash
pip install -r requirements.txt
```

Python 3.11+. Dependencias: fastapi, uvicorn, sqlalchemy, httpx,
beautifulsoup4, lxml, pytest.

---

## 3. Ejecución

### Opción A — datos DEMO (sin red, para ver la interfaz)

```bash
python -m scripts.seed_demo          # 10 empresas sintéticas (prefijo DEMO)
python -m uvicorn app.main:app --reload
```

### Opción B — datos reales de la SMV

```bash
# Ingesta de empresas concretas (por smv_id) para 2023-2025
python -m app.cli ingest --smv-ids 30481 73 168 30003 --years 2023 2024 2025

# o todas las empresas del catálogo (lento; usa --limit para acotar)
python -m app.cli ingest --years 2024 2025 --limit 20

python -m uvicorn app.main:app --reload
```

Otros comandos del CLI ([app/cli.py](app/cli.py)):

```bash
python -m app.cli sync-companies     # solo sincroniza el catálogo de empresas
python -m app.cli recalc             # recalcula KPIs y alertas (p.ej. tras cambiar una fórmula)
```

Abrir **http://127.0.0.1:8000/**. Ficha de empresa en `/empresas/{id}`.

### Pruebas

```bash
python -m pytest tests/ -q           # 86 pruebas (unitarias + integración)
```

---

## 4. Entregables

1. **Arquitectura encontrada:** repositorio vacío (`hola.py`); se construyó el
   stack completo descrito arriba.
2. **Archivos creados** — ver sección 5.
3. **Migraciones:** SQLite se crea automáticamente desde los modelos
   (`Base.metadata.create_all`) al iniciar el servidor o el CLI. No se requiere
   herramienta de migración externa para el MVP.
4. **Funciones de KPIs:** [app/kpis/formulas.py](app/kpis/formulas.py) (puras),
   orquestadas en [app/kpis/engine.py](app/kpis/engine.py).
5. **Endpoints:** ver sección 6.
6. **Frontend:** `static/` (página principal, ficha de empresa, buscador, gráficos).
7. **Pruebas:** `tests/`.
8. **Instrucciones:** sección 3.
9. **Supuestos financieros:** sección 7 y [docs/financial-kpis.md](docs/financial-kpis.md).
10. **KPIs no implementables:** sección 8.

---

## 5. Archivos creados

```
app/
  main.py                  API REST + servido de estáticos
  config.py                umbrales, sectores financieros, pesos del score (centralizado)
  database.py              engine SQLite + sesión
  models.py                companies, sectors, financial_statements, calculated_kpis,
                           financial_alerts, ingestion_logs
  periods.py               normalización de periodos (S1/S2/anual/TTM)
  cli.py                   ingesta y recálculo por línea de comandos
  kpis/
    formulas.py            funciones puras de KPIs
    engine.py              cálculo de todos los KPIs de un periodo
    status.py              semáforos y tendencias
    score.py               score financiero 0-100
    alerts.py              motor de alertas automáticas
    meta.py                etiquetas, fórmulas y tooltips
  smv/
    scraper.py             scraper del portal SMV (WebForms + XBRL)
    xbrl.py                parser XBRL (taxonomía IFRS)
    account_mapping.py     mapeo de cuentas SMV → campos internos
    sectors_seed.py        clasificación sectorial curada
  services/
    ingestion.py           pipeline de ingesta + recálculo
    analytics.py           comparación sectorial, rankings, resumen, score, conclusión
static/
  index.html, empresa.html
  css/styles.css
  js/common.js, search.js, charts.js, home.js, company.js
scripts/seed_demo.py       datos sintéticos para probar la interfaz
tests/                     test_formulas, test_periods, test_engine_alerts,
                           test_mapping, test_api (+ conftest)
docs/financial-kpis.md     diccionario de KPIs
```

---

## 6. API

Todos bajo `/api`. Respuestas con formato consistente (ver ejemplo en el prompt).

| Endpoint | Descripción |
|----------|-------------|
| `GET /api/companies` | listado/búsqueda. Filtros: `search`, `sector`, `year`, `semester`, `consolidated`, `data_complete`, `profitable`, `positive_fcf`, `low_debt`, `positive_growth`, `kpi`, `kpi_min` |
| `GET /api/companies/{id}` | datos de la empresa y periodos disponibles |
| `GET /api/companies/{id}/kpis` | KPIs, semáforos, comparación sectorial, alertas, score, conclusión (`year`, `semester`, `period_type`) |
| `GET /api/companies/{id}/history` | serie histórica de un KPI (`metric`, `from_year`, `to_year`, `period_type`) |
| `GET /api/companies/{id}/statements` | estados financieros originales del periodo |
| `GET /api/rankings/profitability` | ranking por rentabilidad (`metric`, `sector`, `financial`, `limit`) |
| `GET /api/rankings/growth` | ranking por crecimiento de ingresos |
| `GET /api/rankings/cash-flow` | ranking por generación de caja |
| `GET /api/rankings/alerts` | empresas con alertas |
| `GET /api/sectors` · `GET /api/periods` · `GET /api/summary` | catálogos y resumen de mercado |

Docs interactivas en **/docs** (Swagger de FastAPI).

---

## 7. Supuestos financieros

- **Cifras en miles de soles.** El XBRL viene en unidades; se normaliza a miles
  (÷1000) al ingerir, coherente con el resto de reportes SMV.
- **Flujos acumulados.** Los resultados y flujos intermedios se tratan como YTD;
  los semestres se derivan por diferencia (nunca por suma).
- **Tasa tributaria** efectiva acotada a [0%, 60%]; fuera de rango o con base ≤ 0
  se usa la estatutaria peruana 29.5%.
- **EBITDA** solo se aproxima como `EBIT + D&A` si la D&A existe; nunca se inventa.
- **Consolidado por defecto** salvo mención explícita de estado individual.
- **Días por periodo:** 182 (semestre), 365 (anual).
- Detalle completo por KPI en [docs/financial-kpis.md](docs/financial-kpis.md).

---

## 8. KPIs no implementados y por qué

- **P/B, market cap, precio, EPS diluido** — requieren datos de mercado que la
  SMV no publica en los estados financieros. Los campos existen en el modelo
  (`market_price`, `market_cap`, etc.) pero quedan nulos.
- **Indicadores regulatorios de bancos/AFP** (ratio de capital, morosidad) — la
  fuente estándar de estados financieros no los expone; requerirían los anexos
  regulatorios de la SBS.
- **ROIC / deuda-EBITDA en empresas sin deuda desglosada** — cuando el XBRL no
  usa el concepto `Borrowings` estándar, se muestran como "No disponible" en
  lugar de aproximarse.

---

## Descargo de responsabilidad

Plataforma con fines **educativos y analíticos**. La información puede contener
errores de mapeo o de fuente. No constituye asesoría de inversión ni
recomendación de compra o venta de valores.

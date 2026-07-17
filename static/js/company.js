// Ficha de detalle de empresa: cabecera, resumen, KPIs destacados,
// secciones, alertas, comparación sectorial, estados y gráficos históricos.
import { api, apiPost, el, emptyState, loadingScreen, statusBadge, trendText, tooltip, skeletonCards, semesterLabel } from "./common.js";
import { mountSearch } from "./search.js";
import { barChart, lineChart } from "./charts.js";

const companyId = Number(window.location.pathname.split("/").pop());
const $ = (id) => document.getElementById(id);
const app = $("app");
let currentPeriod = { year: null, semester: null, periodType: "semester" };
let chartMode = { periodType: "semester" };

// Scrapea la empresa AÑO POR AÑO (peticiones cortas que no superan el timeout
// del hosting gratuito). Muestra progreso "Descargando 2025… 2024… 2023…".
async function scrapeByYear(name, { force = false } = {}) {
  let years;
  try {
    years = (await api("/api/live-years")).years;
  } catch (_) {
    years = [2025, 2024, 2023];
  }
  let anyData = false;
  for (let i = 0; i < years.length; i++) {
    const y = years[i];
    app.replaceChildren(loadingScreen(
      `Obteniendo datos de ${name} desde la SMV…`,
      `Descargando el año ${y} en tiempo real (${i + 1} de ${years.length}). ` +
      `Cada año tarda unos segundos; por favor espera.`));
    try {
      const r = await apiPost(`/api/companies/${companyId}/ensure-year`, { year: y, force });
      if (r.status === "scraped" || r.status === "cached") anyData = anyData || r.status === "scraped";
    } catch (_) { /* un año que falla no aborta el resto */ }
  }
  return anyData;
}

async function init() {
  mountSearch($("search-slot"));
  try {
    let info = await api(`/api/companies/${companyId}`);
    // Si la empresa no tiene periodos cacheados, scrapear de la SMV en vivo
    if (!info.availablePeriods || info.availablePeriods.length === 0) {
      const name = info.company?.name || "la empresa";
      await scrapeByYear(name);
      info = await api(`/api/companies/${companyId}`);
      if (!info.availablePeriods || info.availablePeriods.length === 0) {
        app.replaceChildren(emptyState(
          "La SMV no tiene información financiera procesable para esta empresa " +
          "(puede no reportar en XBRL o estar retirada del registro).", true));
        return;
      }
    }
    buildPeriodSelector(info.availablePeriods);
    await loadPeriod();
  } catch (e) {
    app.replaceChildren(emptyState("No se pudo cargar la empresa: " + e.message, true));
  }
}

// Botón para re-scrapear en vivo desde la SMV (datos frescos, año por año)
async function refreshFromSMV() {
  const name = document.querySelector("h1")?.textContent || "la empresa";
  try {
    await scrapeByYear(name, { force: true });
    const info = await api(`/api/companies/${companyId}`);
    buildPeriodSelector(info.availablePeriods);
    await loadPeriod();
  } catch (e) {
    app.replaceChildren(emptyState("No se pudo actualizar: " + e.message, true));
  }
}

function buildPeriodSelector(periods) {
  const sel = $("f-period");
  sel.replaceChildren();
  const sem = periods.filter((p) => p.periodType === "semester");
  sem.forEach((p) => sel.append(el("option",
    { value: `semester:${p.year}:${p.semester}` },
    `${p.year} · ${semesterLabel(p.semester)}${p.isConsolidated ? "" : " (individual)"}`)));
  const ann = periods.filter((p) => p.periodType === "annual");
  ann.forEach((p) => sel.append(el("option", { value: `annual:${p.year}:` }, `${p.year} · Anual`)));
  if (sem[0]) currentPeriod = { year: sem[0].year, semester: sem[0].semester, periodType: "semester" };
  sel.onchange = () => {
    const [pt, y, s] = sel.value.split(":");
    currentPeriod = { periodType: pt, year: Number(y), semester: s ? Number(s) : null };
    loadPeriod();
  };
}

async function loadPeriod() {
  app.replaceChildren(el("div", { class: "skeleton", style: "height:36px;width:45%" }), skeletonCards(8));
  try {
    const data = await api(`/api/companies/${companyId}/kpis`, {
      year: currentPeriod.year, semester: currentPeriod.semester,
      period_type: currentPeriod.periodType,
    });
    render(data);
  } catch (e) {
    app.replaceChildren(emptyState(
      `No hay KPIs para ${currentPeriod.year} ${semesterLabel(currentPeriod.semester)}. ${e.message}`, true));
  }
}

function render(data) {
  const { company, period, kpis, alerts, score, summary, dataQuality, highlightKpis, sections } = data;
  app.replaceChildren();
  if (period.updatedAt) $("last-update").textContent =
    "Actualizado: " + new Date(period.updatedAt).toLocaleDateString("es-PE");

  // Cabecera
  app.append(el("section", {},
    el("div", { class: "company-head" }, el("h1", {}, company.name),
      company.ticker ? el("span", { class: "pill" }, company.ticker) : null,
      el("button", { class: "ghost", style: "margin-left:auto;font-size:.82rem",
        title: "Vuelve a descargar los datos de la SMV en tiempo real",
        onclick: refreshFromSMV }, "↻ Actualizar desde SMV")),
    el("div", { class: "company-meta" },
      el("span", { class: "pill" }, company.sector),
      company.ruc ? el("span", {}, "RUC " + company.ruc) : null,
      el("span", {}, `${period.year} · ${semesterLabel(period.semester)}`),
      el("span", {}, period.isConsolidated === false ? "Estado individual ⚠" : "Consolidado"),
      period.currency ? el("span", {}, period.currency) : null,
      period.isDerived ? el("span", { class: "pill" }, "periodo derivado") : null,
      period.sourceUrl ? el("a", { href: period.sourceUrl, target: "_blank", rel: "noopener" }, "Fuente SMV ↗") : null)));

  // Resumen automático + score
  const summarySection = el("section", {}, el("h2", {}, "Resumen"),
    el("p", { class: "subtitle" }, summary));
  if (score) {
    const meterColor = score.score >= 70 ? "var(--good)" : score.score >= 40 ? "var(--warning)" : "var(--critical)";
    summarySection.append(el("div", { class: "score-panel" },
      el("div", {},
        el("div", { class: "score-num" }, score.score ?? "—"),
        el("div", { class: "stat-label" }, score.level || "Score no disponible")),
      el("div", { style: "flex:1;min-width:200px" },
        el("div", { class: "meter" }, el("div", { style: `width:${score.score || 0}%;background:${meterColor}` })),
        el("div", { class: "score-detail", style: "margin-top:6px" },
          `Confianza: ${score.confidence} · Calidad de datos: ${score.dataQualityScore}/100 · `,
          `${score.kpisUsed.length} KPIs usados, ${score.kpisMissing.length} faltantes`))));
  } else if (company.isFinancial) {
    summarySection.append(el("p", { class: "score-detail" },
      "El score 0-100 no aplica a entidades financieras; se priorizan ROE, ROA y solidez patrimonial."));
  }
  app.append(summarySection);

  // Tarjetas destacadas (máx. 8)
  const cards = el("div", { class: "cards" });
  highlightKpis.forEach((k) => { if (kpis[k]) cards.append(kpiCard(k, kpis[k])); });
  app.append(el("section", {}, el("h2", {}, "Indicadores clave"), cards));

  // Alertas
  const alertsSection = el("section", {}, el("h2", {}, `Alertas (${alerts.length})`));
  if (!alerts.length) alertsSection.append(emptyState("Sin alertas para este periodo."));
  else alerts.forEach((a) => alertsSection.append(el("div", { class: `alert-item ${a.severity}` },
    el("div", { class: "alert-title" }, `${sevIcon(a.severity)} ${a.title}`),
    el("div", { class: "alert-desc" }, a.description),
    el("div", { class: "alert-meta" }, `Código ${a.code} · Umbral: ${a.threshold ?? "—"}`))));
  app.append(alertsSection);

  // Secciones de KPIs por categoría (con comparación sectorial embebida)
  for (const [name, keys] of Object.entries(sections)) {
    const grid = el("div", { class: "cards" });
    let any = false;
    keys.forEach((k) => { if (kpis[k]) { grid.append(kpiCard(k, kpis[k], true)); any = true; } });
    if (any) app.append(el("section", {}, el("h2", {}, name), grid));
  }

  // Gráficos históricos
  app.append(buildCharts(company));

  // Estados financieros crudos (en segundo plano)
  app.append(buildStatements());
}

function kpiCard(key, k, showSector = false) {
  const card = el("div", { class: "card" });
  card.append(el("div", { class: "kpi-label" },
    k.label, tooltip(k.label, k.formula, k.explain)));
  if (!k.isAvailable) {
    card.append(el("div", { class: "kpi-value na" }, "No disponible"));
    card.append(el("div", { class: "kpi-foot" }, k.reason || "Dato faltante"));
    return card;
  }
  card.append(el("div", { class: "kpi-value" }, k.displayValue));
  card.append(el("div", {}, statusBadge(k.status)));
  card.append(trendText(k.trend, k.change, k.unit));
  if (k.isEstimated) card.append(el("div", { class: "kpi-foot" }, "≈ estimado: " + (k.estimationNote || "")));
  if (showSector && k.sectorMedian !== undefined) {
    card.append(el("div", { class: "kpi-foot" },
      `Mediana sector: ${fmtLike(k, k.sectorMedian)} · Percentil ${k.percentile ?? "—"} · Puesto ${k.sectorRank}/${k.sectorCompanies}`));
  }
  return card;
}

function fmtLike(k, v) {
  if (v === null || v === undefined) return "—";
  if (k.unit === "percent") return (v * 100).toFixed(1) + "%";
  if (k.unit === "money") return "S/ " + (v * 1000).toLocaleString("es-PE", { maximumFractionDigits: 0 });
  return v.toFixed(2) + "x";
}

function sevIcon(s) { return s === "alta" ? "🔴" : s === "media" ? "🟠" : "🟡"; }

// --- Gráficos históricos ---
const CHART_METRICS = [
  ["revenue", "Ingresos", barChart], ["operating_income", "Utilidad operativa", barChart],
  ["net_income", "Utilidad neta", barChart], ["free_cash_flow", "Flujo de caja libre", barChart],
  ["roic", "ROIC", lineChart], ["roe", "ROE", lineChart],
  ["operating_margin", "Margen operativo", lineChart], ["net_debt_to_ebitda", "Deuda neta/EBITDA", lineChart],
];

function buildCharts(company) {
  const section = el("section", {}, el("h2", {}, "Evolución histórica"));
  const tabs = el("div", { class: "tabs" },
    el("button", { class: chartMode.periodType === "semester" ? "active" : "",
      onclick: (e) => switchMode("semester", e) }, "Semestral"),
    el("button", { class: chartMode.periodType === "annual" ? "active" : "",
      onclick: (e) => switchMode("annual", e) }, "Anual"));
  section.append(tabs);
  const grid = el("div", { class: "chart-grid", id: "chart-grid" });
  section.append(grid);
  CHART_METRICS.forEach(([metric, label, fn]) => grid.append(chartCard(metric, label, fn)));
  return section;
}

function switchMode(pt, e) {
  chartMode.periodType = pt;
  [...e.target.parentElement.children].forEach((c) => c.classList.remove("active"));
  e.target.classList.add("active");
  const grid = $("chart-grid");
  grid.replaceChildren();
  CHART_METRICS.forEach(([metric, label, fn]) => grid.append(chartCard(metric, label, fn)));
}

function chartCard(metric, label, fn) {
  const card = el("div", { class: "chart-card" }, el("h4", {}, label),
    el("div", { class: "skeleton", style: "height:150px" }));
  api(`/api/companies/${companyId}/history`, { metric, period_type: chartMode.periodType })
    .then((data) => {
      card.replaceChildren(el("h4", {}, label));
      if (data.series.length < 2) { card.append(emptyState("Historial insuficiente")); return; }
      card.append(fn(data.series, { unit: data.unit }));
      const est = data.series.some((s) => s.isEstimated);
      card.append(el("div", { class: "chart-note" },
        (data.unit === "percent" ? "En porcentaje" : data.unit === "money" ? "Cifras en miles" : "Ratio") +
        (est ? " · incluye valores estimados" : "")));
    })
    .catch(() => card.replaceChildren(el("h4", {}, label), emptyState("Sin datos")));
  return card;
}

// --- Estados financieros crudos ---
function buildStatements() {
  const section = el("section", {}, el("h2", {}, "Estados financieros (datos originales)"));
  const box = el("div", { id: "statements-box" }, el("div", { class: "skeleton", style: "height:120px" }));
  section.append(box);
  api(`/api/companies/${companyId}/statements`, {
    year: currentPeriod.year, semester: currentPeriod.semester, period_type: currentPeriod.periodType,
  }).then((data) => {
    const entries = Object.entries(data.fields).filter(([, v]) => v !== null);
    if (!entries.length) { box.replaceChildren(emptyState("Sin estados para el periodo.")); return; }
    const body = entries.map(([field, v]) => el("tr", {},
      el("td", {}, field),
      el("td", { class: "num" }, (v * 1000).toLocaleString("es-PE", { maximumFractionDigits: 0 }))));
    box.replaceChildren(
      el("p", { class: "chart-note" }, data.unitNote + (data.period.isDerived ? " · periodo derivado por diferencia de acumulados" : "")),
      el("div", { class: "table-wrap" }, el("table", {},
        el("thead", {}, el("tr", {}, el("th", {}, "Campo"), el("th", { class: "num" }, "Valor"))),
        el("tbody", {}, body))));
  }).catch(() => box.replaceChildren(emptyState("No se pudieron cargar los estados.")));
  return section;
}

init();

// Página principal: resumen de mercado, rankings y alertas.
import { api, el, emptyState, readParams, writeParams, trendText } from "./common.js";
import { mountSearch } from "./search.js";

const state = { year: null, semester: 2, sector: "", metric: "roic", financial: false };
Object.assign(state, readParams());
if (state.semester) state.semester = Number(state.semester);

const $ = (id) => document.getElementById(id);

async function init() {
  mountSearch($("search-slot"));

  const [periods, sectors] = await Promise.all([
    api("/api/periods").catch(() => ({ periods: [] })),
    api("/api/sectors").catch(() => ({ sectors: [] })),
  ]);

  // Selector de año (a partir de periodos disponibles)
  const years = [...new Set(periods.periods.filter((p) => p.periodType === "semester").map((p) => p.year))]
    .sort((a, b) => b - a);
  const ysel = $("f-year");
  if (!years.length) ysel.append(el("option", { value: "" }, "Sin datos"));
  years.forEach((y) => ysel.append(el("option", { value: y }, y)));
  if (!state.year && years.length) state.year = years[0];
  ysel.value = state.year || "";
  $("f-semester").value = state.semester;

  const ssel = $("f-sector");
  sectors.sectors.forEach((s) =>
    ssel.append(el("option", { value: s.name }, `${s.name} (${s.companies})`)));
  ssel.value = state.sector;

  ysel.onchange = () => { state.year = Number(ysel.value); refresh(); };
  $("f-semester").onchange = (e) => { state.semester = Number(e.target.value); refresh(); };
  ssel.onchange = (e) => { state.sector = e.target.value; refresh(); };
  $("f-clear").onclick = () => {
    state.sector = ""; ssel.value = ""; refresh();
  };

  $("prof-tabs").addEventListener("click", (e) => {
    const b = e.target.closest("button[data-metric]");
    if (!b) return;
    [...$("prof-tabs").children].forEach((c) => c.classList.remove("active"));
    b.classList.add("active");
    state.metric = b.dataset.metric;
    loadProfitability();
  });
  $("prof-financial").addEventListener("change", (e) => {
    state.financial = e.target.checked; loadProfitability();
  });

  refresh();
}

function persist() {
  writeParams({ year: state.year, semester: state.semester, sector: state.sector });
}

async function refresh() {
  persist();
  loadSummary();
  loadProfitability();
  loadGrowth();
  loadCash();
  loadAlerts();
}

async function loadSummary() {
  const box = $("summary");
  box.innerHTML = "";
  try {
    const s = await api("/api/summary", { year: state.year, semester: state.semester });
    if (s.lastUpdate) $("last-update").textContent =
      "Actualizado: " + new Date(s.lastUpdate).toLocaleDateString("es-PE");
    const tiles = [
      ["Empresas totales", s.totalCompanies],
      ["Con datos del periodo", s.companiesWithData],
      ["Con datos completos", s.companiesWithCompleteData],
      ["Sectores", s.sectors],
      ["% rentables", s.profitablePct != null ? s.profitablePct + "%" : "—"],
      ["% con FCF positivo", s.positiveFcfPct != null ? s.positiveFcfPct + "%" : "—"],
    ];
    tiles.forEach(([label, value]) =>
      box.append(el("div", { class: "stat-tile" },
        el("div", { class: "stat-value" }, String(value ?? "—")),
        el("div", { class: "stat-label" }, label))));
  } catch (e) {
    box.append(emptyState("No se pudo cargar el resumen: " + e.message, true));
  }
}

function rankingTable(rows, metricLabel, showNdte = true) {
  if (!rows.length) return emptyState("Datos insuficientes para este ranking (mínimo 5 empresas con datos válidos).");
  const cols = ["#", "Empresa", "Sector", metricLabel, "Margen op.", "Crec. ingresos", "FCF"];
  if (showNdte) cols.push("Deuda/EBITDA");
  cols.push("Tendencia", "");
  const thead = el("tr", {}, ...cols.map((c, i) =>
    el("th", { class: i >= 3 && i <= (showNdte ? 7 : 6) ? "num" : "" }, c)));
  const body = rows.map((r) => el("tr", {},
    el("td", {}, String(r.position)),
    el("td", {}, el("a", { href: `/empresas/${r.companyId}` }, r.company)),
    el("td", {}, r.sector),
    el("td", { class: "num" }, r.displayValue),
    el("td", { class: "num" }, r.operating_margin?.displayValue ?? "—"),
    el("td", { class: "num" }, r.revenue_growth_yoy?.displayValue ?? "—"),
    el("td", { class: "num" }, r.free_cash_flow?.displayValue ?? "—"),
    ...(showNdte ? [el("td", { class: "num" }, r.net_debt_to_ebitda?.displayValue ?? "—")] : []),
    el("td", {}, trendText(r.trend)),
    el("td", {}, el("a", { href: `/empresas/${r.companyId}` }, "Ver →"))));
  return el("div", { class: "table-wrap" }, el("table", {}, el("thead", {}, thead), el("tbody", {}, body)));
}

const METRIC_LABELS = {
  roic: "ROIC", roe: "ROE", roa: "ROA", operating_margin: "Margen op.",
  net_margin: "Margen neto", free_cash_flow: "FCF",
  revenue_growth_yoy: "Crec. ingresos", net_income_growth_yoy: "Crec. utilidad",
};

async function loadProfitability() {
  const box = $("ranking-prof");
  box.innerHTML = "<div class='skeleton' style='height:120px'></div>";
  try {
    const data = await api("/api/rankings/profitability", {
      year: state.year, semester: state.semester, sector: state.sector,
      metric: state.metric, financial: state.financial,
    });
    box.replaceChildren(rankingTable(data.ranking, METRIC_LABELS[data.metric] || data.metric,
      !state.financial));
  } catch (e) {
    box.replaceChildren(emptyState("Error: " + e.message, true));
  }
}

async function loadGrowth() {
  const box = $("ranking-growth");
  box.innerHTML = "<div class='skeleton' style='height:100px'></div>";
  try {
    const data = await api("/api/rankings/growth", {
      year: state.year, semester: state.semester, sector: state.sector, limit: 10,
    });
    box.replaceChildren(rankingTable(data.ranking, "Crec. ingresos"));
  } catch (e) { box.replaceChildren(emptyState("Error: " + e.message, true)); }
}

async function loadCash() {
  const box = $("ranking-cash");
  box.innerHTML = "<div class='skeleton' style='height:100px'></div>";
  try {
    const data = await api("/api/rankings/cash-flow", {
      year: state.year, semester: state.semester, limit: 10,
    });
    if (!data.ranking.length) { box.replaceChildren(emptyState("Datos insuficientes.")); return; }
    const body = data.ranking.map((r) => el("tr", {},
      el("td", {}, String(r.position)),
      el("td", {}, el("a", { href: `/empresas/${r.companyId}` }, r.company)),
      el("td", { class: "num" }, r.fcf.displayValue),
      el("td", { class: "num" }, r.fcfMargin.displayValue),
      el("td", { class: "num" }, r.cashConversion.displayValue)));
    box.replaceChildren(el("div", { class: "table-wrap" }, el("table", {},
      el("thead", {}, el("tr", {},
        el("th", {}, "#"), el("th", {}, "Empresa"),
        el("th", { class: "num" }, "FCF"), el("th", { class: "num" }, "Margen FCF"),
        el("th", { class: "num" }, "Conversión"))),
      el("tbody", {}, body))));
  } catch (e) { box.replaceChildren(emptyState("Error: " + e.message, true)); }
}

async function loadAlerts() {
  const box = $("alerts-list");
  box.innerHTML = "<div class='skeleton' style='height:80px'></div>";
  try {
    const data = await api("/api/rankings/alerts", { year: state.year, semester: state.semester });
    if (!data.companies.length) { box.replaceChildren(emptyState("Sin alertas para el periodo seleccionado.")); return; }
    const wrap = el("div", { class: "table-wrap" });
    const body = data.companies.slice(0, 15).map((c) => el("tr", {},
      el("td", {}, el("a", { href: `/empresas/${c.id}` }, c.name)),
      el("td", {}, c.sector),
      el("td", { class: "num" }, String(c.highCount)),
      el("td", {}, c.alerts.map((a) => a.title).join("; "))));
    wrap.append(el("table", {}, el("thead", {}, el("tr", {},
      el("th", {}, "Empresa"), el("th", {}, "Sector"),
      el("th", { class: "num" }, "Severas"), el("th", {}, "Alertas"))),
      el("tbody", {}, body)));
    box.replaceChildren(wrap);
  } catch (e) { box.replaceChildren(emptyState("Error: " + e.message, true)); }
}

init();

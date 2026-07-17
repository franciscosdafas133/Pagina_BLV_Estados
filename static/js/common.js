// Utilidades compartidas del frontend (sin dependencias externas).

export async function api(path, params = {}) {
  const url = new URL(path, window.location.origin);
  Object.entries(params).forEach(([k, v]) => {
    if (v !== null && v !== undefined && v !== "") url.searchParams.set(k, v);
  });
  const res = await fetch(url);
  if (!res.ok) {
    let detail = res.statusText;
    try { detail = (await res.json()).detail || detail; } catch (_) {}
    throw new Error(detail);
  }
  return res.json();
}

export async function apiPost(path, params = {}) {
  const url = new URL(path, window.location.origin);
  Object.entries(params).forEach(([k, v]) => {
    if (v !== null && v !== undefined && v !== "") url.searchParams.set(k, v);
  });
  const res = await fetch(url, { method: "POST" });
  if (!res.ok) {
    let detail = res.statusText;
    try { detail = (await res.json()).detail || detail; } catch (_) {}
    throw new Error(detail);
  }
  return res.json();
}

export function loadingScreen(title, subtitle) {
  return el("div", { class: "loading-screen" },
    el("div", { class: "spinner" }),
    el("div", { class: "loading-title" }, title),
    el("div", { class: "loading-sub" }, subtitle || ""));
}

export function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === "class") node.className = v;
    else if (k === "html") node.innerHTML = v;
    else if (k.startsWith("on") && typeof v === "function") node.addEventListener(k.slice(2), v);
    else if (v !== null && v !== undefined) node.setAttribute(k, v);
  }
  for (const c of children.flat()) {
    if (c == null) continue;
    node.append(c.nodeType ? c : document.createTextNode(String(c)));
  }
  return node;
}

export function debounce(fn, ms = 250) {
  let t;
  return (...args) => { clearTimeout(t); t = setTimeout(() => fn(...args), ms); };
}

// Query params <-> estado (para que los filtros se reflejen en la URL)
export function readParams() {
  return Object.fromEntries(new URLSearchParams(window.location.search));
}
export function writeParams(state) {
  const p = new URLSearchParams();
  Object.entries(state).forEach(([k, v]) => {
    if (v !== null && v !== undefined && v !== "" && v !== false) p.set(k, v);
  });
  const qs = p.toString();
  history.replaceState(null, "", qs ? `?${qs}` : window.location.pathname);
}

export const STATUS_META = {
  good: { label: "Bueno", icon: "▲" },
  medium: { label: "Intermedio", icon: "●" },
  risky: { label: "Riesgoso", icon: "▼" },
  not_significant: { label: "No significativo", icon: "–" },
};
export const TREND_META = {
  improving: { label: "Mejorando", icon: "↑", cls: "delta-up" },
  stable: { label: "Estable", icon: "→", cls: "" },
  worsening: { label: "Empeorando", icon: "↓", cls: "delta-down" },
};

export function statusBadge(status) {
  if (!status) return el("span", { class: "badge neutral" }, "– Sin umbral");
  const m = STATUS_META[status] || STATUS_META.not_significant;
  const cls = status === "good" ? "good" : status === "risky" ? "risky"
    : status === "medium" ? "medium" : "neutral";
  return el("span", { class: `badge ${cls}` }, `${m.icon} ${m.label}`);
}

export function trendText(trend, change, unit) {
  if (!trend) return el("span", { class: "kpi-change" }, "Sin comparación interanual");
  const m = TREND_META[trend];
  let ch = "";
  if (change !== null && change !== undefined) {
    const sign = change >= 0 ? "+" : "";
    ch = unit === "percent" ? ` (${sign}${(change * 100).toFixed(1)} pp)`
      : ` (${sign}${change.toFixed(2)})`;
  }
  return el("span", { class: `kpi-change ${m.cls}` }, `${m.icon} ${m.label}${ch}`);
}

export function tooltip(label, formula, explain) {
  return el("span", { class: "tip" },
    el("span", { class: "tip-icon", tabindex: "0", "aria-label": `Ayuda: ${label}` }, "?"),
    el("span", { class: "tip-body" },
      explain || "",
      formula ? el("span", { class: "formula" }, `Fórmula: ${formula}`) : null));
}

export function skeletonCards(n = 8) {
  const wrap = el("div", { class: "cards" });
  for (let i = 0; i < n; i++) {
    wrap.append(el("div", { class: "card" },
      el("div", { class: "skeleton", style: "width:50%" }),
      el("div", { class: "skeleton", style: "height:32px;margin:8px 0" }),
      el("div", { class: "skeleton", style: "width:70%" })));
  }
  return wrap;
}

export function emptyState(msg, isError = false) {
  return el("div", { class: `empty-state ${isError ? "error-state" : ""}` }, msg);
}

export function semesterLabel(s) {
  return s === 1 ? "1er semestre" : s === 2 ? "2do semestre" : "Anual";
}

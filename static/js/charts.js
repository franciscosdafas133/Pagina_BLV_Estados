// Gráficos SVG mínimos, sin librerías. Un solo eje por gráfico (nunca dual).
// Barras: extremos redondeados 4px anclados a la base, hueco de 2px entre barras.
// Líneas: 2px, marcadores >=8px, crosshair + tooltip en hover.
import { el } from "./common.js";

const CSS = getComputedStyle(document.documentElement);
function color(name, fallback) { return (CSS.getPropertyValue(name).trim() || fallback); }

let tooltipNode = null;
function showTip(x, y, html) {
  if (!tooltipNode) {
    tooltipNode = el("div", { class: "chart-tooltip" });
    document.body.append(tooltipNode);
  }
  tooltipNode.innerHTML = html;
  tooltipNode.style.left = `${x}px`;
  tooltipNode.style.top = `${y}px`;
  tooltipNode.style.display = "block";
}
function hideTip() { if (tooltipNode) tooltipNode.style.display = "none"; }

const NS = "http://www.w3.org/2000/svg";
function svgEl(tag, attrs = {}) {
  const n = document.createElementNS(NS, tag);
  for (const [k, v] of Object.entries(attrs)) n.setAttribute(k, v);
  return n;
}

// series: [{label, value, display}]; unit para formatear el tooltip
export function barChart(series, { unit = "money", height = 190 } = {}) {
  const W = 480, H = height, padL = 12, padR = 12, padB = 34, padT = 12;
  const values = series.map((s) => s.value).filter((v) => v !== null && v !== undefined);
  if (!values.length) return el("div", { class: "empty-state" }, "Sin datos para graficar");
  const svg = svgEl("svg", { viewBox: `0 0 ${W} ${H}`, class: "chart-svg", preserveAspectRatio: "none" });

  const max = Math.max(...values, 0), min = Math.min(...values, 0);
  const span = (max - min) || 1;
  const plotH = H - padB - padT;
  const zeroY = padT + (max / span) * plotH;
  const n = series.length;
  const gap = 6;
  const bw = (W - padL - padR - gap * (n - 1)) / n;

  // línea base cero
  svg.append(svgEl("line", { x1: padL, x2: W - padR, y1: zeroY, y2: zeroY,
    stroke: color("--baseline", "#c3c2b7"), "stroke-width": 1 }));

  series.forEach((s, i) => {
    if (s.value === null || s.value === undefined) return;
    const x = padL + i * (bw + gap);
    const h = Math.abs(s.value) / span * plotH;
    const y = s.value >= 0 ? zeroY - h : zeroY;
    const fill = s.value >= 0 ? color("--series-1", "#2a78d6") : color("--critical", "#d03b3b");
    const rect = svgEl("rect", { x, y, width: bw, height: Math.max(h, 1), rx: 3, ry: 3, fill });
    rect.addEventListener("mousemove", (e) =>
      showTip(e.clientX, e.clientY, `<b>${s.label}</b><br>${s.display}`));
    rect.addEventListener("mouseleave", hideTip);
    svg.append(rect);
    // etiqueta del eje x
    const t = svgEl("text", { x: x + bw / 2, y: H - 10, "text-anchor": "middle",
      "font-size": 10, fill: color("--muted", "#898781") });
    t.textContent = s.label;
    svg.append(t);
  });
  return svg;
}

// Línea temporal con marcadores y crosshair
export function lineChart(series, { unit = "percent", height = 190 } = {}) {
  const pts = series.filter((s) => s.value !== null && s.value !== undefined);
  if (pts.length < 2) return el("div", { class: "empty-state" }, "Se requieren al menos 2 periodos");
  const W = 480, H = height, padL = 12, padR = 12, padB = 34, padT = 12;
  const svg = svgEl("svg", { viewBox: `0 0 ${W} ${H}`, class: "chart-svg", preserveAspectRatio: "none" });
  const values = pts.map((s) => s.value);
  const max = Math.max(...values), min = Math.min(...values);
  const span = (max - min) || 1;
  const plotH = H - padB - padT, plotW = W - padL - padR;
  const X = (i) => padL + (i / (series.length - 1)) * plotW;
  const Y = (v) => padT + (1 - (v - min) / span) * plotH;

  if (min < 0 && max > 0) {
    svg.append(svgEl("line", { x1: padL, x2: W - padR, y1: Y(0), y2: Y(0),
      stroke: color("--baseline", "#c3c2b7"), "stroke-width": 1, "stroke-dasharray": "3 3" }));
  }
  let d = "";
  series.forEach((s, i) => {
    if (s.value === null || s.value === undefined) return;
    d += (d ? " L" : "M") + `${X(i).toFixed(1)},${Y(s.value).toFixed(1)}`;
  });
  svg.append(svgEl("path", { d, fill: "none", stroke: color("--series-1", "#2a78d6"), "stroke-width": 2 }));

  series.forEach((s, i) => {
    if (s.value === null || s.value === undefined) return;
    const c = svgEl("circle", { cx: X(i), cy: Y(s.value), r: 4.5,
      fill: color("--surface", "#fff"), stroke: color("--series-1", "#2a78d6"), "stroke-width": 2 });
    c.addEventListener("mousemove", (e) =>
      showTip(e.clientX, e.clientY, `<b>${s.label}</b><br>${s.display}`));
    c.addEventListener("mouseleave", hideTip);
    svg.append(c);
    if (i % Math.ceil(series.length / 6) === 0 || i === series.length - 1) {
      const t = svgEl("text", { x: X(i), y: H - 10, "text-anchor": "middle",
        "font-size": 10, fill: color("--muted", "#898781") });
      t.textContent = s.label;
      svg.append(t);
    }
  });
  return svg;
}

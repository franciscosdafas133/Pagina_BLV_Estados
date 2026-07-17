// Buscador con autocompletado, debounce y navegación a la ficha.
import { api, el, debounce } from "./common.js";

export function mountSearch(container) {
  const input = el("input", {
    type: "search", placeholder: "Buscar empresa por nombre, ticker o RUC…",
    autocomplete: "off", "aria-label": "Buscar empresa",
  });
  const results = el("div", { class: "autocomplete", style: "display:none" });
  const wrap = el("div", { class: "search-wrap" }, input, results);
  container.append(wrap);

  let items = [];
  let active = -1;

  function close() { results.style.display = "none"; active = -1; }
  function open() { if (results.children.length) results.style.display = "block"; }

  const run = debounce(async () => {
    const q = input.value.trim();
    if (q.length < 2) { close(); return; }
    try {
      const data = await api("/api/companies", { search: q, limit: 8 });
      items = data.companies;
      results.replaceChildren();
      if (!items.length) {
        results.append(el("div", { class: "empty" }, "Sin resultados para tu búsqueda"));
      } else {
        items.forEach((c, i) => {
          results.append(el("div", {
            class: "item", "data-i": i,
            onclick: () => { window.location.href = `/empresas/${c.id}`; },
          },
            el("span", {}, c.ticker ? `${c.name} (${c.ticker})` : c.name),
            el("span", { class: "sec" }, c.sector)));
        });
      }
      open();
    } catch (_) { close(); }
  }, 250);

  input.addEventListener("input", run);
  input.addEventListener("focus", () => { if (input.value.trim().length >= 2) open(); });
  input.addEventListener("keydown", (e) => {
    const nodes = [...results.querySelectorAll(".item")];
    if (e.key === "ArrowDown") { e.preventDefault(); active = Math.min(active + 1, nodes.length - 1); }
    else if (e.key === "ArrowUp") { e.preventDefault(); active = Math.max(active - 1, 0); }
    else if (e.key === "Enter" && active >= 0 && items[active]) {
      window.location.href = `/empresas/${items[active].id}`;
    } else if (e.key === "Escape") { close(); return; }
    nodes.forEach((n, i) => n.classList.toggle("active", i === active));
  });
  document.addEventListener("click", (e) => { if (!wrap.contains(e.target)) close(); });
  return input;
}

async function loadBulletins() {
  const res = await fetch("data/boletines.json", { cache: "no-store" });
  if (!res.ok) return [];
  return res.json();
}

function formatPeriod(start, end) {
  const fmt = (iso) => {
    const [y, m, d] = iso.split("-");
    return `${d}/${m}/${y}`;
  };
  return `${fmt(start)} – ${fmt(end)}`;
}

function render(items, themeFilter) {
  const list = document.getElementById("list");
  const empty = document.getElementById("empty");
  const count = document.getElementById("count");
  const filtered =
    themeFilter === "all"
      ? items
      : items.filter((i) => i.theme_id === themeFilter);

  count.textContent = `${filtered.length} boletín${filtered.length === 1 ? "" : "es"}`;
  list.innerHTML = "";

  if (!filtered.length) {
    empty.classList.remove("hidden");
    return;
  }
  empty.classList.add("hidden");

  for (const item of filtered) {
    const card = document.createElement("article");
    card.className = "card";

    const localHref = item.pdf_local || "";
    const driveHref = item.drive_view_link || "";
    const primaryHref = localHref || driveHref;
    const primaryLabel = localHref ? "Ver PDF" : "Ver en Drive";

    card.innerHTML = `
      <span class="chip">${item.theme_label || item.theme_id}</span>
      <h2>${item.theme_title || "Boletín"}</h2>
      <p>Periodo ${formatPeriod(item.periodo_inicio, item.periodo_fin)} · ${item.noticias || "?"} noticias</p>
      <p>Generado ${item.generado_el || ""}${item.author ? ` · ${item.author}` : ""}</p>
      <div class="actions">
        ${
          primaryHref
            ? `<a class="primary" href="${primaryHref}" target="_blank" rel="noopener">${primaryLabel}</a>`
            : ""
        }
        ${
          localHref && driveHref
            ? `<a href="${driveHref}" target="_blank" rel="noopener">Abrir en Drive</a>`
            : ""
        }
      </div>
    `;
    list.appendChild(card);
  }
}

function fillThemeFilter(items) {
  const select = document.getElementById("theme-filter");
  const themes = [...new Set(items.map((i) => i.theme_id).filter(Boolean))];
  for (const t of themes) {
    const opt = document.createElement("option");
    opt.value = t;
    opt.textContent = t;
    select.appendChild(opt);
  }
  select.addEventListener("change", () => render(items, select.value));
}

(async () => {
  const items = await loadBulletins();
  if (items[0]?.author) {
    document.getElementById("author-line").textContent = `Por ${items[0].author}`;
  }
  fillThemeFilter(items);
  render(items, "all");
})();

function initTable() {
  document.getElementById("btn-copy-selected").addEventListener("click", copySelected);
  document.getElementById("btn-export-csv").addEventListener("click", exportCSV);
  document.getElementById("btn-toggle-columns").addEventListener("click", () => {
    const el = document.getElementById("column-chooser");
    el.style.display = el.style.display === "none" ? "" : "none";
  });
  document.getElementById("btn-font-down").addEventListener("click", () => changeFontSize(-1));
  document.getElementById("btn-font-up").addEventListener("click", () => changeFontSize(1));
  document.getElementById("search-input").addEventListener("input", handleSearch);
  document.getElementById("result-table").addEventListener("click", handleTableClick);
  document.getElementById("result-table").addEventListener("change", handleTableChange);
  document.getElementById("result-table").addEventListener("input", handleTableInput);
  document.getElementById("table-container").addEventListener("change", e => {
    if (e.target.dataset.col) toggleColumn(e.target.dataset.col);
  });
  loadPrefs();
}

function renderTable(response) {
  state.columns = response.columns;
  state.rows = response.rows;
  const oldVis = state.columnVisibility;
  state.columnVisibility = Object.fromEntries(
    response.columns.map(col => [col, oldVis[col]])
  );
  state.sortCol = null;
  state.sortDir = "asc";
  state.rowSelect = {};
  state.ratings = {};
  state.searchText = "";
  document.getElementById("search-input").value = "";
  renderColumnChooser();
  renderTableContent();
}

function renderColumnChooser() {
  const el = document.getElementById("column-chooser");
  el.innerHTML = state.columns.map(col => {
    const hidden = state.columnVisibility[col] === false;
    return `<label><input type="checkbox"${hidden ? "" : " checked"} data-col="${col}"> ${col}</label>`;
  }).join("");
}

function getVisibleColumns() {
  return state.columns.filter(col => state.columnVisibility[col] !== false);
}

function getFilteredRows() {
  if (!state.searchText) return state.rows;
  const q = state.searchText.toLowerCase();
  const visibleCols = getVisibleColumns();
  return state.rows.filter(row =>
    visibleCols.some(col => {
      const v = row[col];
      return v != null && String(v).toLowerCase().includes(q);
    })
  );
}

function getSortedRows(rows) {
  if (!state.sortCol) return rows;
  const col = state.sortCol;
  const dir = state.sortDir === "asc" ? 1 : -1;
  return [...rows].sort((a, b) => {
    const va = a[col], vb = b[col];
    if (va == null) return 1;
    if (vb == null) return -1;
    if (typeof va === "string") return dir * va.localeCompare(vb);
    return dir * (va - vb);
  });
}

function renderTableContent() {
  renderTableHeader();
  renderTableBody();
  updateResultCount();
}

function renderTableHeader() {
  const thead = document.querySelector("#result-table thead");
  const visibleCols = getVisibleColumns();
  const cols = ["checkbox", "rating", "notes", ...visibleCols];

  thead.innerHTML = `<tr>${cols.map(col => {
    if (col === "checkbox") return '<th class="cb">&#x2611;</th>';
    if (col === "rating") return '<th class="cb">&#x2605;</th>';
    if (col === "notes") return '<th class="notes-th">Notes</th>';
    const arrow = state.sortCol === col ? (state.sortDir === "asc" ? " &#x25B2;" : " &#x25BC;") : "";
    return `<th data-col="${col}">${col}${arrow}</th>`;
  }).join("")}</tr>`;
}

function renderTableBody() {
  const tbody = document.querySelector("#result-table tbody");
  const visibleCols = getVisibleColumns();
  const filtered = getFilteredRows();
  const sorted = getSortedRows(filtered);
  const colspan = visibleCols.length + 3;

  if (sorted.length === 0) {
    tbody.innerHTML = '<tr><td colspan="' + colspan + '" style="text-align:center;color:#999;padding:20px;">No results</td></tr>';
    return;
  }

  tbody.innerHTML = sorted.map(row => {
    const origIdx = state.rows.indexOf(row);
    const checked = state.rowSelect[origIdx] ? "checked" : "";
    const rating = state.ratings[origIdx] || 0;
    const stars = "\u2605".repeat(rating) + "\u2606".repeat(5 - rating);
    const note = state.rowNotes[origIdx] || "";

    const cells = visibleCols.map(col => {
      const v = row[col];
      const display = (v != null && typeof v === "number" && !Number.isInteger(v) && col !== "sl" && col !== "tp")
        ? v.toFixed(1)
        : v;
      return `<td>${display == null ? "" : display}</td>`;
    }).join("");

    return `<tr data-idx="${origIdx}">
      <td class="cb"><input type="checkbox" class="row-cb" ${checked}></td>
      <td class="star" data-rating="${rating}">${stars}</td>
      <td class="notes-cell"><input class="note-input" type="text" value="${note.replace(/"/g, '&quot;')}" placeholder="..."></td>
      ${cells}
    </tr>`;
  }).join("");
}

function handleTableClick(e) {
  if (e.target.tagName === "TH" && e.target.dataset.col) {
    toggleSort(e.target.dataset.col);
    return;
  }

  const tr = e.target.closest("tr");
  if (!tr) return;
  const idx = parseInt(tr.dataset.idx);
  if (isNaN(idx)) return;

  if (e.target.classList.contains("star")) {
    const rect = e.target.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const starW = rect.width / 5;
    const stars = Math.min(5, Math.max(0, Math.floor(x / starW) + 1));
    const current = state.ratings[idx] || 0;
    setRating(idx, stars === current ? 0 : stars);
  }
}

function handleTableChange(e) {
  const tr = e.target.closest("tr");
  if (!tr) return;
  const idx = parseInt(tr.dataset.idx);
  if (isNaN(idx)) return;

  if (e.target.classList.contains("row-cb")) {
    state.rowSelect[idx] = e.target.checked;
    state.dirty = true;
    updateDirtyIndicator();
  }
}

function handleTableInput(e) {
  const tr = e.target.closest("tr");
  if (!tr) return;
  const idx = parseInt(tr.dataset.idx);
  if (isNaN(idx)) return;

  if (e.target.classList.contains("note-input")) {
    state.rowNotes[idx] = e.target.value;
    state.dirty = true;
    updateDirtyIndicator();
  }
}

function toggleSort(col) {
  if (state.sortCol === col) {
    state.sortDir = state.sortDir === "asc" ? "desc" : "asc";
  } else {
    state.sortCol = col;
    state.sortDir = "asc";
  }
  renderTableContent();
}

function toggleColumn(col) {
  state.columnVisibility[col] = state.columnVisibility[col] === false ? true : false;
  renderColumnChooser();
  renderTableContent();
  savePrefs();
}

function handleSearch() {
  state.searchText = document.getElementById("search-input").value;
  renderTableBody();
  updateResultCount();
}

function setRating(idx, stars) {
  state.ratings[idx] = stars;
  state.dirty = true;
  updateDirtyIndicator();
  renderTableBody();
}

function getSelectedRows() {
  const visibleCols = getVisibleColumns();
  const sorted = getSortedRows(getFilteredRows());
  return sorted
    .filter(row => {
      const idx = state.rows.indexOf(row);
      return state.rowSelect[idx];
    })
    .map(row => {
      const obj = {};
      visibleCols.forEach(col => { obj[col] = row[col]; });
      return obj;
    });
}

function csvEscape(v) {
  if (v == null) return "";
  const s = String(v);
  if (s.includes(",") || s.includes('"') || s.includes("\n")) {
    return '"' + s.replace(/"/g, '""') + '"';
  }
  return s;
}

function tsvEscape(v) {
  if (v == null) return "";
  const s = String(v);
  if (s.includes("\t") || s.includes("\n") || s.includes('"')) {
    return '"' + s.replace(/"/g, '""') + '"';
  }
  return s;
}

function buildFilename() {
  const now = new Date();
  const ts = now.getFullYear() +
    String(now.getMonth() + 1).padStart(2, "0") +
    String(now.getDate()).padStart(2, "0") + "_" +
    String(now.getHours()).padStart(2, "0") +
    String(now.getMinutes()).padStart(2, "0") +
    String(now.getSeconds()).padStart(2, "0");
  const tfs = (state.selectedTimeframes || []).join("_");
  const mode = state.mode || "normal";
  let symbol = "BTCUSD";
  if (state.lastRunPayload) symbol = state.lastRunPayload.symbol;
  return symbol + "_" + mode + (tfs ? "_" + tfs : "") + "_" + ts + ".csv";
}

function copySelected() {
  const rows = getSelectedRows();
  if (rows.length === 0) { showStatus("No rows selected"); return; }
  const cols = getVisibleColumns();
  const lines = rows.map(row => cols.map(col => tsvEscape(row[col])).join("\t"));
  const tsv = cols.join("\t") + "\n" + lines.join("\n");

  navigator.clipboard.writeText(tsv).then(() => {
    showStatus("Copied " + rows.length + " rows");
  }).catch(() => {
    const ta = document.createElement("textarea");
    ta.value = tsv;
    document.body.appendChild(ta);
    ta.select();
    document.execCommand("copy");
    ta.remove();
    showStatus("Copied " + rows.length + " rows");
  });
}

function exportCSV() {
  const cols = getVisibleColumns();
  const reviewCols = ["selected", "rating", "note"];
  const allCols = [...cols, ...reviewCols];
  const filtered = getFilteredRows();
  const sorted = getSortedRows(filtered);
  const rows = sorted.map(row => {
    const origIdx = state.rows.indexOf(row);
    const dataCells = cols.map(col => csvEscape(row[col]));
    const sel = state.rowSelect[origIdx] ? "yes" : "";
    const rating = state.ratings[origIdx] || "";
    const note = state.rowNotes[origIdx] || "";
    const reviewCells = [sel, rating, note].map(csvEscape);
    return [...dataCells, ...reviewCells].join(",");
  }).join("\n");
  const csv = allCols.join(",") + "\n" + rows.join("\n");

  const blob = new Blob(["\ufeff" + csv], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = buildFilename();
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
  showStatus("CSV exported");
}

function changeFontSize(delta) {
  state.fontSize = Math.max(9, Math.min(24, state.fontSize + delta));
  document.getElementById("result-table").style.fontSize = state.fontSize + "px";
  savePrefs();
}

function savePrefs() {
  try {
    localStorage.setItem("my-backtest.columnVisibility", JSON.stringify(state.columnVisibility));
    localStorage.setItem("my-backtest.tableFontSize", String(state.fontSize));
  } catch (_) {}
}

function loadPrefs() {
  try {
    const cv = localStorage.getItem("my-backtest.columnVisibility");
    if (cv) {
      const parsed = JSON.parse(cv);
      if (typeof parsed === "object" && !Array.isArray(parsed)) {
        Object.assign(state.columnVisibility, parsed);
      }
    }
    const fs = localStorage.getItem("my-backtest.tableFontSize");
    if (fs) {
      const n = parseInt(fs, 10);
      if (!isNaN(n) && n >= 9 && n <= 24) state.fontSize = n;
    }
    document.getElementById("result-table").style.fontSize = state.fontSize + "px";
  } catch (_) {}
}

function updateResultCount() {
  const filteredCount = state.searchText ? getFilteredRows().length : state.rows.length;
  document.getElementById("result-count").textContent =
    filteredCount + " / " + state.rows.length + " rows";
}

function initTable() {
  document.getElementById("btn-save").addEventListener("click", () => {
    alert("Save will be implemented in Phase 4");
  });
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
  document.getElementById("table-container").addEventListener("change", e => {
    if (e.target.dataset.col) toggleColumn(e.target.dataset.col);
  });
}

function renderTable(response) {
  state.columns = response.columns;
  state.rows = response.rows;
  state.columnVisibility = {};
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
  el.innerHTML = state.columns.map(col =>
    `<label><input type="checkbox" checked data-col="${col}"> ${col}</label>`
  ).join("");
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
  const cols = ["checkbox", "rating", ...visibleCols];

  thead.innerHTML = `<tr>${cols.map(col => {
    if (col === "checkbox") return '<th class="cb">&#x2611;</th>';
    if (col === "rating") return '<th class="cb">&#x2605;</th>';
    const arrow = state.sortCol === col ? (state.sortDir === "asc" ? " &#x25B2;" : " &#x25BC;") : "";
    return `<th data-col="${col}">${col}${arrow}</th>`;
  }).join("")}</tr>`;
}

function renderTableBody() {
  const tbody = document.querySelector("#result-table tbody");
  const visibleCols = getVisibleColumns();
  const filtered = getFilteredRows();
  const sorted = getSortedRows(filtered);

  if (sorted.length === 0) {
    tbody.innerHTML = '<tr><td colspan="' + (visibleCols.length + 2) + '" style="text-align:center;color:#999;padding:20px;">No results</td></tr>';
    return;
  }

  tbody.innerHTML = sorted.map(row => {
    const origIdx = state.rows.indexOf(row);
    const checked = state.rowSelect[origIdx] ? "checked" : "";
    const rating = state.ratings[origIdx] || 0;
    const stars = "\u2605".repeat(rating) + "\u2606".repeat(5 - rating);

    const cells = visibleCols.map(col => {
      const v = row[col];
      return `<td>${v == null ? "" : v}</td>`;
    }).join("");

    return `<tr data-idx="${origIdx}">
      <td class="cb"><input type="checkbox" class="row-cb" ${checked}></td>
      <td class="star" data-rating="${rating}">${stars}</td>
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
    const stars = Math.min(5, Math.max(1, Math.floor(x / starW) + 1));
    setRating(idx, stars);
  }
}

function handleTableChange(e) {
  const tr = e.target.closest("tr");
  if (!tr) return;
  const idx = parseInt(tr.dataset.idx);
  if (isNaN(idx)) return;

  if (e.target.classList.contains("row-cb")) {
    state.rowSelect[idx] = e.target.checked;
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
}

function handleSearch() {
  state.searchText = document.getElementById("search-input").value;
  renderTableBody();
  updateResultCount();
}

function setRating(idx, stars) {
  state.ratings[idx] = stars;
  renderTableBody();
}

function getSelectedRows() {
  const visibleCols = getVisibleColumns();
  return state.rows
    .map((row, idx) => ({ row, idx }))
    .filter(({ idx }) => state.rowSelect[idx])
    .map(({ row }) => {
      const obj = {};
      visibleCols.forEach(col => { obj[col] = row[col]; });
      return obj;
    });
}

function copySelected() {
  const rows = getSelectedRows();
  if (rows.length === 0) { alert("No rows selected"); return; }
  const cols = getVisibleColumns();
  const lines = rows.map(row => cols.map(col => row[col] ?? "").join("\t"));
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
  const rows = state.rows.map(row => cols.map(col => {
    const v = row[col];
    if (v == null) return "";
    const s = String(v);
    return s.includes(",") || s.includes('"') || s.includes("\n")
      ? '"' + s.replace(/"/g, '""') + '"'
      : s;
  }).join(","));
  const csv = cols.join(",") + "\n" + rows.join("\n");

  const blob = new Blob(["\ufeff" + csv], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = "backtest_results.csv";
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
  showStatus("CSV exported");
}

function changeFontSize(delta) {
  state.fontSize = Math.max(9, Math.min(24, state.fontSize + delta));
  document.getElementById("result-table").style.fontSize = state.fontSize + "px";
}

function updateResultCount() {
  const filteredCount = state.searchText ? getFilteredRows().length : state.rows.length;
  document.getElementById("result-count").textContent =
    filteredCount + " / " + state.rows.length + " rows";
}

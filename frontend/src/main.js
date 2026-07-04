async function init() {
  try {
    const opts = await fetchOptions();
    state.timeframes = opts.timeframes;
    state.strategies = opts.indicators;
    state.filterFields = opts.filter_fields;
    state.operators = opts.operators;
    populateFilterAddControls();
    renderAll();
    initTable();
    bindEvents();
  } catch (e) {
    showError("Failed to load options: " + e.message);
  }
}

function renderAll() {
  renderTimeframes();
  renderStrategies();
  renderSelected();
  renderFilters();
  updateRunButton();
}

function renderTimeframes() {
  const el = document.getElementById("timeframe-list");
  el.innerHTML = state.timeframes.map(tf =>
    `<div class="item${state.selectedTimeframes.includes(tf) ? " selected" : ""}" data-value="${tf}">${tf}</div>`
  ).join("");
}

function renderStrategies() {
  const el = document.getElementById("strategy-list");
  el.innerHTML = state.strategies.map(s =>
    `<div class="item${state.selectedStrategies.includes(s) ? " selected" : ""}" data-value="${s}">${s}</div>`
  ).join("");
}

function renderSelected() {
  const tfEl = document.getElementById("selected-timeframes");
  tfEl.innerHTML = state.selectedTimeframes.length === 0
    ? '<span class="placeholder" style="color:#999;font-size:11px;">Click timeframes to add</span>'
    : state.selectedTimeframes.map(tf =>
        `<span class="selected-tag">${tf} <span class="remove" data-tf="${tf}">&times;</span></span>`
      ).join("");

  const sEl = document.getElementById("selected-strategies");
  sEl.innerHTML = state.selectedStrategies.length === 0
    ? '<span class="placeholder" style="color:#999;font-size:11px;">Click strategies to add</span>'
    : state.selectedStrategies.map(s =>
        `<span class="selected-tag">${s} <span class="remove" data-strat="${s}">&times;</span></span>`
      ).join("");
}

function renderFilters() {
  const el = document.getElementById("filter-list");
  el.innerHTML = state.filters.map((f, i) => `
    <div class="filter-row" data-idx="${i}">
      <select class="field-sel">
        <option value="">field</option>
        ${state.filterFields.map(ff => `<option value="${ff}"${ff === f.field ? " selected" : ""}>${ff}</option>`).join("")}
      </select>
      <select class="op-sel">
        <option value="">op</option>
        ${state.operators.map(op => `<option value="${op}"${op === f.op ? " selected" : ""}>${op}</option>`).join("")}
      </select>
      <input class="val-inp" type="text" value="${f.value}">
      <button class="btn-remove" data-idx="${i}">&times;</button>
    </div>
  `).join("");
}

function populateFilterAddControls() {
  const fieldSel = document.getElementById("filter-field-add");
  fieldSel.innerHTML = '<option value="">field</option>' +
    state.filterFields.map(f => `<option value="${f}">${f}</option>`).join("");

  const opSel = document.getElementById("filter-op-add");
  opSel.innerHTML = '<option value="">op</option>' +
    state.operators.map(o => `<option value="${o}">${o}</option>`).join("");
}

function updateRunButton() {
  const btn = document.getElementById("btn-run");
  const statusText = document.getElementById("status-text");
  btn.disabled = state.selectedTimeframes.length === 0 || state.loading;
  btn.textContent = state.loading ? "Running..." : "Run Backtest";
  if (state.loading) {
    statusText.textContent = "Running backtest...";
  }
}

function showStatus(msg) {
  document.getElementById("status-text").textContent = msg;
}

function showError(msg) {
  const el = document.getElementById("status-error");
  el.textContent = msg;
}

function hideError() {
  document.getElementById("status-error").textContent = "";
}

function toggleTimeframe(tf) {
  const idx = state.selectedTimeframes.indexOf(tf);
  if (idx >= 0) {
    state.selectedTimeframes.splice(idx, 1);
  } else {
    state.selectedTimeframes.push(tf);
  }
  renderTimeframes();
  renderSelected();
  updateRunButton();
}

function toggleStrategy(s) {
  const idx = state.selectedStrategies.indexOf(s);
  if (idx >= 0) {
    state.selectedStrategies.splice(idx, 1);
  } else {
    state.selectedStrategies.push(s);
  }
  renderStrategies();
  renderSelected();
  updateRunButton();
}

function clearSelected() {
  state.selectedTimeframes.length = 0;
  state.selectedStrategies.length = 0;
  renderAll();
}

function handleFilterChange(e) {
  const row = e.target.closest(".filter-row");
  if (!row) return;
  const idx = parseInt(row.dataset.idx);
  if (e.target.classList.contains("field-sel")) state.filters[idx].field = e.target.value;
  else if (e.target.classList.contains("op-sel")) state.filters[idx].op = e.target.value;
  else if (e.target.classList.contains("val-inp")) state.filters[idx].value = e.target.value;
}

function addFilter() {
  const field = document.getElementById("filter-field-add").value;
  const op = document.getElementById("filter-op-add").value;
  const value = document.getElementById("filter-value-add").value;
  if (!field || !op) return;
  state.filters.push({ field, op, value });
  renderFilters();
}

function removeFilter(idx) {
  state.filters.splice(idx, 1);
  renderFilters();
}

async function handleRun() {
  if (state.selectedTimeframes.length === 0) {
    showError("Select at least one timeframe");
    return;
  }
  setState({ loading: true });
  hideError();
  updateRunButton();

  try {
    const filters = state.filters.map(f => ({
      field: f.field,
      op: f.op,
      value: isNaN(Number(f.value)) ? f.value : Number(f.value),
    }));

    const payload = {
      symbol: "BTCUSD",
      timeframes: state.selectedTimeframes,
      mode: state.mode,
      strategies: state.selectedStrategies.length > 0 ? state.selectedStrategies : null,
      filters,
      limit: 500,
    };

    const result = await runBacktestAPI(payload);
    state.columns = result.columns;
    state.rows = result.rows;
    showStatus(`Done — ${result.row_count} rows`);
    renderTable(result);
  } catch (e) {
    showError(e.message);
    showStatus("Error");
  } finally {
    setState({ loading: false });
    updateRunButton();
  }
}

function bindEvents() {
  document.getElementById("timeframe-list").addEventListener("click", e => {
    const item = e.target.closest(".item");
    if (item) toggleTimeframe(item.dataset.value);
  });

  document.getElementById("strategy-list").addEventListener("click", e => {
    const item = e.target.closest(".item");
    if (item) toggleStrategy(item.dataset.value);
  });

  document.getElementById("panel-selected").addEventListener("click", e => {
    if (!e.target.classList.contains("remove")) return;
    const tf = e.target.dataset.tf;
    if (tf) {
      state.selectedTimeframes = state.selectedTimeframes.filter(t => t !== tf);
      renderTimeframes();
      renderSelected();
      updateRunButton();
    }
    const strat = e.target.dataset.strat;
    if (strat) {
      state.selectedStrategies = state.selectedStrategies.filter(s => s !== strat);
      renderStrategies();
      renderSelected();
      updateRunButton();
    }
  });

  document.getElementById("btn-clear-selected").addEventListener("click", clearSelected);

  document.getElementById("filter-list").addEventListener("change", handleFilterChange);
  document.getElementById("filter-list").addEventListener("input", handleFilterChange);

  document.getElementById("filter-list").addEventListener("click", e => {
    if (e.target.classList.contains("btn-remove")) {
      removeFilter(parseInt(e.target.dataset.idx));
    }
  });

  document.getElementById("btn-add-filter").addEventListener("click", addFilter);

  document.querySelectorAll('input[name="mode"]').forEach(radio => {
    radio.addEventListener("change", e => {
      state.mode = e.target.value;
    });
  });

  document.getElementById("btn-run").addEventListener("click", handleRun);
}

init();

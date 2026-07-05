async function init() {
  try {
    const opts = await fetchOptions();
    state.timeframes = opts.timeframes;
    state.strategies = opts.indicators;
    state.filterFields = opts.filter_fields;
    state.operators = opts.operators;
    state.strategyParamSchemas = opts.strategy_param_schemas || {};
    state.gridParamSchema = opts.grid_param_schema || {};
    populateFilterAddControls();
    renderAll();
    initTable();
    bindEvents();
    refreshSavedRuns();
  } catch (e) {
    showError("Failed to load options: " + parseApiError(e));
  }
}

function renderAll() {
  renderTimeframes();
  renderStrategies();
  renderStrategySettings();
  renderSelected();
  renderFilters();
  renderSearchGrid();
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

function renderStrategySettings() {
  const el = document.getElementById("strategy-settings");
  const s = state.activeStrategy;
  const schema = state.strategyParamSchemas[s];
  if (!s || !schema) {
    el.innerHTML = '<div class="settings-placeholder">Click a strategy to edit</div>';
    return;
  }
  const settings = state.strategySettings[s] || {};
  let html = `<div class="settings-strat-name">${s}</div>`;
  for (const [param, meta] of Object.entries(schema)) {
    const value = settings[param] || meta.default;
    if (meta.type === "range") {
      html += `<div class="setting-row">
        <label>${param}</label>
        <div class="setting-range">
          <input type="number" class="setting-min" data-strat="${s}" data-param="${param}" value="${value[0]}" min="${meta.min}" max="${meta.max}" step="${meta.step}">
          <span>to</span>
          <input type="number" class="setting-max" data-strat="${s}" data-param="${param}" value="${value[1]}" min="${meta.min}" max="${meta.max}" step="${meta.step}">
        </div>
      </div>`;
    } else if (meta.type === "select") {
      const checkboxHtml = meta.options.map(opt =>
        `<label class="setting-checkbox">
          <input type="checkbox" data-strat="${s}" data-param="${param}" value="${opt}" ${value.includes(opt) ? "checked" : ""}>
          ${opt}
        </label>`
      ).join("");
      html += `<div class="setting-row">
        <label>${param}</label>
        <div class="setting-checkbox-group">${checkboxHtml}</div>
      </div>`;
    }
  }
  el.innerHTML = html;
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

function renderSearchGrid() {
  const el = document.getElementById("search-grid");
  const schema = state.gridParamSchema;
  if (!schema || Object.keys(schema).length === 0) {
    el.innerHTML = "";
    return;
  }
  const gs = state.gridSettings;
  const ds = state.densitySettings;
  el.innerHTML = `
    <div class="grid-row">
      <label>Profile</label>
      <select id="grid-profile">
        <option value="dense" ${gs.profile === "dense" ? "selected" : ""}>Dense</option>
        <option value="normal" ${gs.profile === "normal" ? "selected" : ""}>Normal</option>
      </select>
    </div>
    <div class="grid-row">
      <label>SL values</label>
      <input type="text" id="grid-sl" value="${gs.sl_values}" placeholder="e.g. 0.02, 0.04, 0.06">
    </div>
    <div class="grid-row">
      <label>TP values</label>
      <input type="text" id="grid-tp" value="${gs.tp_values}" placeholder="e.g. 0.005, 0.01, 0.02">
    </div>
    <div class="grid-row">
      <label>Max Hold</label>
      <input type="text" id="grid-max-hold" value="${gs.max_holds}" placeholder="e.g. 16, 32, 64">
    </div>
    <div class="grid-row">
      <label>Min trades/day</label>
      <input type="number" id="grid-mtpd" value="${ds.min_trades_per_day}" min="0.1" max="5" step="0.01">
    </div>
    <div class="grid-row">
      <label>Min test trades/day</label>
      <input type="number" id="grid-mttpd" value="${ds.min_test_trades_per_day}" min="0.1" max="5" step="0.01">
    </div>
  `;
}

function populateFilterAddControls() {
  const fieldSel = document.getElementById("filter-field-add");
  fieldSel.innerHTML = '<option value="">field</option>' +
    state.filterFields.map(f => `<option value="${f}">${f}</option>`).join("");

  const opSel = document.getElementById("filter-op-add");
  opSel.innerHTML = '<option value="">op</option>' +
    state.operators.map(o => `<option value="${o}">${o}</option>`).join("");
}

let timerInterval = null;

function updateRunButton() {
  const btn = document.getElementById("btn-run");
  const saveBtn = document.getElementById("btn-save");
  const statusText = document.getElementById("status-text");
  const loading = state.loading;
  btn.disabled = state.selectedTimeframes.length === 0 || loading;
  saveBtn.disabled = loading;
  btn.textContent = loading ? "Running..." : "Run Backtest";
  if (loading) {
    statusText.textContent = "Running backtest...";
  }
}

function startTimer() {
  state.runningStartTime = Date.now();
  const statusText = document.getElementById("status-text");
  clearInterval(timerInterval);
  timerInterval = setInterval(() => {
    if (!state.loading) { clearInterval(timerInterval); return; }
    const elapsed = ((Date.now() - state.runningStartTime) / 1000).toFixed(1);
    statusText.textContent = "Running backtest... " + elapsed + "s";
  }, 200);
}

function stopTimer() {
  clearInterval(timerInterval);
  timerInterval = null;
  state.runningStartTime = null;
}

function showStatus(msg) {
  document.getElementById("status-text").textContent = msg;
}

function updateDirtyIndicator() {
  const el = document.getElementById("dirty-indicator");
  if (el) el.textContent = state.dirty ? "unsaved" : "";
}

function parseNumberList(text) {
  if (!text || !text.trim()) return null;
  const nums = text.split(",")
    .map(s => s.trim())
    .filter(s => s !== "" && !isNaN(Number(s)))
    .map(Number);
  return nums.length > 0 ? nums : null;
}

function parseIntList(text) {
  if (!text || !text.trim()) return null;
  const nums = text.split(",")
    .map(s => s.trim())
    .filter(s => s !== "" && !isNaN(parseInt(s, 10)))
    .map(s => parseInt(s, 10));
  return nums.length > 0 ? nums : null;
}

function buildSearchParams() {
  const gs = state.gridSettings;
  const ds = state.densitySettings;
  const strategy_params = {};
  for (const [name, settings] of Object.entries(state.strategySettings)) {
    if (state.selectedStrategies.includes(name)) {
      strategy_params[name] = settings;
    }
  }
  const params = { strategy_params };
  const sl = parseNumberList(gs.sl_values);
  if (sl) params.sl_values = sl;
  const tp = parseNumberList(gs.tp_values);
  if (tp) params.tp_values = tp;
  const mh = parseIntList(gs.max_holds);
  if (mh) params.max_holds = mh;
  params.grid_profile = gs.profile;
  params.min_trades_per_day = parseFloat(ds.min_trades_per_day) || 0.33;
  params.min_test_trades_per_day = parseFloat(ds.min_test_trades_per_day) || 0.33;
  return params;
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
  state.activeStrategy = s;
  if (!state.strategySettings[s]) {
    const schema = state.strategyParamSchemas[s];
    if (schema) {
      const settings = {};
      for (const [param, meta] of Object.entries(schema)) {
        settings[param] = [...meta.default];
      }
      state.strategySettings[s] = settings;
    }
  }
  renderStrategies();
  renderStrategySettings();
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

function isHeavyRequest() {
  const tfCount = state.selectedTimeframes.length;
  const stratCount = state.selectedStrategies.length || state.strategies.length || 10;
  const mode = state.mode;
  let score = tfCount * stratCount;
  if (mode === "dense_high_winrate") score *= 2;
  return score >= 40;
}

async function handleRun() {
  if (state.selectedTimeframes.length === 0) {
    showError("Select at least one timeframe");
    return;
  }

  if (isHeavyRequest()) {
    const tfStr = state.selectedTimeframes.join(", ");
    const stratStr = state.selectedStrategies.length > 0 ? state.selectedStrategies.join(", ") : "all";
    const msg = `This request may take a while:\n\nTimeframes: ${tfStr}\nStrategies: ${stratStr}\nMode: ${state.mode}\n\nContinue?`;
    if (!confirm(msg)) return;
  }

  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);

  hideError();
  setState({ loading: true });
  updateRunButton();
  startTimer();

  try {
    const filters = state.filters
      .filter(f => f.field && f.op && f.value != null && f.value.toString().trim() !== "")
      .map(f => ({
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
      search_params: buildSearchParams(),
    };

    const result = await runBacktestAPI(payload, controller.signal);
    state.columns = result.columns;
    state.rows = result.rows;
    state.currentRunId = null;
    state.currentRunMeta = null;
    state.loadedFromSave = false;
    state.lastRunPayload = payload;
    state.lastTiming = result.timing || null;
    state.rowNotes = {};
    state.dirty = false;
    updateDirtyIndicator();

    const timing = result.timing;
    const durationStr = timing ? " — " + timing.duration_sec.toFixed(2) + "s" : "";
    showStatus(`Done — ${result.row_count} rows${durationStr}`);
    renderTable(result);
  } catch (e) {
    showError(parseApiError(e));
    showStatus("Error");
  } finally {
    clearTimeout(timeoutId);
    setState({ loading: false });
    updateRunButton();
    stopTimer();
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

  document.getElementById("strategy-settings").addEventListener("change", e => {
    const target = e.target;
    const strat = target.dataset.strat;
    const param = target.dataset.param;
    if (!strat || !param) return;
    if (!state.strategySettings[strat]) state.strategySettings[strat] = {};
    if (target.classList.contains("setting-min")) {
      if (!Array.isArray(state.strategySettings[strat][param])) state.strategySettings[strat][param] = [null, null];
      state.strategySettings[strat][param][0] = parseFloat(target.value);
    } else if (target.classList.contains("setting-max")) {
      if (!Array.isArray(state.strategySettings[strat][param])) state.strategySettings[strat][param] = [null, null];
      state.strategySettings[strat][param][1] = parseFloat(target.value);
    } else if (target.type === "checkbox") {
      if (!Array.isArray(state.strategySettings[strat][param])) state.strategySettings[strat][param] = [];
      if (target.checked) {
        if (!state.strategySettings[strat][param].includes(target.value)) {
          state.strategySettings[strat][param].push(target.value);
        }
      } else {
        state.strategySettings[strat][param] = state.strategySettings[strat][param].filter(v => v !== target.value);
      }
    }
  });

  document.getElementById("search-grid").addEventListener("change", e => {
    const target = e.target;
    if (target.id === "grid-profile") state.gridSettings.profile = target.value;
    if (target.id === "grid-mtpd") state.densitySettings.min_trades_per_day = target.value;
    if (target.id === "grid-mttpd") state.densitySettings.min_test_trades_per_day = target.value;
  });

  document.getElementById("search-grid").addEventListener("input", e => {
    const target = e.target;
    if (target.id === "grid-sl") state.gridSettings.sl_values = target.value;
    if (target.id === "grid-tp") state.gridSettings.tp_values = target.value;
    if (target.id === "grid-max-hold") state.gridSettings.max_holds = target.value;
    if (target.id === "grid-mtpd") state.densitySettings.min_trades_per_day = target.value;
    if (target.id === "grid-mttpd") state.densitySettings.min_test_trades_per_day = target.value;
  });

  document.getElementById("btn-run").addEventListener("click", handleRun);
  document.getElementById("btn-save").addEventListener("click", handleSave);
  document.getElementById("saved-runs-list").addEventListener("click", e => {
    const loadBtn = e.target.closest(".saved-load-btn");
    if (loadBtn) handleLoadSavedRun(loadBtn.dataset.runId);

    const exportBtn = e.target.closest(".saved-export-btn");
    if (exportBtn) downloadSavedRunCSV(exportBtn.dataset.runId);

    const delBtn = e.target.closest(".saved-delete-btn");
    if (delBtn) handleDeleteSavedRun(delBtn.dataset.runId);
  });
}

async function handleSave() {
  if (!state.rows || state.rows.length === 0) {
    showStatus("No results to save");
    return;
  }

  const payloadMeta = state.lastRunPayload;
  const search_params = buildSearchParams();
  const metadata = {
    symbol: payloadMeta ? payloadMeta.symbol : "BTCUSD",
    timeframes: payloadMeta ? payloadMeta.timeframes : state.selectedTimeframes,
    mode: payloadMeta ? payloadMeta.mode : state.mode,
    strategies: payloadMeta ? (payloadMeta.strategies || []) : state.selectedStrategies,
    filters: payloadMeta ? (payloadMeta.filters || []) : state.filters.filter(f => f.field && f.op),
    row_count: state.rows.length,
    note: "",
    search_params,
  };
  if (state.lastTiming) metadata.timing = state.lastTiming;

  const payload = {
    columns: state.columns,
    rows: state.rows,
    ratings: state.ratings,
    selectedRows: state.rowSelect,
    rowNotes: state.rowNotes,
    metadata,
  };

  try {
    const result = await saveRun(payload);
    state.currentRunId = result.run_id;
    state.currentRunMeta = metadata;
    state.dirty = false;
    updateDirtyIndicator();
    showStatus("Saved");
    refreshSavedRuns();
  } catch (e) {
    showError(parseApiError(e));
  }
}

async function handleLoadSavedRun(runId) {
  try {
    const data = await loadSavedRun(runId);
    state.columns = data.columns;
    state.rows = data.rows;
    state.ratings = data.ratings || {};
    state.rowSelect = data.selectedRows || {};
    state.rowNotes = data.rowNotes || {};
    const oldVis = state.columnVisibility;
    state.columnVisibility = Object.fromEntries(
      data.columns.map(col => [col, oldVis[col]])
    );
    state.sortCol = null;
    state.sortDir = "asc";
    state.searchText = "";
    document.getElementById("search-input").value = "";

    const meta = data.metadata || {};
    state.selectedTimeframes = meta.timeframes || [];
    state.selectedStrategies = meta.strategies || [];
    state.mode = meta.mode || "normal";
    state.filters = meta.filters && meta.filters.length > 0
      ? meta.filters
      : [{ field: "win_rate", op: ">=", value: "65" }, { field: "profit_factor", op: ">=", value: "1.2" }];
    document.querySelectorAll('input[name="mode"]').forEach(r => {
      r.checked = r.value === state.mode;
    });

    state.currentRunId = runId;
    state.currentRunMeta = meta;
    state.lastTiming = meta.timing || null;
    state.loadedFromSave = true;
    state.dirty = false;
    updateDirtyIndicator();

    const sp = meta.search_params;
    if (sp) {
      state.gridSettings.profile = sp.grid_profile || "dense";
      state.gridSettings.sl_values = Array.isArray(sp.sl_values) ? sp.sl_values.join(", ") : "";
      state.gridSettings.tp_values = Array.isArray(sp.tp_values) ? sp.tp_values.join(", ") : "";
      state.gridSettings.max_holds = Array.isArray(sp.max_holds) ? sp.max_holds.join(", ") : "";
      state.densitySettings.min_trades_per_day = sp.min_trades_per_day ?? 0.33;
      state.densitySettings.min_test_trades_per_day = sp.min_test_trades_per_day ?? 0.33;
      if (sp.strategy_params && typeof sp.strategy_params === "object") {
        state.strategySettings = {};
        for (const [strat, settings] of Object.entries(sp.strategy_params)) {
          state.strategySettings[strat] = settings;
        }
      }
    }

    renderAll();
    renderColumnChooser();
    renderTableContent();

    const tfs = (meta.timeframes || []).join(",");
    const rowsInfo = data.rows ? " — " + data.rows.length + " rows" : "";
    showStatus("Loaded saved run" + (tfs ? " — " + tfs : "") + rowsInfo);
  } catch (e) {
    showError(parseApiError(e));
  }
}

async function handleDeleteSavedRun(runId) {
  const meta = state.savedRuns.find(r => r.run_id === runId);
  let msg = "Delete this saved run?";
  if (meta) {
    const parts = [];
    if (meta.created_at) parts.push("Created: " + meta.created_at.slice(0, 19).replace("T", " "));
    if (meta.timeframes && meta.timeframes.length) parts.push("Timeframes: " + meta.timeframes.join(", "));
    if (meta.row_count) parts.push("Rows: " + meta.row_count);
    if (parts.length) msg += "\n\n" + parts.join("\n");
  }
  if (!confirm(msg)) return;
  try {
    await deleteSavedRun(runId);
    if (state.currentRunId === runId) {
      state.currentRunId = null;
      state.currentRunMeta = null;
      state.loadedFromSave = false;
    }
    refreshSavedRuns();
    showStatus("Deleted saved run");
  } catch (e) {
    showError(parseApiError(e));
  }
}

function downloadSavedRunCSV(runId) {
  const a = document.createElement("a");
  a.href = exportCsvURL(runId);
  a.download = runId + ".csv";
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  showStatus("Downloading CSV...");
}

async function refreshSavedRuns() {
  try {
    state.savedRuns = await fetchSavedRuns();
  } catch (e) {
    state.savedRuns = [];
  }
  renderSavedRuns();
}

function renderSavedRuns() {
  const el = document.getElementById("saved-runs-list");
  const badge = document.getElementById("saved-badge");
  const list = state.savedRuns;

  if (!list || list.length === 0) {
    el.innerHTML = '<div class="saved-empty">No saved runs</div>';
    if (badge) badge.textContent = "";
    return;
  }

  if (badge) badge.textContent = "(" + list.length + ")";

  el.innerHTML = list.map(meta => {
    const created = meta.created_at ? meta.created_at.slice(0, 19).replace("T", " ") : "?";
    const tfs = (meta.timeframes || []).join(",");
    const strats = (meta.strategies || []).length;
    return `
      <div class="saved-item${meta.run_id === state.currentRunId ? " saved-current" : ""}">
        <div class="saved-info">
          <span class="saved-date">${created}</span>
          <span class="saved-tfs">${tfs}</span>
          <span class="saved-mode">${meta.mode || "?"}</span>
          <span class="saved-rows">${meta.row_count || "?"} rows</span>
          ${strats > 0 ? `<span class="saved-strats">${strats} strats</span>` : ""}
        </div>
        <div class="saved-actions">
          <button class="btn-small saved-load-btn" data-run-id="${meta.run_id}">Load</button>
          <button class="btn-small saved-export-btn" data-run-id="${meta.run_id}">Export CSV</button>
          <button class="btn-small saved-delete-btn" data-run-id="${meta.run_id}">Delete</button>
        </div>
      </div>
    `;
  }).join("");
}

init();

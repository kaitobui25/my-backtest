async function init() {
  try {
    const opts = await fetchOptions();
    state.timeframes = opts.timeframes;
    state.strategies = opts.indicators;
    state.filterFields = opts.filter_fields;
    state.operators = opts.operators;
    state.strategyParamSchemas = opts.strategy_param_schemas || {};
    state.gridParamSchema = opts.grid_param_schema || {};
    applyGridDefaults(true);
    populateFilterAddControls();
    renderAll();
    initTable();
    bindEvents();
    refreshSavedRuns();
  } catch (e) {
    showError("Failed to load options: " + parseApiError(e));
  }
}

function isConfigLocked() {
  return state.loading;
}

function cloneConfig(obj) {
  if (typeof structuredClone === "function") return structuredClone(obj);
  return JSON.parse(JSON.stringify(obj));
}

function renderAll() {
  renderTimeframes();
  renderStrategies();
  renderStrategySettings();
  renderSelected();
  renderFilters();
  renderSearchGrid();
  renderExecutionSettings();
  renderRiskSettings();
  renderRunningConfig();
  updateApplyStatusBadges();
  updateRunButton();
}

function renderTimeframes() {
  const el = document.getElementById("timeframe-list");
  el.innerHTML = state.timeframes.map(tf =>
    `<div class="item${state.selectedTimeframes.includes(tf) ? " selected" : ""}" data-value="${tf}">${tf}</div>`
  ).join("");
  const panel = el.closest(".panel");
  if (panel) {
    panel.classList.toggle("config-dirty", hasTrackableResult() && isConfigKeyChanged("timeframes"));
  }
}

function renderStrategies() {
  const el = document.getElementById("strategy-list");
  el.innerHTML = state.strategies.map(s => {
    let cls = "item";
    if (state.selectedStrategies.includes(s)) cls += " selected";
    if (s === state.activeStrategy) cls += " active";
    return `<div class="${cls}" data-value="${s}">${s}</div>`;
  }).join("");
  const panel = el.closest(".panel");
  if (panel) {
    panel.classList.toggle("config-dirty", hasTrackableResult() && isConfigKeyChanged("strategies"));
  }
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
  const trackable = hasTrackableResult();
  const dirty = trackable && isConfigKeyChanged("strategySettings") ? " config-dirty" : "";
  let html = `<div class="settings-strat-name">${s}</div>`;
  for (const [param, meta] of Object.entries(schema)) {
    const value = settings[param] || meta.default;
    if (meta.type === "range") {
      html += `<div class="setting-row${dirty}">
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
      html += `<div class="setting-row${dirty}">
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
    ? '<span class="placeholder" style="color:#999;font-size:11px;">Double-click strategies to add</span>'
    : state.selectedStrategies.map(s =>
        `<span class="selected-tag">${s} <span class="remove" data-strat="${s}">&times;</span></span>`
      ).join("");

  const groups = document.querySelectorAll("#panel-selected .selected-group");
  if (groups.length >= 2) {
    groups[0].classList.toggle("config-dirty", hasTrackableResult() && isConfigKeyChanged("timeframes"));
    groups[1].classList.toggle("config-dirty", hasTrackableResult() && isConfigKeyChanged("strategies"));
  }
}

function renderFilters() {
  const el = document.getElementById("filter-list");
  const favs = getFilterFavorites();
  const sortedFields = [...state.filterFields].sort((a, b) => {
    const af = favs.includes(a) ? 0 : 1;
    const bf = favs.includes(b) ? 0 : 1;
    return af - bf;
  });
  el.innerHTML = state.filters.map((f, i) => `
    <div class="filter-row" data-idx="${i}">
      <span class="filter-star${favs.includes(f.field) ? " fav" : ""}" data-field="${f.field}">&#9733;</span>
      <select class="field-sel">
        <option value="">field</option>
        ${sortedFields.map(ff => `<option value="${ff}"${ff === f.field ? " selected" : ""}>${ff}</option>`).join("")}
      </select>
      <select class="op-sel">
        <option value="">op</option>
        ${state.operators.map(op => `<option value="${op}"${op === f.op ? " selected" : ""}>${op}</option>`).join("")}
      </select>
      <input class="val-inp" type="text" value="${f.value}">
      <button class="btn-remove" data-idx="${i}">&times;</button>
    </div>
  `).join("");
  const panel = el.closest(".panel");
  if (panel) {
    panel.classList.toggle("config-dirty", hasTrackableResult() && isConfigKeyChanged("filters"));
  }
}

function getFilterFavorites() {
  try {
    return JSON.parse(localStorage.getItem("myBacktest.filterFieldFavorites")) || [];
  } catch { return []; }
}

function saveFilterFavorites(favs) {
  localStorage.setItem("myBacktest.filterFieldFavorites", JSON.stringify(favs));
}

function toggleFilterFavorite(field) {
  let favs = getFilterFavorites();
  if (favs.includes(field)) {
    favs = favs.filter(f => f !== field);
  } else {
    favs.push(field);
  }
  saveFilterFavorites(favs);
  renderFilters();
  populateFilterAddControls();
}

function formatCsvValue(v) {
  if (v == null) return "";
  if (Array.isArray(v)) return v.join(", ");
  return String(v);
}

function getProfileDefaults(profile) {
  const schema = state.gridParamSchema;
  const pd = schema && schema[profile];
  const DENSE_FALLBACK = {
    sl_values: [0.02, 0.03, 0.04, 0.06, 0.08],
    tp_values: [0.005, 0.0075, 0.01, 0.015, 0.02, 0.03],
    max_holds: [16, 32, 64, 96],
  };
  const NORMAL_FALLBACK = {
    sl_values: [0.01, 0.02, 0.04, 0.06],
    tp_values: [0.005, 0.01, 0.02, 0.03],
    max_holds: [48, 96, 0],
  };
  const fb = profile === "dense" ? DENSE_FALLBACK : NORMAL_FALLBACK;
  return {
    sl_values: pd?.sl_values || fb.sl_values,
    tp_values: pd?.tp_values || fb.tp_values,
    max_holds: pd?.max_holds || fb.max_holds,
  };
}

function applyGridDefaults(overwrite) {
  const profile = state.gridSettings.profile || "dense";
  const defs = getProfileDefaults(profile);
  const gs = state.gridSettings;
  if (overwrite || !gs.sl_values) gs.sl_values = formatCsvValue(defs.sl_values);
  if (overwrite || !gs.tp_values) gs.tp_values = formatCsvValue(defs.tp_values);
  if (overwrite || !gs.max_holds) gs.max_holds = formatCsvValue(defs.max_holds);
}

function snapshotCurrentConfig() {
  return {
    timeframes: [...state.selectedTimeframes].sort().join(","),
    strategies: [...state.selectedStrategies].sort().join(","),
    mode: state.mode,
    filters: JSON.stringify(state.filters.map(f => ({ field: f.field, op: f.op, value: String(f.value) }))),
    gridProfile: state.gridSettings.profile,
    gridSl: state.gridSettings.sl_values,
    gridTp: state.gridSettings.tp_values,
    gridMh: state.gridSettings.max_holds,
    gridMtpd: String(state.densitySettings.min_trades_per_day),
    gridMttpd: String(state.densitySettings.min_test_trades_per_day),
    strategySettings: JSON.stringify(state.strategySettings),
    entryMode: state.executionSettings.entry_next_open ? "next_open" : "same_open",
    useSpread: String(state.executionSettings.use_spread_slippage),
    spreadPct: String(state.executionSettings.spread_pct),
    slippagePct: String(state.executionSettings.slippage_pct),
    usePositionSizing: String(state.riskSettings.use_position_sizing),
    riskPerTradePct: String(state.riskSettings.risk_per_trade_pct),
    useLeverage: String(state.riskSettings.use_leverage),
    leverage: String(state.riskSettings.leverage),
    useLiquidation: String(state.riskSettings.use_liquidation),
    maintenanceMarginPct: String(state.riskSettings.maintenance_margin_pct),
  };
}

function getConfigValue(key) {
  switch (key) {
    case "timeframes": return [...state.selectedTimeframes].sort().join(",");
    case "strategies": return [...state.selectedStrategies].sort().join(",");
    case "mode": return state.mode;
    case "filters": return JSON.stringify(state.filters.map(f => ({ field: f.field, op: f.op, value: String(f.value) })));
    case "gridProfile": return state.gridSettings.profile;
    case "gridSl": return state.gridSettings.sl_values;
    case "gridTp": return state.gridSettings.tp_values;
    case "gridMh": return state.gridSettings.max_holds;
    case "gridMtpd": return String(state.densitySettings.min_trades_per_day);
    case "gridMttpd": return String(state.densitySettings.min_test_trades_per_day);
    case "strategySettings": return JSON.stringify(state.strategySettings);
    case "entryMode": return state.executionSettings.entry_next_open ? "next_open" : "same_open";
    case "useSpread": return String(state.executionSettings.use_spread_slippage);
    case "spreadPct": return String(state.executionSettings.spread_pct);
    case "slippagePct": return String(state.executionSettings.slippage_pct);
    case "usePositionSizing": return String(state.riskSettings.use_position_sizing);
    case "riskPerTradePct": return String(state.riskSettings.risk_per_trade_pct);
    case "useLeverage": return String(state.riskSettings.use_leverage);
    case "leverage": return String(state.riskSettings.leverage);
    case "useLiquidation": return String(state.riskSettings.use_liquidation);
    case "maintenanceMarginPct": return String(state.riskSettings.maintenance_margin_pct);
    default: return "";
  }
}

function hasTrackableResult() {
  return state.loading || (state.rows.length > 0 && !state.currentRunId && state.lastRunConfigSnapshot !== null);
}

function isConfigKeyChanged(key) {
  if (!state.lastRunConfigSnapshot) return false;
  return getConfigValue(key) !== state.lastRunConfigSnapshot[key];
}

function saveConfigSnapshot() {
  state.lastRunConfigSnapshot = snapshotCurrentConfig();
}

function appliedStatusFor(keys) {
  if (state.loading) return "Running backtest...";
  if (!state.lastRunConfigSnapshot) return "";
  const changed = keys.some(key => isConfigKeyChanged(key));
  return changed
    ? "Changed after run — click Run Backtest to apply"
    : "Applied to current results";
}

function updateApplyStatusBadges() {
  const setBadge = (id, keys) => {
    const el = document.getElementById(id);
    if (!el) return;
    const text = appliedStatusFor(keys);
    el.textContent = text;
    el.classList.toggle("changed", text.startsWith("Changed"));
  };
  setBadge("filters-apply-status", ["filters"]);
  setBadge("grid-apply-status", ["gridProfile", "gridSl", "gridTp", "gridMh", "gridMtpd", "gridMttpd"]);
  setBadge("execution-apply-status", ["entryMode", "useSpread", "spreadPct", "slippagePct"]);
  setBadge("risk-apply-status", ["usePositionSizing", "riskPerTradePct", "useLeverage", "leverage", "useLiquidation", "maintenanceMarginPct"]);
}

function renderSearchGrid() {
  const el = document.getElementById("search-grid");
  const schema = state.gridParamSchema;
  if (!schema || Object.keys(schema).length === 0) {
    el.innerHTML = "";
    return;
  }
  const locked = isConfigLocked();
  const gs = state.gridSettings;
  const ds = state.densitySettings;
  const trackable = hasTrackableResult();
  const dirty = (key) => trackable && isConfigKeyChanged(key) ? " config-dirty" : "";
  el.innerHTML = `
    <div class="grid-row${dirty("gridProfile")}">
      <label>Profile</label>
      <select id="grid-profile" ${locked ? "disabled" : ""}>
        <option value="dense" ${gs.profile === "dense" ? "selected" : ""}>Dense</option>
        <option value="normal" ${gs.profile === "normal" ? "selected" : ""}>Normal</option>
      </select>
    </div>
    <div class="grid-row${dirty("gridSl")}">
      <label>SL values</label>
      <input type="text" id="grid-sl" value="${gs.sl_values}" placeholder="e.g. 0.02, 0.04, 0.06" ${locked ? "disabled" : ""}>
    </div>
    <div class="grid-row${dirty("gridTp")}">
      <label>TP values</label>
      <input type="text" id="grid-tp" value="${gs.tp_values}" placeholder="e.g. 0.005, 0.01, 0.02" ${locked ? "disabled" : ""}>
    </div>
    <div class="grid-row${dirty("gridMh")}">
      <label>Max Hold</label>
      <input type="text" id="grid-max-hold" value="${gs.max_holds}" placeholder="e.g. 16, 32, 64" ${locked ? "disabled" : ""}>
    </div>
    <div class="grid-row${dirty("gridMtpd")}">
      <label>Min trades/day</label>
      <input type="number" id="grid-mtpd" value="${ds.min_trades_per_day}" min="0.1" max="5" step="0.01" ${locked ? "disabled" : ""}>
    </div>
    <div class="grid-row${dirty("gridMttpd")}">
      <label>Min test trades/day</label>
      <input type="number" id="grid-mttpd" value="${ds.min_test_trades_per_day}" min="0.1" max="5" step="0.01" ${locked ? "disabled" : ""}>
    </div>
  `;
}

function renderExecutionSettings() {
  const el = document.getElementById("execution-settings");
  const es = state.executionSettings;
  const locked = isConfigLocked();
  el.innerHTML = `
    <div class="exec-row">
      <label class="exec-checkbox">
        <input type="checkbox" id="exec-entry-next" ${es.entry_next_open ? "checked" : ""} ${locked ? "disabled" : ""}>
        Entry next open
      </label>
    </div>
    <div class="exec-row">
      <label class="exec-checkbox">
        <input type="checkbox" id="exec-use-spread" ${es.use_spread_slippage ? "checked" : ""} ${locked ? "disabled" : ""}>
        Use spread/slippage
      </label>
    </div>
    <div class="exec-sub ${es.use_spread_slippage ? "" : "exec-disabled"}">
      <div class="exec-row">
        <label>Spread %</label>
        <input type="number" id="exec-spread-pct" value="${es.spread_pct}" min="0" max="0.1" step="0.0001" ${es.use_spread_slippage ? "" : "disabled"} ${locked ? "disabled" : ""}>
      </div>
      <div class="exec-row">
        <label>Slippage %</label>
        <input type="number" id="exec-slippage-pct" value="${es.slippage_pct}" min="0" max="0.1" step="0.0001" ${es.use_spread_slippage ? "" : "disabled"} ${locked ? "disabled" : ""}>
      </div>
    </div>
  `;
}

function renderRiskSettings() {
  const el = document.getElementById("risk-settings");
  const rs = state.riskSettings;
  const locked = isConfigLocked();
  const trackable = hasTrackableResult();
  const dirtyRow = (key) => trackable && isConfigKeyChanged(key) ? " config-dirty" : "";
  const anyDirty = trackable && (
    isConfigKeyChanged("usePositionSizing") ||
    isConfigKeyChanged("riskPerTradePct") ||
    isConfigKeyChanged("useLeverage") ||
    isConfigKeyChanged("leverage") ||
    isConfigKeyChanged("useLiquidation") ||
    isConfigKeyChanged("maintenanceMarginPct")
  );
  const panelSection = el.closest(".panel-section");
  if (panelSection) {
    panelSection.classList.toggle("config-dirty", anyDirty);
  }
  el.innerHTML = `
    <div class="risk-row${dirtyRow("usePositionSizing")}">
      <label class="risk-checkbox">
        <input type="checkbox" id="risk-use-sizing" ${rs.use_position_sizing ? "checked" : ""} ${locked ? "disabled" : ""}>
        Position sizing
      </label>
    </div>
    <div class="risk-sub ${rs.use_position_sizing ? "" : "risk-disabled"}">
      <div class="risk-row${dirtyRow("riskPerTradePct")}">
        <label>Risk % per trade</label>
        <input type="number" id="risk-per-trade" value="${rs.risk_per_trade_pct}" min="0.1" max="10" step="0.1" ${rs.use_position_sizing ? "" : "disabled"} ${locked ? "disabled" : ""}>
      </div>
    </div>
    <div class="risk-row${dirtyRow("useLeverage")}">
      <label class="risk-checkbox">
        <input type="checkbox" id="risk-use-leverage" ${rs.use_leverage ? "checked" : ""} ${locked ? "disabled" : ""}>
        Use leverage
      </label>
    </div>
    <div class="risk-sub ${rs.use_leverage ? "" : "risk-disabled"}">
      <div class="risk-row${dirtyRow("leverage")}">
        <label>Leverage</label>
        <input type="number" id="risk-leverage" value="${rs.leverage}" min="1" max="125" step="1" ${rs.use_leverage ? "" : "disabled"} ${locked ? "disabled" : ""}>
      </div>
    </div>
    <div class="risk-row${dirtyRow("useLiquidation")}">
      <label class="risk-checkbox">
        <input type="checkbox" id="risk-use-liq" ${rs.use_liquidation ? "checked" : ""} ${locked ? "disabled" : ""}>
        Liquidation
      </label>
    </div>
    <div class="risk-sub ${rs.use_liquidation ? "" : "risk-disabled"}">
      <div class="risk-row${dirtyRow("maintenanceMarginPct")}">
        <label>Maint. margin %</label>
        <input type="number" id="risk-mm" value="${rs.maintenance_margin_pct}" min="0.01" max="1" step="0.01" ${rs.use_liquidation ? "" : "disabled"} ${locked ? "disabled" : ""}>
      </div>
    </div>
  `;
}

function renderRunningConfig() {
  const el = document.getElementById("running-config-view");
  const snap = state.runningConfigSnapshot;
  if (!snap) {
    el.innerHTML = '<div class="config-empty">No active backtest config yet</div>';
    return;
  }
  let html = '<div class="config-section"><div class="config-section-title">Basic</div>';
  html += '<div class="config-row"><span class="config-label">Symbol</span><span class="config-value">' + snap.symbol + '</span></div>';
  html += '<div class="config-row"><span class="config-label">Mode</span><span class="config-value">' + snap.mode + '</span></div>';
  html += '<div class="config-row"><span class="config-label">Timeframes</span><span class="config-value">' + ((snap.timeframes || []).join(", ")) + '</span></div>';
  html += '<div class="config-row"><span class="config-label">Strategies</span><span class="config-value">' + (snap.strategies ? snap.strategies.join(", ") : "all") + '</span></div>';
  html += '</div>';
  const filters = snap.filters;
  if (filters && filters.length > 0) {
    html += '<div class="config-section"><div class="config-section-title">Result Filters</div>';
    filters.forEach(function(f) {
      html += '<div class="config-row"><span class="config-label">' + f.field + " " + f.op + '</span><span class="config-value">' + f.value + '</span></div>';
    });
    html += '</div>';
  }
  const sp = snap.search_params;
  if (sp) {
    html += '<div class="config-section"><div class="config-section-title">Search Grid</div>';
    html += '<div class="config-row"><span class="config-label">Profile</span><span class="config-value">' + (sp.grid_profile || "dense") + '</span></div>';
    if (sp.sl_values) html += '<div class="config-row"><span class="config-label">SL values</span><span class="config-value">' + (Array.isArray(sp.sl_values) ? sp.sl_values.join(", ") : sp.sl_values) + '</span></div>';
    if (sp.tp_values) html += '<div class="config-row"><span class="config-label">TP values</span><span class="config-value">' + (Array.isArray(sp.tp_values) ? sp.tp_values.join(", ") : sp.tp_values) + '</span></div>';
    if (sp.max_holds) html += '<div class="config-row"><span class="config-label">Max holds</span><span class="config-value">' + (Array.isArray(sp.max_holds) ? sp.max_holds.join(", ") : sp.max_holds) + '</span></div>';
    if (sp.min_trades_per_day != null) html += '<div class="config-row"><span class="config-label">Min trades/day</span><span class="config-value">' + sp.min_trades_per_day + '</span></div>';
    if (sp.min_test_trades_per_day != null) html += '<div class="config-row"><span class="config-label">Min test trades/day</span><span class="config-value">' + sp.min_test_trades_per_day + '</span></div>';
    html += '</div>';
    html += '<div class="config-section"><div class="config-section-title">Execution</div>';
    html += '<div class="config-row"><span class="config-label">Entry mode</span><span class="config-value">' + (sp.entry_mode || "same_open") + '</span></div>';
    html += '<div class="config-row"><span class="config-label">Spread/slippage</span><span class="config-value">' + (sp.use_spread_slippage ? "yes" : "no") + '</span></div>';
    if (sp.use_spread_slippage) {
      html += '<div class="config-row"><span class="config-label">Spread %</span><span class="config-value">' + (sp.spread_pct != null ? sp.spread_pct : 0) + '</span></div>';
      html += '<div class="config-row"><span class="config-label">Slippage %</span><span class="config-value">' + (sp.slippage_pct != null ? sp.slippage_pct : 0) + '</span></div>';
    }
    html += '</div>';
    html += '<div class="config-section"><div class="config-section-title">Risk / Leverage</div>';
    html += '<div class="config-row"><span class="config-label">Position sizing</span><span class="config-value">' + (sp.use_position_sizing ? "yes" : "no") + '</span></div>';
    if (sp.use_position_sizing) {
      html += '<div class="config-row"><span class="config-label">Risk % per trade</span><span class="config-value">' + (sp.risk_per_trade_pct != null ? sp.risk_per_trade_pct : 1.0) + '</span></div>';
    }
    html += '<div class="config-row"><span class="config-label">Use leverage</span><span class="config-value">' + (sp.use_leverage ? "yes" : "no") + '</span></div>';
    if (sp.use_leverage) {
      html += '<div class="config-row"><span class="config-label">Leverage</span><span class="config-value">' + (sp.leverage != null ? sp.leverage : 1) + '</span></div>';
    }
    html += '<div class="config-row"><span class="config-label">Liquidation</span><span class="config-value">' + (sp.use_liquidation ? "yes" : "no") + '</span></div>';
    if (sp.use_liquidation) {
      html += '<div class="config-row"><span class="config-label">Maint. margin %</span><span class="config-value">' + (sp.maintenance_margin_pct != null ? sp.maintenance_margin_pct : 0.5) + '</span></div>';
    }
    html += '</div>';
  }
  el.innerHTML = html;
}

function dirtyTrack(key) {
  const el = document.getElementById("execution-settings");
  if (el) {
    el.classList.toggle("config-dirty", hasTrackableResult() && isConfigKeyChanged(key));
  }
}

function populateFilterAddControls() {
  const fieldSel = document.getElementById("filter-field-add");
  const favs = getFilterFavorites();
  const sortedFields = [...state.filterFields].sort((a, b) => {
    const af = favs.includes(a) ? 0 : 1;
    const bf = favs.includes(b) ? 0 : 1;
    return af - bf;
  });
  fieldSel.innerHTML = '<option value="">field</option>' +
    sortedFields.map(f => `<option value="${f}">${f}${favs.includes(f) ? " ★" : ""}</option>`).join("");

  const opSel = document.getElementById("filter-op-add");
  opSel.innerHTML = '<option value="">op</option>' +
    state.operators.map(o => `<option value="${o}">${o}</option>`).join("");
}

let strategyClickTimer = null;
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
  const es = state.executionSettings;
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
  params.entry_mode = es.entry_next_open ? "next_open" : "same_open";
  params.use_spread_slippage = es.use_spread_slippage;
  params.spread_pct = Number(es.spread_pct) || 0;
  params.slippage_pct = Number(es.slippage_pct) || 0;
  params.use_position_sizing = state.riskSettings.use_position_sizing;
  params.risk_per_trade_pct = Number(state.riskSettings.risk_per_trade_pct) || 1.0;
  params.use_leverage = state.riskSettings.use_leverage;
  params.leverage = Number(state.riskSettings.leverage) || 1;
  params.use_liquidation = state.riskSettings.use_liquidation;
  params.maintenance_margin_pct = Number(state.riskSettings.maintenance_margin_pct) || 0.5;
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

function activateStrategy(s) {
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
}

function toggleSelectedStrategy(s) {
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
  const panel = document.getElementById("filter-list").closest(".panel");
  if (panel) {
    panel.classList.toggle("config-dirty", hasTrackableResult() && isConfigKeyChanged("filters"));
  }
  updateApplyStatusBadges();
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
  renderSearchGrid();
  renderExecutionSettings();
  renderRiskSettings();
  updateApplyStatusBadges();
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
      timeframes: [...state.selectedTimeframes],
      mode: state.mode,
      strategies: state.selectedStrategies.length > 0 ? [...state.selectedStrategies] : null,
      filters,
      limit: 500,
      search_params: buildSearchParams(),
    };

    state.runningConfigSnapshot = cloneConfig(payload);
    renderRunningConfig();

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
    saveConfigSnapshot();

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
    renderSearchGrid();
    renderExecutionSettings();
    renderRiskSettings();
    updateApplyStatusBadges();
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
    if (!item) return;
    if (e.detail !== 1) return;
    if (strategyClickTimer) {
      clearTimeout(strategyClickTimer);
      strategyClickTimer = null;
    }
    strategyClickTimer = setTimeout(() => {
      strategyClickTimer = null;
      activateStrategy(item.dataset.value);
    }, 200);
  });

  document.getElementById("strategy-list").addEventListener("dblclick", e => {
    const item = e.target.closest(".item");
    if (!item) return;
    e.preventDefault();
    if (strategyClickTimer) {
      clearTimeout(strategyClickTimer);
      strategyClickTimer = null;
    }
    activateStrategy(item.dataset.value);
    toggleSelectedStrategy(item.dataset.value);
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
    if (e.target.classList.contains("filter-star")) {
      toggleFilterFavorite(e.target.dataset.field);
    }
  });

  document.getElementById("btn-add-filter").addEventListener("click", addFilter);

  document.querySelectorAll('input[name="mode"]').forEach(radio => {
    radio.addEventListener("change", e => {
      state.mode = e.target.value;
      const el = document.getElementById("mode-row");
      if (el) {
        el.classList.toggle("config-dirty", hasTrackableResult() && isConfigKeyChanged("mode"));
      }
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
    const splitEl = document.getElementById("strategy-settings");
    const splitPanel = splitEl.closest(".panel-body-split");
    if (splitPanel) {
      splitPanel.classList.toggle("config-dirty", hasTrackableResult() && isConfigKeyChanged("strategySettings"));
    }
  });

  document.getElementById("search-grid").addEventListener("change", e => {
    if (isConfigLocked()) return;
    const target = e.target;
    if (target.id === "grid-profile") {
      state.gridSettings.profile = target.value;
      applyGridDefaults(true);
      renderSearchGrid();
    }
    if (target.id === "grid-mtpd") state.densitySettings.min_trades_per_day = target.value;
    if (target.id === "grid-mttpd") state.densitySettings.min_test_trades_per_day = target.value;
  });

  document.getElementById("search-grid").addEventListener("input", e => {
    if (isConfigLocked()) return;
    const target = e.target;
    const row = target.closest(".grid-row");
    const setDirty = (key) => {
      if (row) row.classList.toggle("config-dirty", hasTrackableResult() && isConfigKeyChanged(key));
    };
    if (target.id === "grid-sl") { state.gridSettings.sl_values = target.value; setDirty("gridSl"); }
    if (target.id === "grid-tp") { state.gridSettings.tp_values = target.value; setDirty("gridTp"); }
    if (target.id === "grid-max-hold") { state.gridSettings.max_holds = target.value; setDirty("gridMh"); }
    if (target.id === "grid-mtpd") {
      state.densitySettings.min_trades_per_day = target.value;
      if (row) row.classList.toggle("config-dirty", hasTrackableResult() && isConfigKeyChanged("gridMtpd"));
    }
    if (target.id === "grid-mttpd") {
      state.densitySettings.min_test_trades_per_day = target.value;
      if (row) row.classList.toggle("config-dirty", hasTrackableResult() && isConfigKeyChanged("gridMttpd"));
    }
    updateApplyStatusBadges();
  });

  document.getElementById("execution-settings").addEventListener("change", e => {
    if (isConfigLocked()) return;
    const target = e.target;
    if (target.id === "exec-entry-next") {
      state.executionSettings.entry_next_open = target.checked;
      dirtyTrack("entryMode");
      updateApplyStatusBadges();
    }
    if (target.id === "exec-use-spread") {
      state.executionSettings.use_spread_slippage = target.checked;
      renderExecutionSettings();
      dirtyTrack("useSpread");
    }
  });

  document.getElementById("execution-settings").addEventListener("input", e => {
    if (isConfigLocked()) return;
    const target = e.target;
    if (target.id === "exec-spread-pct") {
      state.executionSettings.spread_pct = target.value;
      dirtyTrack("spreadPct");
      updateApplyStatusBadges();
    }
    if (target.id === "exec-slippage-pct") {
      state.executionSettings.slippage_pct = target.value;
      dirtyTrack("slippagePct");
      updateApplyStatusBadges();
    }
  });

  document.getElementById("risk-settings").addEventListener("change", e => {
    if (isConfigLocked()) return;
    const target = e.target;
    if (target.id === "risk-use-sizing") {
      state.riskSettings.use_position_sizing = target.checked;
      renderRiskSettings();
      dirtyTrack("usePositionSizing");
    }
    if (target.id === "risk-use-leverage") {
      state.riskSettings.use_leverage = target.checked;
      renderRiskSettings();
      dirtyTrack("useLeverage");
    }
    if (target.id === "risk-use-liq") {
      state.riskSettings.use_liquidation = target.checked;
      renderRiskSettings();
      dirtyTrack("useLiquidation");
    }
    if (target.id === "risk-per-trade") {
      state.riskSettings.risk_per_trade_pct = Number(target.value);
    }
    if (target.id === "risk-leverage") {
      state.riskSettings.leverage = Number(target.value);
    }
    if (target.id === "risk-mm") {
      state.riskSettings.maintenance_margin_pct = Number(target.value);
    }
  });

  document.getElementById("risk-settings").addEventListener("input", e => {
    if (isConfigLocked()) return;
    const target = e.target;
    if (target.id === "risk-per-trade") {
      state.riskSettings.risk_per_trade_pct = Number(target.value);
      dirtyTrack("riskPerTradePct");
      updateApplyStatusBadges();
    }
    if (target.id === "risk-leverage") {
      state.riskSettings.leverage = Number(target.value);
      dirtyTrack("leverage");
      updateApplyStatusBadges();
    }
    if (target.id === "risk-mm") {
      state.riskSettings.maintenance_margin_pct = Number(target.value);
      dirtyTrack("maintenanceMarginPct");
      updateApplyStatusBadges();
    }
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
  const search_params = payloadMeta?.search_params || buildSearchParams();
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
    saveConfigSnapshot();
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
      state.executionSettings.entry_next_open = sp.entry_mode === "next_open";
      state.executionSettings.use_spread_slippage = sp.use_spread_slippage === true;
      state.executionSettings.spread_pct = sp.spread_pct ?? 0;
      state.executionSettings.slippage_pct = sp.slippage_pct ?? 0;
      state.riskSettings.use_position_sizing = sp.use_position_sizing === true;
      state.riskSettings.risk_per_trade_pct = sp.risk_per_trade_pct ?? 1.0;
      state.riskSettings.use_leverage = sp.use_leverage === true;
      state.riskSettings.leverage = sp.leverage ?? 1;
      state.riskSettings.use_liquidation = sp.use_liquidation === true;
      state.riskSettings.maintenance_margin_pct = sp.maintenance_margin_pct ?? 0.5;
    }

    if (sp) {
      state.runningConfigSnapshot = {
        symbol: meta.symbol || "BTCUSD",
        timeframes: meta.timeframes || [],
        mode: meta.mode || "normal",
        strategies: meta.strategies && meta.strategies.length > 0 ? meta.strategies : null,
        filters: meta.filters || [],
        limit: 500,
        search_params: sp,
      };
    } else {
      state.runningConfigSnapshot = null;
    }

    const savedStrats = Object.keys(state.strategySettings);
    if (savedStrats.length > 0) {
      state.activeStrategy = savedStrats[0];
    } else if (state.selectedStrategies.length > 0) {
      state.activeStrategy = state.selectedStrategies[0];
    } else {
      state.activeStrategy = null;
    }

    renderAll();
    renderColumnChooser();
    renderTableContent();
    saveConfigSnapshot();
    updateApplyStatusBadges();

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

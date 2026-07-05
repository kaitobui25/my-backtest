# Phase 5 - Polish / Export / Safety Checklist

## Goal

Make the internal BTC backtest web app more comfortable, safer, and easier to use daily.

Focus:
- Polish existing UI behavior.
- Improve export/copy reliability.
- Persist small frontend preferences.
- Improve backend/frontend error visibility.
- Add lightweight runtime timing/benchmark information.
- Keep the code simple and boring.
- Do not modify the core backtest/search logic.

Current project note:
- Phase 4 currently uses JSON saved runs under `data/saved_runs/`.
- Do not migrate to SQLite in Phase 5 unless explicitly requested.
- Keep existing `/api/saved-runs` behavior working.

---

## 1. Export CSV polish

### Frontend CSV export

- [ ] Keep `Export CSV` working from the currently displayed table.
- [ ] Export only visible columns.
- [ ] Export rows according to current search filter.
- [ ] Export rows according to current sort order.
- [ ] Include review fields:
  - [ ] `selected`
  - [ ] `rating`
  - [ ] `note`
- [ ] Keep UTF-8 BOM so Excel opens Japanese/Vietnamese text correctly.
- [ ] Escape commas, quotes, newlines correctly.
- [ ] Confirm CSV works after:
  - [ ] Fresh backtest result
  - [ ] Loaded saved run
  - [ ] Search applied
  - [ ] Sort applied
  - [ ] Some columns hidden
  - [ ] Notes containing Japanese/Vietnamese
  - [ ] Notes containing commas
  - [ ] Notes containing double quotes
  - [ ] Notes containing line breaks

### CSV filename

- [ ] Use a more useful filename than always `backtest_results.csv`.
- [ ] Suggested format:

    `BTCUSD_<mode>_<timeframes>_<YYYYMMDD_HHMMSS>.csv`

- [ ] If loaded from saved run, include saved run id or saved run date if available.
- [ ] Avoid invalid filename characters.

---

## 2. Copy selected rows polish

- [ ] Keep `Copy Selected` working from the current table.
- [ ] Copy rows in current filtered + sorted order.
- [ ] Copy only selected rows.
- [ ] Copy only visible columns.
- [ ] Decide whether to include review fields:
  - [ ] `rating`
  - [ ] `note`
- [ ] If review fields are included, keep the output clean for spreadsheet paste.
- [ ] Use TSV format for clipboard copy.
- [ ] Preserve Japanese/Vietnamese text.
- [ ] Show clear status after copy:

    `Copied 3 rows`

- [ ] If no row is selected, show:

    `No rows selected`

- [ ] Confirm copy works after:
  - [ ] Load saved run
  - [ ] Search
  - [ ] Sort
  - [ ] Hide/show columns
  - [ ] Edit note
  - [ ] Change rating
  - [ ] Toggle checkbox

---

## 3. Persist column visibility in localStorage

### Storage key

- [ ] Add a stable localStorage key, for example:

    `my-backtest.columnVisibility`

### Save behavior

- [ ] Save `state.columnVisibility` to localStorage whenever a column is toggled.
- [ ] Do not save result rows to localStorage.
- [ ] Only save small UI preference data.

### Load behavior

- [ ] On app init, load column visibility from localStorage.
- [ ] Apply saved visibility after columns are known.
- [ ] If a saved column no longer exists, ignore it.
- [ ] If a new column appears, show it by default.
- [ ] If localStorage data is corrupt, ignore it and continue without crashing.

### Manual test

- [ ] Run backtest.
- [ ] Hide several columns.
- [ ] Reload browser.
- [ ] Confirm hidden columns remain hidden.
- [ ] Load saved run.
- [ ] Confirm visibility preference still applies.
- [ ] Clear browser localStorage.
- [ ] Confirm default visibility works again.

---

## 4. Persist table font size in localStorage

### Storage key

- [ ] Add a stable localStorage key, for example:

    `my-backtest.tableFontSize`

### Save behavior

- [ ] Save font size whenever user clicks `A-` or `A+`.
- [ ] Keep current min/max limits.
- [ ] Do not allow broken values.

### Load behavior

- [ ] On app init, load saved font size.
- [ ] Apply it to the result table.
- [ ] If localStorage value is missing or invalid, use default font size.
- [ ] If localStorage value is too small/large, clamp it.

### Manual test

- [ ] Change font size.
- [ ] Reload browser.
- [ ] Confirm font size is preserved.
- [ ] Clear localStorage.
- [ ] Confirm default font size returns.

---

## 5. Delete saved run safety

Current Phase 4 already has confirm before delete. Phase 5 should polish it.

- [ ] Keep confirmation before deleting a saved run.
- [ ] Confirmation text should include useful context:
  - [ ] created_at
  - [ ] timeframes
  - [ ] row_count
- [ ] Do not delete if user cancels.
- [ ] After successful delete:
  - [ ] Refresh saved runs list
  - [ ] Show clear status: `Deleted saved run`
- [ ] If deleting the currently loaded run:
  - [ ] Clear `currentRunId`
  - [ ] Clear `currentRunMeta`
  - [ ] Set `loadedFromSave = false`
  - [ ] Decide whether to keep current table visible
- [ ] If delete fails:
  - [ ] Show clear error
  - [ ] Do not silently fail

Manual test:

- [ ] Save two runs.
- [ ] Delete one run.
- [ ] Confirm list refreshes.
- [ ] Load the remaining run.
- [ ] Try deleting a missing run.
- [ ] Confirm the app does not crash.

---

## 6. Better backend error messages

### Backtest API errors

- [ ] Show clear error when backend returns 400.
- [ ] Show clear error when backend returns 500.
- [ ] Show clear error when backend is offline.
- [ ] Show clear error when request times out.
- [ ] Keep errors user-readable.

Examples:

- [ ] `Invalid timeframe: M3`
- [ ] `Invalid mode: abc`
- [ ] `Invalid filter field: profit`
- [ ] `Backtest failed. Check backend logs.`
- [ ] `Backend is not reachable. Is uvicorn running on port 8000?`

### Frontend API helper

- [ ] Reuse one helper for parsing API errors if possible.
- [ ] Try to read JSON error body.
- [ ] Fall back to `HTTP <status>`.
- [ ] Catch network errors.
- [ ] Do not show raw stack traces to the user.

### Manual test

- [ ] Stop backend and click Run.
- [ ] Use invalid API payload manually if needed.
- [ ] Force backend error if practical.
- [ ] Confirm the frontend shows useful messages.

---

## 7. Request timeout / heavy request warning

### Frontend timeout

- [ ] Add request timeout support for `runBacktestAPI()`.
- [ ] Suggested timeout:

    60 seconds

- [ ] Use `AbortController`.
- [ ] Show clear message if timeout happens:

    `Backtest request timed out. Try fewer timeframes, fewer strategies, or lighter filters.`

### Heavy request warning

Before running backtest:

- [ ] Estimate request heaviness from:
  - [ ] number of selected timeframes
  - [ ] number of selected strategies
  - [ ] mode
  - [ ] limit
- [ ] If request seems heavy, show a confirm warning.
- [ ] Example:

    `This may take a while because many timeframes/strategies are selected. Continue?`

- [ ] Do not block normal small requests.

### Manual test

- [ ] Run one timeframe + one strategy.
- [ ] Confirm no warning.
- [ ] Run many timeframes + all strategies.
- [ ] Confirm warning appears.
- [ ] Cancel warning.
- [ ] Confirm no request is sent.
- [ ] Continue warning.
- [ ] Confirm request runs.

---

## 8. Simple progress / running status

No websocket in Phase 5.

- [ ] Keep progress simple.
- [ ] Show `Running backtest...` while request is active.
- [ ] Disable Run button while running.
- [ ] Disable Save button while running.
- [ ] Optional: show elapsed seconds while running.
- [ ] Example:

    `Running backtest... 12s`

- [ ] Stop timer when request finishes or fails.
- [ ] Do not add realtime websocket.
- [ ] Do not add complex progress backend unless needed.

Manual test:

- [ ] Start backtest.
- [ ] Confirm Run button is disabled.
- [ ] Confirm status updates.
- [ ] Confirm status stops after success.
- [ ] Confirm status stops after error.

---

## 9. Runtime benchmark / timing info

Add lightweight timing metadata.

### Backend timing

- [ ] Add `started_at`.
- [ ] Add `finished_at`.
- [ ] Add `duration_sec`.

For `/api/backtest` response, include optional metadata:

    {
      "run_temp_id": "uuid",
      "row_count": 123,
      "columns": [...],
      "rows": [...],
      "timing": {
        "started_at": "...",
        "finished_at": "...",
        "duration_sec": 12.34
      }
    }

- [ ] Keep existing frontend compatible if timing is missing.
- [ ] Do not change core backtest logic.
- [ ] Measure API-level duration around `run_search(...)`.

### Frontend timing display

- [ ] Show duration in status after success:

    `Done — 123 rows — 12.34s`

- [ ] Save timing metadata if saved run payload supports metadata.
- [ ] Show timing in saved runs list if useful.

### Manual test

- [ ] Run backtest.
- [ ] Confirm response has timing.
- [ ] Confirm frontend shows duration.
- [ ] Save run.
- [ ] Load run.
- [ ] Confirm timing metadata does not break saved run load.

---

## 10. Backend CSV export endpoint

Add endpoint from plan:

    GET /api/backtest/runs/{run_id}/export.csv

Current Phase 4 uses `/api/saved-runs`, so implement against the current saved-run store unless SQLite migration is explicitly requested.

Suggested current endpoint:

    GET /api/saved-runs/{run_id}/export.csv

Or, for plan compatibility, optionally add both:

    GET /api/backtest/runs/{run_id}/export.csv
    GET /api/saved-runs/{run_id}/export.csv

### Backend behavior

- [ ] Load saved run by `run_id`.
- [ ] Return 404 if run does not exist.
- [ ] Return 404 or clear error if saved JSON is corrupt.
- [ ] Generate CSV from saved rows.
- [ ] Include UTF-8 BOM.
- [ ] Set response headers:
  - [ ] `Content-Type: text/csv; charset=utf-8`
  - [ ] `Content-Disposition: attachment; filename="...csv"`
- [ ] Include review fields:
  - [ ] selected
  - [ ] rating
  - [ ] note
- [ ] Preserve visible columns if possible.
- [ ] If saved visibility is not stored, export all saved columns.
- [ ] Escape CSV values correctly.

### Frontend behavior

- [ ] Add export saved run button if useful.
- [ ] Or keep only current frontend CSV export if backend export is not needed yet.
- [ ] Do not break existing `Export CSV`.

### Manual test

- [ ] Save a run.
- [ ] Open export endpoint directly in browser.
- [ ] Confirm CSV downloads.
- [ ] Open CSV in Excel.
- [ ] Confirm Japanese/Vietnamese text is correct.
- [ ] Confirm notes/rating/selected are included.
- [ ] Try missing run id.
- [ ] Confirm clear 404.

---

## 11. Save/load polish

- [ ] Save current `columnVisibility` if useful.
- [ ] Save current `fontSize` if useful.
- [ ] Save `timing` metadata if available.
- [ ] Save `lastRunPayload` or normalized run setup if useful.
- [ ] Make loaded saved run display its source clearly.
- [ ] Example status:

    `Loaded saved run — BTCUSD M15,H1 — 120 rows`

- [ ] If user edits rating/note after loading, dirty indicator should appear.
- [ ] After save, dirty indicator should disappear.
- [ ] If user tries to run new backtest while dirty, optionally confirm:

    `You have unsaved review changes. Continue?`

- [ ] Keep this simple. Do not build complex draft management.

---

## 12. UI polish without making it fancy

- [ ] Keep layout simple.
- [ ] Improve spacing only where needed.
- [ ] Keep table readable.
- [ ] Notes column should not destroy layout.
- [ ] Long text should be clipped or scrollable.
- [ ] Status and error messages should be easy to see.
- [ ] Dirty indicator should be visible but not annoying.
- [ ] Saved runs list should remain compact.
- [ ] Do not add chart.
- [ ] Do not add dashboard.
- [ ] Do not add login.
- [ ] Do not add websocket.

---

## 13. Backend safety

- [ ] Keep path traversal protection for saved runs.
- [ ] Do not access files outside saved run directory.
- [ ] Keep corrupt JSON handling.
- [ ] Keep delete safe.
- [ ] Do not expose local filesystem paths unnecessarily in API response.
- [ ] Consider removing or hiding `saved_path` from frontend-facing response if not needed.
- [ ] Validate `run_id` before file access.
- [ ] Avoid crashing server on invalid input.
- [ ] Keep error messages clear.

---

## 14. Tests

### Backend tests

Add or update tests for:

- [ ] `/api/backtest` timing metadata exists.
- [ ] Timing metadata has `started_at`.
- [ ] Timing metadata has `finished_at`.
- [ ] Timing metadata has `duration_sec`.
- [ ] Invalid request gives readable 400.
- [ ] Saved run CSV export works.
- [ ] Missing saved run CSV export returns 404.
- [ ] Corrupt saved run CSV export does not crash.
- [ ] Path traversal export is blocked.
- [ ] Saved run delete still works.

### Frontend manual tests

Because current frontend is vanilla JS, manual testing is acceptable if no frontend test setup exists.

Create or update manual checklist:

- [ ] Run backtest.
- [ ] Sort table.
- [ ] Search table.
- [ ] Hide columns.
- [ ] Change font size.
- [ ] Select rows.
- [ ] Set ratings.
- [ ] Add notes.
- [ ] Export CSV.
- [ ] Copy selected.
- [ ] Save run.
- [ ] Reload browser.
- [ ] Confirm column visibility persists.
- [ ] Confirm font size persists.
- [ ] Load saved run.
- [ ] Confirm rating/selected/note restored.
- [ ] Edit note after load.
- [ ] Confirm dirty indicator appears.
- [ ] Save again.
- [ ] Confirm dirty indicator disappears.
- [ ] Delete saved run.
- [ ] Confirm delete requires confirmation.
- [ ] Stop backend.
- [ ] Confirm frontend shows clear backend unreachable error.

---

## 15. Files likely to modify

### Frontend

- [ ] `frontend/src/api.js`
  - request timeout
  - improved error parsing
  - optional backend CSV export helper

- [ ] `frontend/src/state.js`
  - persisted preference keys
  - timing metadata if needed

- [ ] `frontend/src/table.js`
  - CSV export polish
  - copy selected polish
  - localStorage column visibility
  - localStorage font size

- [ ] `frontend/src/main.js`
  - dirty warning if needed
  - timing status
  - heavy request warning
  - load persisted preferences
  - better status/error messages

- [ ] `frontend/src/style.css`
  - small polish only
  - dirty indicator
  - error/status visibility
  - notes layout if needed

- [ ] `frontend/index.html`
  - only if extra status/timing/export controls are needed

### Backend

- [ ] `app/api/routes_backtest.py`
  - timing metadata for `/api/backtest`

- [ ] `app/api/routes_saved.py`
  - optional CSV export endpoint

- [ ] `app/services/saved_store.py`
  - optional CSV helper
  - keep path safety

- [ ] `tests/test_saved_store.py`
  - add CSV export tests
  - make tests use temp directory, not real `data/saved_runs`

- [ ] New test file if needed:
  - `tests/test_backtest_routes.py`

### Do not modify unless required

- [ ] `app/backtest/engine.py`
- [ ] `app/backtest/signals.py`
- [ ] `app/backtest/indicators.py`
- [ ] `app/backtest/metrics.py`
- [ ] Core old search scripts

---

## 16. Do not do in Phase 5

- [ ] Do not add user accounts.
- [ ] Do not add cloud deployment.
- [ ] Do not add realtime websocket.
- [ ] Do not add complex charts.
- [ ] Do not add multi-symbol support.
- [ ] Do not add live trading.
- [ ] Do not rewrite the backtest engine.
- [ ] Do not migrate to SQLite unless explicitly requested.
- [ ] Do not add heavy frontend framework unless explicitly requested.
- [ ] Do not store signal arrays.
- [ ] Do not store huge temporary data in browser localStorage.

---

## 17. Done criteria

Phase 5 is done when:

- [ ] Export CSV works from current table.
- [ ] Export CSV works after loading saved run.
- [ ] CSV opens correctly in Excel with Japanese/Vietnamese text.
- [ ] Copy Selected works after search/sort/load.
- [ ] Column visibility persists after browser reload.
- [ ] Font size persists after browser reload.
- [ ] Delete saved run has confirmation and clear result status.
- [ ] Backtest errors are user-readable.
- [ ] Backend offline/network errors are user-readable.
- [ ] Heavy request warning exists.
- [ ] Long-running request timeout exists.
- [ ] Basic running status/progress exists.
- [ ] Backtest response includes timing metadata.
- [ ] Timing is shown in frontend status.
- [ ] Optional saved-run CSV endpoint works if implemented.
- [ ] Tests or manual checklist cover the main Phase 5 flows.
- [ ] Core backtest logic is unchanged.
- [ ] Existing Phase 3/4 behavior is not broken.

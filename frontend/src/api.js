const API_BASE = "http://127.0.0.1:8000/api";
const REQUEST_TIMEOUT_MS = 300000;

function parseApiError(err) {
  if (err.name === "AbortError") return "Backtest request timed out in the browser. The backend may still be finishing the old run. Try fewer timeframes/strategies, wait a bit before running again, or check the backend console.";
  if (err instanceof TypeError && err.message === "Failed to fetch") return "Backend is not reachable. Is uvicorn running on port 8000?";
  return err.message || "Unknown error";
}

async function fetchOptions() {
  const res = await fetch(API_BASE + "/options");
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || `HTTP ${res.status}`);
  }
  return res.json();
}

async function runBacktestAPI(payload, signal) {
  const res = await fetch(API_BASE + "/backtest", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
    signal,
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || `HTTP ${res.status}`);
  }
  return res.json();
}

async function saveRun(payload) {
  const res = await fetch(API_BASE + "/saved-runs", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || `HTTP ${res.status}`);
  }
  return res.json();
}

async function fetchSavedRuns() {
  const res = await fetch(API_BASE + "/saved-runs");
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

async function loadSavedRun(runId) {
  const res = await fetch(API_BASE + "/saved-runs/" + runId);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

async function deleteSavedRun(runId) {
  const res = await fetch(API_BASE + "/saved-runs/" + runId, { method: "DELETE" });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

function exportCsvURL(runId) {
  return API_BASE + "/saved-runs/" + runId + "/export.csv";
}

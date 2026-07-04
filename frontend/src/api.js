const API_BASE = "http://127.0.0.1:8000/api";

async function fetchOptions() {
  const res = await fetch(API_BASE + "/options");
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || `HTTP ${res.status}`);
  }
  return res.json();
}

async function runBacktestAPI(payload) {
  const res = await fetch(API_BASE + "/backtest", {
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

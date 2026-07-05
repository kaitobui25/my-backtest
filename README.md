# My Backtest

Cong cu backtest noi bo cho chien luoc giao dich BTCUSD. Du an gom backend FastAPI de chay search/backtest, frontend tinh de chon timeframe/strategy/filter va bang ket qua de luu, danh dau, ghi chu, xuat CSV.

## Tinh nang chinh

- Chay backtest cho `BTCUSD` tren cac timeframe `M15`, `M30`, `H1`, `H2`, `H4`, `D1`.
- Ho tro 2 che do search: `normal` va `dense_high_winrate`.
- Loc ket qua theo cac cot nhu `win_rate`, `profit_factor`, `test_total_return`, `score`, ...
- Luu ket qua vao `data/saved_runs/`, tai lai run da luu va xuat CSV.
- Frontend chay bang HTML/CSS/JavaScript thuan, goi backend qua API.

## Yeu cau

- Python 3.11+.
- Du lieu OHLC dang parquet cho BTCUSD.
- Cac package Python trong `requirements.txt`.

Du lieu backtest duoc load tu mot trong hai vi tri:

```text
flect_mt5/cache/btc/
my-data/flect_mt5/cache/btc/
```

Moi timeframe can nam trong thu muc lowercase tuong ung, vi du:

```text
flect_mt5/cache/btc/m15/BTCUSD_M15_*.parquet
flect_mt5/cache/btc/h1/BTCUSD_H1_*.parquet
flect_mt5/cache/btc/d1/BTCUSD_D1_*.parquet
```

File parquet can co index thoi gian va cac cot:

```text
open, high, low, close, volume
```

## Cai dat

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

## Chay backend

```powershell
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Kiem tra backend:

```powershell
curl http://127.0.0.1:8000/api/health
curl http://127.0.0.1:8000/api/options
```

Tai lieu API tu dong cua FastAPI:

```text
http://127.0.0.1:8000/docs
```

## Chay frontend

Frontend goi API mac dinh tai `http://127.0.0.1:8000/api`. Sau khi backend dang chay, mo mot terminal khac:

```powershell
python -m http.server 5173 -d frontend
```

Sau do mo:

```text
http://127.0.0.1:5173
```

## Vi du goi API

```powershell
Invoke-RestMethod `
  -Method Post `
  -Uri http://127.0.0.1:8000/api/backtest `
  -ContentType "application/json" `
  -Body '{
    "symbol": "BTCUSD",
    "timeframes": ["M15"],
    "mode": "normal",
    "strategies": ["EMA_PULLBACK"],
    "filters": [
      {"field": "win_rate", "op": ">=", "value": 60},
      {"field": "profit_factor", "op": ">=", "value": 1.1}
    ],
    "limit": 100
  }'
```

## Test

```powershell
pytest
```

Luu y: mot so test/API backtest can du lieu parquet hop le trong `flect_mt5/cache/btc/` hoac `my-data/flect_mt5/cache/btc/`.

## Cau truc thu muc

```text
my-backtest/
+-- app/
|   +-- main.py                  # FastAPI app, CORS, dang ky router
|   +-- api/
|   |   +-- routes_backtest.py    # POST /api/backtest
|   |   +-- routes_options.py     # /api/health, /api/options
|   |   +-- routes_saved.py       # API luu/tai/xoa/xuat CSV saved runs
|   |   +-- schemas.py            # Pydantic request/response models
|   +-- backtest/
|   |   +-- config.py             # symbol, timeframe, grid SL/TP, nguong loc
|   |   +-- data_loader.py        # load OHLC parquet
|   |   +-- engine.py             # mo phong lenh va trade exits
|   |   +-- indicators.py         # tinh indicator
|   |   +-- metrics.py            # tinh metric va score
|   |   +-- paths.py              # tim data root/result path
|   |   +-- runner.py             # evaluate timeframe va run_search
|   |   +-- signals.py            # tao bien the tin hieu strategy
|   +-- services/
|       +-- saved_store.py        # luu ket qua vao data/saved_runs
+-- frontend/
|   +-- index.html                # giao dien web tinh
|   +-- src/
|       +-- api.js                # client goi FastAPI
|       +-- main.js               # UI events va workflow run/save/load
|       +-- state.js              # state phia frontend
|       +-- style.css             # style giao dien
|       +-- table.js              # render/sort/filter bang ket qua
+-- flect_mt5/
|   +-- core/                     # script lien quan MT5/data fetch
+-- core/                         # script nghien cuu/search cu
+-- ref/                          # ma tham khao va Pine Script TradingView
+-- scripts/
|   +-- smoke_backtest.py         # smoke script phu tro
+-- tests/
|   +-- test_saved_store.py       # test saved runs va mot so API behavior
+-- data/
|   +-- saved_runs/               # ket qua da luu, bi ignore boi git
+-- result/                       # output backtest, bi ignore boi git
+-- requirements.txt
+-- .gitignore
+-- README.md
```

## Ghi chu van hanh

- `data/saved_runs/`, `cache/`, `result/`, `.venv/`, `old/`, `vectorbt/` dang duoc ignore trong git.
- Backend hien chi validate symbol `BTCUSD`.
- Neu request qua nang, frontend se canh bao truoc khi chay vi so to hop timeframe/strategy/grid co the lon.

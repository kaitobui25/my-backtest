# Backtest V7 - BTCUSD MT5 5Y Research

Muc tieu: gom ket qua research/backtest that tren du lieu BTCUSD MT5 5 nam vao mot thu muc gon, de doc va audit lai.

## Doc Truoc

- `result/05_manual_portfolio_research/summary_manual_vi.md`: ket qua moi cho cach trade tay nhieu setup/nhieu timeframe.
- `result/00_recommendations/short_stop_recommendation.md`: ket luan moi cho bai toan SL ngan.
- `result/00_recommendations/final_recommendation.md`: ket luan va setup nen uu tien.
- `result/02_validation/validation_summary.md`: bang validation cua 4 setup chinh.
- `result/02_validation/*_trades.csv`: log tung lenh.
- `result/01_search_raw/summary.md`: tom tat broad search.

## Ket Qua Manual Multi-Timeframe Moi

Muc tieu moi khong ep mot cau hinh dat 50%/nam, ma ghep nhieu setup de trade tay.

Recommended basket:
- 8 setup tren H6/H8/H12/D1.
- Moi lenh dung 15% equity.
- Toi da 4 lenh BTC mo cung luc.
- Khong giu long va short nguoc chieu cung luc.
- OOS tu 2025-01-01 den 2026-06-05: 131 trades, 71.76% winrate, +79.00% total return, CAGR 50.44%, PF 4.81.
- Full period: 390 trades, 64.87% winrate, +355.49% total return, CAGR 35.98%, PF 3.92.

Doc chi tiet tai `result/05_manual_portfolio_research/summary_manual_vi.md`.

## Ket Qua Short-Stop Moi

Ket qua cu co winrate cao nhung SL qua rong. Research moi chay them tat ca timeframe BTC trong `my-data/flect_mt5/cache/btc`, uu tien SL ngan va tach long/short.

Primary high-winrate sell-only:
- `H3 IBS Cycle Short-Only`
- Rule: short khi `IBS >= 0.95`, `close < EMA200`, `EMA50 < EMA200`; vao lenh open nen H3 tiep theo.
- SL 4.0%, TP 0.75%, max hold 48 nen H3.
- Full period: 132 trades, 88.64% winrate, +26.76% total return, PF 1.45.
- OOS tu 2025-01-01: 52 trades, 90.38% winrate, +12.91% total return, PF 1.65.
- Risk: TP rat nho; 1 SL co the xoa khoang 5-6 lenh thang binh thuong.

Balanced sell-only profit:
- `H4 IBS Cycle Short-Only`
- Rule: short khi `IBS >= 0.95`, `close < EMA200`, `EMA50 < EMA200`; vao lenh open nen H4 tiep theo.
- SL 4.0%, TP 1.5%, max hold 24 nen H4.
- Full period: 77 trades, 80.52% winrate, +44.00% total return, PF 1.73.
- OOS tu 2025-01-01: 42 trades, 88.10% winrate, +40.81% total return, PF 2.86.
- Risk: nam 2023 xau; worst MAE lon hon H3.

## Ket Qua Chinh

Best high-winrate pick:
- `D1 IBS Trend Aggressive`
- Full period: 62 trades, 96.77% winrate, +663.82% total return, PF 7.92.
- OOS tu 2025-01-01: 27 trades, 96.30% winrate, +157.48% total return, PF 14.03.
- Risk: SL 30%, worst MAE -25.47%; chi hop voi position sizing nho/no leverage.

Best balanced profit pick:
- `H4 IBS Range Profit`
- Full period: 52 trades, 75.00% winrate, +1126.96% total return, PF 3.22.
- OOS tu 2025-01-01: 13 trades, 76.92% winrate, +88.12% total return, PF 3.37.

## Gia Dinh Backtest

- Symbol: BTCUSD tu MT5.
- Data: `my-data/flect_mt5/cache/btc`.
- Period: 2021-05-31 den 2026-05-29.
- Entry signal duoc shift 1 candle, vao lenh o open candle ke tiep.
- TP/SL check bang OHLC high/low.
- Neu TP va SL cung cham trong mot candle, tinh SL truoc.
- Cost model: 0.035% moi chieu, 0.070% round trip.
- Max drawdown trong report la closed-trade drawdown; xem them `worst_mae_pct` de biet drawdown trong luc lenh dang mo.

## Chay Lai

Tu root repo:

```powershell
python vectorbt-master/my-data/backtest_v7/core/20_btc_strategy_search.py
python vectorbt-master/my-data/backtest_v7/core/21_btc_validate_candidates.py
python vectorbt-master/my-data/backtest_v7/core/40_btc_manual_portfolio_research.py
```

TradingView script:

- `result/03_tradingview/btc_d1_ibs_trend_aggressive.pine`

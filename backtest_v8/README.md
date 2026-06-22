# Backtest V8

Muc tieu: chay search/backtest co config ro rang, tach rieng khoi `backtest_v7`, dung data MT5 cache va chi dung indicator da convert sang Python.

## Chay backtest

Tu root repo `vectorbt-master`:

```powershell
python my-data\backtest_v8\run.py
```

Ket qua nam trong:

```text
my-data/backtest_v8/result/<run_id>/
```

Runner se in top 5 setup, so setup da test, so setup bi loai, ly do bi loai pho bien, va duong dan report.

## Sua config

File chinh:

```text
my-data/backtest_v8/config.toml
```

Phan hay sua:

- `[market]`: `symbol`, `asset_class`, `data_path`, `timeframes`, `start`, `end`.
- `[costs]`: `fee_per_side`, `slippage_per_side`.
- `[execution]`: `position_size_pct`, long/short, entry lag, uu tien TP/SL neu cung cham trong mot nen.
- `[validation]`: moc train/OOS va dieu kien OOS toi thieu.
- `[targets]`: mo ta target, target loi nhuan thang, min/max lenh moi thang, max drawdown, min winrate.
- `[targets.achievement]`: dieu kien de cot `dat_target=yes`; doi muc tieu trade thi sua block nay.
- `[hard_filters]`: dieu kien bat buoc cho full/train/OOS. Setup khong qua block nay se khong vao nhom A.
- `[filters]`: filter chong setup ao nhu qua it lenh, qua nhieu thang khong co lenh, profit phu thuoc 1-2 lenh lon.
- `[data_quality]`: nguong canh bao/phat diem khi data co gap lon.
- `[scoring.weights]` va `[scoring.params]`: trong so va nguong phu khi xep hang setup.
- `[warning_thresholds]`: nguong tao warning trong report.
- `[risk]`: nguong phan loai rui ro `thap/vua/cao`.
- `[optimization.*]`: range TP/SL/max hold/side mode.
- `[indicators.*]`: bat/tat indicator va sua parameter range.

Hard filters hien tai:

- Full avg monthly >= 2%.
- Train avg monthly >= 1.5%.
- OOS avg monthly >= 1.5%.
- OOS trades >= 40.
- OOS months >= 12.
- OOS profit factor >= 1.4.
- Full profit factor >= 1.3.
- OOS no-trade-month ratio <= 10%.
- Full no-trade-month ratio <= 15%.
- Full max drawdown <= 22%.
- OOS max drawdown <= 18%.

Target hien tai duoc khai bao trong config, mac dinh la raw monthly return 10-20%/month. Report lay ten target tu `targets.description` va cot `dat_target` lay rule tu `[targets.achievement]`.

Rule trong `[targets.achievement]` co dang:

```text
<scope>_<metric>_<operator> = <value>
```

Trong do `scope` la `full`, `train`, hoac `oos`; `operator` la `min`, `max`, `abs_min`, hoac `abs_max`; `metric` la ten metric trong report/detail JSON, vi du `avg_monthly_return`, `winrate`, `profit_factor`, `max_drawdown`, `trades`.

Vi du doi target sang winrate cao ma khong sua code:

```toml
[targets]
description = "winrate >= 70%, PF >= 1.3"
monthly_return_min = 0.0001
monthly_return_max = 10.0
min_winrate = 0.70

[targets.achievement]
full_winrate_min = 0.70
oos_winrate_min = 0.65
full_profit_factor_min = 1.30
oos_profit_factor_min = 1.30
```

Neu doi muc tieu, thuong can dong bo them `[hard_filters]`, `[scoring.weights]`, `[scoring.params]`, `[warning_thresholds]`, `[risk]`, va grid trong `[optimization.*]`.

Vi du doi sang ETH hoac vang:

```toml
[market]
symbol = "ETHUSD"
asset_class = "crypto"
data_path = "../flect_mt5/cache/eth"
timeframes = ["H1", "H4", "D1"]
```

Voi vang/co phieu, chi can data folder co subfolder timeframe va file dang:

```text
<data_path>/<timeframe>/<SYMBOL>_<TIMEFRAME>_*.parquet
```

CSV cung duoc neu co cot `time/open/high/low/close/volume`.

## Them indicator moi

Khong dung raw Pine truc tiep. Pine trong `my-data/ref/tradingview` chi la reference.

De them indicator:

1. Tao file Python moi trong `my-data/backtest_v8/indicators/`, vi du `my_indicator.py`.
2. Import `IndicatorMetadata` va `SignalSet` tu `indicators.base`.
3. Viet class co `metadata` va ham `generate(df, params) -> list[SignalSet]`.
4. Export module-level `INDICATORS = [MyIndicator()]`.
5. Them block `[indicators.my_indicator_name]` vao `config.toml` va set `enabled = true`.

Interface toi thieu:

```python
from indicators.base import IndicatorMetadata, SignalSet

class MyIndicator:
    metadata = IndicatorMetadata(
        name="my_indicator",
        display_name="My Indicator",
        source="Manual Python conversion from <raw pine or formula>",
        repaint_risk="low",
    )

    def generate(self, df, params):
        long_signal = ...
        short_signal = ...
        return [SignalSet(self.metadata.name, "my_strategy", dict(params), long_signal, short_signal)]

INDICATORS = [MyIndicator()]
```

Tin hieu trong indicator la tin hieu dong nen hien tai. Runner se tu shift theo `execution.entry_lag_bars`, mac dinh vao lenh o open nen sau de tranh lookahead.

## Doc report

Report ngan:

```text
report_simple_vi.md
```

Dung de xem nhanh top setup, avg monthly return, best/worst month, max DD, winrate, trades/month, risk, ket luan.

Report chia 3 nhom:

- A `robust/stable`: qua hard filters full/train/OOS.
- B `high-return but suspicious`: return cao nhung bi loai vi DD, OOS/train lech, it lenh, PF ao, inactive months, gap data, v.v.
- C `rejected but gan dat`: bi loai nhung gan qua filter, dung de nghien cuu tiep.

Moi setup co them:

- `why_selected`: vi sao duoc dua vao nhom A.
- `why_not_live_trade_yet`: ly do chua nen live.

Report chi tiet:

```text
report_detail.md
report_detail.json
```

Dung cho ChatGPT/developer phan tich sau. Kem cac file:

- `kept_setups.csv`: setup qua filter.
- `rejected_setups.csv`: setup bi loai va ly do.
- `group_A_robust_stable.csv`: nhom A.
- `group_B_high_return_suspicious.csv`: nhom B.
- `group_C_rejected_near_miss.csv`: nhom C.
- `data_audit.csv`: kiem tra data.
- `pine_audit.csv`: Pine nao da convert, Pine nao chi la reference/chua dung.
- `setups/*_trades.csv`: trade log top setup.
- `setups/*_monthly_returns.csv`: monthly returns top setup.
- `setups/*_equity_curve.csv`: equity curve top setup.
- `setups/*_meta.json`: metadata/metric setup.

## Hieu warning

- `target_not_met`: setup chua dat rule trong `[targets.achievement]`.
- `avg_monthly_return_above_target_check_overfit`: loi nhuan qua cao, can nghi ngo overfit/rui ro.
- `large_data_gaps`: data co gap lon. Voi BTC, can can than neu data MT5 dong cuoi tuan trong khi crypto trade 24/7.
- `many_inactive_months`: nhieu thang khong co lenh.
- `profit_concentration_notice`: loi nhuan tap trung vao it lenh lon.
- `oos_much_weaker_than_train`: train dep nhung OOS yeu.
- `oos_much_better_than_train_check_regime_or_luck`: OOS dep bat thuong so voi train.
- `high_profit_factor_with_limited_trades`: PF cao nhung so lenh chua du.
- `indicator_repaint_risk_medium`: indicator co diem can audit them, vi du raw Pine goc co `security()`.

## Data gap BTC

`data_audit.csv` co cac cot:

- `gap_count_gt_1_5x`
- `weekend_gap_count`
- `weekday_gap_count`
- `missing_bar_ratio`
- `data_gap_warning`

Run `strict_filters` cho thay BTC cache hien tai thieu khoang 26-27% bar ky vong, chu yeu la gap cuoi tuan. Dieu nay khong lam backtest sai theo file data dang co, nhung la rui ro lon neu muc tieu la trade BTC 24/7. Nen xac minh bang data exchange 24/7 truoc khi live.

## Pine conversion status

Da convert va co the backtest:

- `adx_ema_combined.pine` -> `adx_ema_trend`, enabled.
- `WaveTrend Oscillator.pine` -> `wavetrend_cross`.
- `CM_Williams_Vix_Fix.pine` -> `williams_vix_fix`.
- `Squeeze Momentum Indicator [LazyBear].pine` -> `squeeze_momentum`.
- `SuperTrend by KivancOzbilgic.pine` -> `supertrend_flip`.
- `MacD Custom.pine` -> `macd_cross`, nhung raw Pine co `security()`, Python ban hien tai chi dung current timeframe.

Da convert mot phan nhung tat mac dinh:

- `Signal Forge [LuxAlgo] by LuxAlgo.pine` -> `signal_forge_lite`, disabled de cho parity test voi TradingView.

Chua cho vao backtest:

- `Predictive Breakout Channels.pine`: co pivot confirmation va HTF `request.security`; can audit repaint/lookahead ky hon.
- `PrecSniper.pine`: co HTF `request.security(...lookahead_on)`.
- `SMC.pipe`: co pivot/stateful structure va `request.security(...lookahead_on)`.

## Gia dinh backtest

- Fee va slippage tinh moi chieu theo config.
- Mot setup chi mo mot lenh tai mot thoi diem.
- Entry signal duoc shift `entry_lag_bars`.
- TP/SL check bang OHLC high/low.
- Neu TP va SL cung cham trong mot candle, dung `same_bar_exit_priority`, mac dinh la SL truoc.
- Metrics co full period, train va OOS.
- Score khong sort theo total return; score uu tien monthly return gan target, so lenh du, DD vua phai, OOS on, equity it gay va profit khong qua tap trung.

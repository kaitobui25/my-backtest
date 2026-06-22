import pandas as pd
df = pd.read_parquet(r"d:\Phong\03_Finance\trade\vectorbt-master\my-data\cache\m3\XAUUSD_M3_v2_new.parquet")
print(f"Rows: {len(df):,}")
print(f"Range: {df.index[0]} -> {df.index[-1]}")
print(f"Cols: {list(df.columns)}")
months = df.index.to_period("M").unique().tolist()
print(f"Months ({len(months)}): {months}")

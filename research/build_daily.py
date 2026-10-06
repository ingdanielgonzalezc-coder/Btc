import pandas as pd, numpy as np
import os, sys
B = os.path.join(sys.argv[1] if len(sys.argv) > 1 else "bitstamp-btcusd-minute-data", "data") + "/"
cols=["timestamp","close","volume"]
h=pd.read_csv(B+"historical/btcusd_bitstamp_1min_2012-2025.csv.gz", usecols=cols)
u=pd.read_csv(B+"updates/btcusd_bitstamp_1min_latest.csv", usecols=cols)
m=pd.concat([h,u]).drop_duplicates("timestamp",keep="last").sort_values("timestamp")
m["ts"]=pd.to_datetime(m.timestamp,unit="s")
m=m.set_index("ts")
# cierre diario = close del último minuto [23:59,00:00) -> etiqueta = día de la vela (convención Coinbase: vela del día D cierra a 00:00 de D+1)
d=m.close.resample("1D").last()
vol=m.volume.resample("1D").sum()
# precio a las 00:05 y 01:00 del día siguiente (para shortfall de ejecución)
p0005=m.close[(m.index.hour==0)&(m.index.minute==4)]; p0005.index=p0005.index.normalize()-pd.Timedelta(days=1)
out=pd.DataFrame({"close":d,"volume":vol,"px_0005_next":p0005.reindex(d.index)})
out.index.name="date"
out.to_csv("data/btc_daily_bitstamp.csv")
print(out.head(2)); print(out.tail(3)); print(len(out), out.close.isna().sum())

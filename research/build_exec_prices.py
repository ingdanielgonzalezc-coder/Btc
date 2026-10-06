import pandas as pd
import os, sys
B = os.path.join(sys.argv[1] if len(sys.argv) > 1 else "bitstamp-btcusd-minute-data", "data") + "/"
cols=["timestamp","close"]
m=pd.concat([pd.read_csv(B+"historical/btcusd_bitstamp_1min_2012-2025.csv.gz",usecols=cols),pd.read_csv(B+"updates/btcusd_bitstamp_1min_latest.csv",usecols=cols)]).drop_duplicates("timestamp",keep="last")
m["ts"]=pd.to_datetime(m.timestamp,unit="s"); m=m.set_index("ts").close.sort_index()
out={}
for h,mi,name in [(0,4,"x0005"),(0,59,"x0100"),(4,59,"x0500"),(11,59,"x1200")]:
    s=m[(m.index.hour==h)&(m.index.minute==mi)]; s.index=s.index.normalize()-pd.Timedelta(days=1); out[name]=s
pd.DataFrame(out).to_csv("data/exec_prices.csv")
print(pd.DataFrame(out).tail(2))

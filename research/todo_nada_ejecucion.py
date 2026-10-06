import sys; sys.path.insert(0, __import__("os").path.dirname(__import__("os").path.abspath(__file__)))
import pandas as pd, numpy as np, lib
from cands import px, tgt, trend
ex=pd.read_csv(__import__("os").path.join(__import__("os").path.dirname(__import__("os").path.abspath(__file__)),"data","exec_prices.csv"),index_col=0,parse_dates=True)
held=lib.band_held(tgt); v3=(trend>=0.75-1e-12).astype(float)
END="2026-10-03"
print("precios de ejecución faltantes 2014→:", {c:int(ex[c].reindex(px.loc['2014':END].index).isna().sum()) for c in ex.columns})
rows=[]
for name,col in [("cierre (teórico)",None),("00:05 UTC",'x0005'),("01:00 UTC",'x0100'),("05:00 UTC",'x0500'),("12:00 UTC",'x1200')]:
    e=None if col is None else ex[col].reindex(px.index)
    for k,t in [("v2.1",held),("V3",v3)]:
        try:
            r=lib.simulate(px,t,cost=0.0015,start="2014-01-01",end=END,exec_px=e)
        except ValueError as err:
            rows.append(dict(ejec=name,k=k,final=np.nan,dd=np.nan,err=str(err))); continue
        rows.append(dict(ejec=name,k=k,final=r.equity.iloc[-1],dd=(r.equity/r.equity.cummax()-1).min()))
T=pd.DataFrame(rows); print(T.pivot(index="ejec",columns="k",values=["final","dd"]).round(2).to_string())
h=px.loc["2014-01-01":END]; print("HODL", round(h.iloc[-1]/h.iloc[0],1))

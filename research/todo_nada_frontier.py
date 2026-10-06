import sys; sys.path.insert(0, __import__("os").path.dirname(__import__("os").path.abspath(__file__)))
import pandas as pd, numpy as np, lib
from cands import px, tgt, trend
held=lib.band_held(tgt); bin3=(trend>=0.75).astype(float)
vol=lib.ewm_vol(px)
S={"v2.1":held}
for a in [0.25,0.5,0.75]: S[f"Mezcla {int(a*100)}% todo/nada + {int((1-a)*100)}% v2.1"]=lib.band_held((a*bin3+(1-a)*tgt).fillna(0))
for tv in [0.5,0.65,0.8,1.0]: S[f"Todo/nada ≥3 × vol objetivo {int(tv*100)}%"]=lib.band_held((bin3*(tv/vol).clip(upper=1)).fillna(0))
S["Todo/nada ≥3"]=lib.band_held(bin3)
PER={"IS":("2014-01-01","2021-12-31"),"OOS":("2022-01-01",None),"Total":("2014-01-01",None)}
rows=[]
for k,t in S.items():
    r={"k":k}
    for p,(a,b) in PER.items():
        m=lib.summarize(lib.simulate(px,t,cost=0.0015,start=a,end=b))
        r[f"{p} CAGR"]=m["CAGR"]; r[f"{p} DD"]=m["MaxDD"]; r[f"{p} Sh"]=m["Sharpe"]
        if p=="Total": r["Final"]=m["Final"]; r["Exp"]=m["Exposure"]; r["Trades"]=m["TradesPY"]
    # start years beating HODL
    wins=0
    for y in range(2014,2026):
        s=f"{y}-01-01"
        wins+= lib.simulate(px,t,cost=0.0015,start=s).equity.iloc[-1] > lib.hodl(px,s).iloc[-1]
    r["Gana HODL"]=f"{wins}/12"; rows.append(r)
T=pd.DataFrame(rows).set_index("k"); pd.set_option("display.width",250)
print(T.round(3).to_string())
pd.to_pickle(S,"frontier_targets.pkl")

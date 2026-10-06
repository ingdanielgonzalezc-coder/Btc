import sys; sys.path.insert(0, __import__("os").path.dirname(__import__("os").path.abspath(__file__)))
import pandas as pd, numpy as np, lib
from cands import px, tgt, trend, VS, dc
held=lib.band_held(tgt)
PER={"IS 2014–21":("2014-01-01","2021-12-31"),"OOS 2022–26":("2022-01-01",None),"Total":("2014-01-01",None)}
def binary(score, thr): return (score>=thr-1e-12).astype(float)
C={
 "v2.1 (escalonado 0/25/50/75/100 × vol)": ("chg", held),
 "Todo/nada: ≥1 de 4 plazos arriba": ("chg", binary(trend,0.25)),
 "Todo/nada: ≥2 de 4 (mayoría o empate)": ("chg", binary(trend,0.5)),
 "Todo/nada: ≥3 de 4": ("chg", binary(trend,0.75)),
 "Todo/nada: 4 de 4": ("chg", binary(trend,1.0)),
 "Todo/nada ≥3 de 4 × vol-target": ("band", (binary(trend,0.75)*VS).clip(0,1)),
 "Todo/nada solo plazo 250d (precio > hace 1 año)": ("chg", (px>px.shift(250)).astype(float)),
 "Todo/nada media móvil 200d": ("chg", (px>px.rolling(200).mean()).astype(float)),
 "V3 Donchian escalonado × vol": ("band", (dc*VS).clip(0,1)),
 "Todo/nada Donchian ≥3 de 4 canales": ("chg", binary(dc,0.75)),
}
rows=[]
for name,(mode,t) in C.items():
    for p,(a,b) in PER.items():
        kw={"rebalance":"band","band":0.10} if mode=="band" else {}
        m=lib.summarize(lib.simulate(px,t.fillna(0),cost=0.0015,start=a,end=b,**kw))
        rows.append(dict(estrategia=name,periodo=p,**{k:m[k] for k in ["CAGR","Sharpe","MaxDD","Calmar","Exposure","TradesPY"]}))
for p in PER:
    h=lib.metrics(lib.hodl(px,*PER[p])); rows.append(dict(estrategia="HODL",periodo=p,CAGR=h["CAGR"],Sharpe=h["Sharpe"],MaxDD=h["MaxDD"],Calmar=h["Calmar"],Exposure=1,TradesPY=0))
T=pd.DataFrame(rows)
pd.set_option("display.width",250); pd.set_option("display.max_colwidth",50)
for p in PER:
    print("\n==",p); print(T[T.periodo==p].drop(columns="periodo").round(3).to_string(index=False))
T.to_csv("binary_results.csv",index=False)
# bootstrap OOS vs v2.1 for binary ≥2 and ≥3
b=lib.simulate(px,held,cost=0.0015,start="2022-01-01").equity.pct_change().dropna()
for name in ["Todo/nada: ≥2 de 4 (mayoría o empate)","Todo/nada: ≥3 de 4","Todo/nada media móvil 200d"]:
    a=lib.simulate(px,C[name][1].fillna(0),cost=0.0015,start="2022-01-01").equity.pct_change().dropna()
    print(name, "ΔSharpe OOS vs v2.1:", lib.boot_sharpe_diff(a,b,B=1000,seed=3))

import sys; sys.path.insert(0, __import__("os").path.dirname(__import__("os").path.abspath(__file__)))
import pandas as pd, numpy as np, lib
px=lib.load_prices(); r=px.pct_change().fillna(0); COST=0.0015; START="2014-01-01"
votes=lambda l: pd.concat([(px>px.shift(L)).astype(float) for L in l],axis=1).mean(axis=1)
def hyst(v,en,ex):
    on=0; out=np.zeros(len(v)); vv=v.values
    for t in range(len(vv)):
        if on==0 and vv[t]>=en-1e-9: on=1
        elif on==1 and vv[t]<=ex+1e-9: on=0
        out[t]=on
    return pd.Series(out,index=v.index)
def eq(w):
    w=w.loc[START:]; rr=r.loc[START:]
    return (1+w.shift(1).fillna(0)*rr-w.diff().abs().fillna(w.iloc[0])*COST).cumprod()
H=px.loc[START:]/px.loc[START]
def windows(e, years):
    # todas las ventanas de N años con inicio mensual: fracción en que gana a HODL
    starts=pd.date_range(START, px.index[-1]-pd.DateOffset(years=years), freq="MS")
    w=0
    for s in starts:
        en=s+pd.DateOffset(years=years)
        i0=e.index.get_indexer([s],method="bfill")[0]; i1=e.index.get_indexer([en],method="ffill")[0]
        w+= (e.iloc[i1]/e.iloc[i0]) > (H.iloc[i1]/H.iloc[i0])
    return w/len(starts)
S={
 "Histéresis 10/30/60/120 (≥3 entra, ≤1 sale)": hyst(votes((10,30,60,120)),0.75,0.25),
 "Histéresis 20/60/120/250 (≥3 entra, ≤1 sale)": hyst(votes((20,60,120,250)),0.75,0.25),
 "Histéresis 15/50/100/200 (≥3 entra, ≤1 sale)": hyst(votes((15,50,100,200)),0.75,0.25),
 "Histéresis 20/50/100/200 (≥3 entra, ≤1 sale)": hyst(votes((20,50,100,200)),0.75,0.25),
 "Histéresis 25/75/150/300 (≥3 entra, ≤1 sale)": hyst(votes((25,75,150,300)),0.75,0.25),
 "Histéresis 30/90/180/365 (≥3 entra, ≤1 sale)": hyst(votes((30,90,180,365)),0.75,0.25),
 "Todo/nada 20/60/120/250 ≥3": (votes((20,60,120,250))>=0.75-1e-9).astype(float),
 "Todo/nada 10/30/60/120 ≥3": (votes((10,30,60,120))>=0.75-1e-9).astype(float),
 "HODL": pd.Series(1.0,index=px.index),
}
rows=[]
for k,w in S.items():
    e=eq(w); dd=e/e.cummax()-1
    trough=dd.idxmin(); peak=e.loc[:trough].idxmax()
    rows.append(dict(estrategia=k, final=e.iloc[-1], maxdd=dd.min(), dd_desde=peak.date(), dd_hasta=trough.date(),
        exp=w.loc[START:].mean(), trades=(w.loc[START:].diff().abs()>0).sum()/12.76,
        **{f"gana {y}a": windows(e,y) for y in (1,2,3,4)}))
T=pd.DataFrame(rows).set_index("estrategia"); pd.set_option("display.width",250)
print(T.round(2).to_string())
# Detalle de la caída de la histéresis 10/30/60/120
w=S["Histéresis 10/30/60/120 (≥3 entra, ≤1 sale)"]; e=eq(w)
dd=e/e.cummax()-1; t=dd.idxmin(); p=e.loc[:t].idxmax()
print("\nCaída máx histéresis 10/30/60/120:", p.date(),"→",t.date(), f"{dd.min():.0%}", "| BTC en ese tramo:", f"{px.loc[t]/px.loc[p]-1:.0%}", "| % del tramo invertido:", f"{w.loc[p:t].mean():.0%}")

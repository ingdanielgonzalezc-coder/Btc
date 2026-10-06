import sys; sys.path.insert(0, __import__("os").path.dirname(__import__("os").path.abspath(__file__)))
import pandas as pd, numpy as np, lib, itertools
px=lib.load_prices(); r=px.pct_change().fillna(0); COST=0.0015
vol=lib.ewm_vol(px)
START="2014-01-01"
def eq_from_w(w):
    w=w.fillna(0).clip(0,1).loc[START:]; rr=r.loc[START:]
    wp=w.shift(1).fillna(0); turn=w.diff().abs().fillna(w.iloc[0])
    return (1+wp*rr-turn*COST).cumprod()
YRS=[f"{y}-01-01" for y in range(2014,2026)]
H=px.loc[START:]
def score(e):
    ratios=[]
    for s in YRS:
        i=e.index.get_indexer([pd.Timestamp(s)])[0]
        se=e.iloc[-1]/e.iloc[i-1] if i>0 else e.iloc[-1]
        sh=H.iloc[-1]/H.iloc[i]
        ratios.append(se/sh)
    ratios=np.array(ratios)
    isv=e.loc[:"2021-12-31"].iloc[-1]; oos=e.iloc[-1]/e.loc[:"2021-12-31"].iloc[-1]
    dd=(e/e.cummax()-1).min()
    return dict(final=e.iloc[-1], maxdd=dd, IS=isv, OOS=oos, wins=int((ratios>1).sum()), med_ratio=float(np.median(ratios)), min_ratio=float(ratios.min()))
votes=lambda lbs: pd.concat([(px>px.shift(L)).astype(float) for L in lbs],axis=1).mean(axis=1)
res=[]
def add(fam,name,w,params=None):
    s=score(eq_from_w(w)); s.update(fam=fam,name=name); res.append(s)
# A votos binarios
LBS={"10/30/60/120":(10,30,60,120),"15/50/100/200":(15,50,100,200),"20/60/120/250":(20,60,120,250),"20/50/100/200":(20,50,100,200),"25/75/150/300":(25,75,150,300),"30/90/180/365":(30,90,180,365),"40/80/160/320":(40,80,160,320),"10/20/50/100/200":(10,20,50,100,200),"5/10/20/40/80/160":(5,10,20,40,80,160)}
for k,l in LBS.items():
    v=votes(l); n=len(l)
    for m in range(1,n+1): add("A votos todo/nada",f"{k} ≥{m}/{n}",(v>=m/n-1e-9).astype(float))
    add("J votos graduado sin vol",f"{k} graduado",v)
    add("K votos graduado ×vol80",f"{k} graduado ×vol80",v*(0.8/vol).clip(upper=1))
# B momentum simple
for L in [20,30,45,60,90,120,150,180,200,250,300,365]: add("B momentum simple",f"P>P[-{L}]",(px>px.shift(L)).astype(float))
# C precio sobre media
for N in [20,30,50,75,100,125,150,200,250,300]:
    add("C precio>SMA",f"SMA{N}",(px>px.rolling(N).mean()).astype(float))
    add("C precio>EMA",f"EMA{N}",(px>px.ewm(span=N).mean()).astype(float))
# D cruces
for f,s in [(5,20),(10,30),(10,50),(20,50),(20,100),(30,100),(50,100),(50,150),(50,200),(100,200)]:
    add("D cruce SMA",f"SMA{f}>SMA{s}",(px.rolling(f).mean()>px.rolling(s).mean()).astype(float))
# E Donchian single
def donch(N,M):
    hi=px.shift(1).rolling(N).max().values; lo=px.shift(1).rolling(M).min().values; p=px.values; on=0; out=np.zeros(len(p))
    for t in range(len(p)):
        if np.isnan(hi[t]): continue
        if on==0 and p[t]>hi[t]: on=1
        elif on==1 and p[t]<lo[t]: on=0
        out[t]=on
    return pd.Series(out,index=px.index)
for N in [20,40,60,90,120,180,250]:
    for frac in [0.25,0.5,1.0]:
        add("E Donchian",f"N{N} salida{int(N*frac)}",donch(N,max(int(N*frac),5)))
# F histéresis en votos (20/60/120/250 y 10/30/60/120)
def hyst(v,enter,exit_):
    on=0; out=np.zeros(len(v)); vv=v.values
    for t in range(len(vv)):
        if on==0 and vv[t]>=enter-1e-9: on=1
        elif on==1 and vv[t]<=exit_+1e-9: on=0
        out[t]=on
    return pd.Series(out,index=v.index)
for k in ["20/60/120/250","10/30/60/120","15/50/100/200"]:
    v=votes(LBS[k])
    for en,ex in [(0.75,0.25),(0.75,0.0),(1.0,0.25),(1.0,0.5),(0.5,0.0),(1.0,0.0)]:
        add("F histéresis",f"{k} entra≥{en} sale≤{ex}",hyst(v,en,ex))
# G todo/nada con tope de vol
for k in ["20/60/120/250","10/30/60/120"]:
    b=(votes(LBS[k])>=0.75-1e-9).astype(float)
    for tv in [0.8,1.0,1.2]: add("G todo/nada ×tope vol",f"{k} ≥3/4 tope{int(tv*100)}%",b*(tv/vol).clip(upper=1))
# H decisión semanal
b=(votes(LBS["20/60/120/250"])>=0.75-1e-9).astype(float)
add("H semanal","20/60/120/250 ≥3/4 lunes",b.where(b.index.dayofweek==0).ffill())
# referencias
add("Ref","HODL",pd.Series(1.0,index=px.index))
add("Ref","v2.1",lib.band_held(lib.v21_target(px)[0]))
R=pd.DataFrame(res); R.to_pickle("maxcap.pkl")
print("candidatos:",len(R))
pd.set_option("display.width",250); pd.set_option("display.max_rows",400)
cols=["fam","name","final","maxdd","IS","OOS","wins","med_ratio","min_ratio"]
print("\nTOP 25 por capital final desde 2014:"); print(R.sort_values("final",ascending=False)[cols].head(25).round(2).to_string(index=False))
print("\nTOP 25 por mediana de ventaja vs HODL (12 años de inicio):"); print(R.sort_values("med_ratio",ascending=False)[cols].head(25).round(2).to_string(index=False))
print("\nMejor de cada familia (por mediana de ventaja):"); print(R.sort_values("med_ratio",ascending=False).groupby("fam").head(1)[cols].round(2).to_string(index=False))
print("\nReferencias:"); print(R[R.fam=="Ref"][cols].round(2).to_string(index=False))
print("\nTodo/nada actual:"); print(R[R.name=="20/60/120/250 ≥3/4"][cols].round(2).to_string(index=False))

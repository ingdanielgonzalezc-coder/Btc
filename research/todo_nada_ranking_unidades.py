"""Ranking de 147 reglas con el MISMO motor units/cash (lib.simulate), teórico y con
ejecución a las 05:00 UTC del día siguiente. Pesos parciales: banda 0,10 sobre el
objetivo + rebalanceo al cambiar (regla v2.1). Binarios: rebalanceo al cambiar."""
import sys; sys.path.insert(0, __import__("os").path.dirname(__import__("os").path.abspath(__file__)))
import pandas as pd, numpy as np, lib
src=open(__import__("os").path.join(__import__("os").path.dirname(__import__("os").path.abspath(__file__)),"todo_nada_maxcap.py")).read()
src=src.replace("def add(fam,name,w,params=None):\n    s=score(eq_from_w(w)); s.update(fam=fam,name=name); res.append(s)",
                "W={}\ndef add(fam,name,w,params=None):\n    W[(fam,name)]=w.fillna(0).clip(0,1)")
exec(src.split("R=pd.DataFrame(res)")[0])
ex=pd.read_csv(__import__("os").path.join(__import__("os").path.dirname(__import__("os").path.abspath(__file__)),"datos","exec_prices.csv"),index_col=0,parse_dates=True)["x0500"].reindex(px.index)
END="2026-10-03"; H=px.loc[START:END]
def start_ratios(e):
    out=[]
    for s in YRS:
        i=e.index.get_indexer([pd.Timestamp(s)])[0]
        out.append((e.iloc[-1]/(e.iloc[i-1] if i>0 else 1.0))/(H.iloc[-1]/H.iloc[i]))
    return np.array(out)
rows=[]; RET={}
for (fam,name),w in W.items():
    if name=="HODL": continue
    binary=set(np.unique(w.values))<= {0.0,1.0}
    t=w if binary else lib.band_held(w)
    for mode,e in [("teórico",None),("05:00",ex)]:
        r=lib.simulate(px,t,cost=0.0015,start=START,end=END,exec_px=e)
        eq=r.equity; rr=start_ratios(eq)
        rows.append(dict(fam=fam,name=name,mode=mode,final=eq.iloc[-1],maxdd=(eq/eq.cummax()-1).min(),
                         wins=int((rr>1).sum()),med_ratio=float(np.median(rr)),min_ratio=float(rr.min()),
                         IS=eq.loc[:"2021-12-31"].iloc[-1], OOS=eq.iloc[-1]/eq.loc[:"2021-12-31"].iloc[-1]))
        if mode=="05:00": RET[(fam,name)]=eq.pct_change().fillna(eq.iloc[0]-1)
R=pd.DataFrame(rows); R.to_pickle("maxcap_uc.pkl")
pd.set_option("display.width",250)
cols=["fam","name","final","maxdd","wins","med_ratio","min_ratio","OOS"]
for mode in ["teórico","05:00"]:
    S=R[R["mode"]==mode].sort_values("final",ascending=False)
    print(f"\n=== {mode}: top 12 por capital final (de {len(S)})"); print(S[cols].head(12).round(2).to_string(index=False))
    v3=S[S.name=="20/60/120/250 ≥3/4"]; print("V3 elegida:", v3[cols].round(2).to_string(index=False,header=False), "| puesto", int((S.final>v3.final.iloc[0]).sum())+1)
# comparar con ranking aproximado
A=pd.read_pickle("todo_nada_maxcap.pkl")[["name","final"]].rename(columns={"final":"aprox"})
M=R[R["mode"]=="teórico"].merge(A,on="name"); M["dif%"]=(M.final/M.aprox-1)*100
print("\nDiferencia motor units/cash vs aproximación: mediana |dif| %.1f%%, máx %.1f%%; en binarias máx %.2f%%"%(
      M["dif%"].abs().median(), M["dif%"].abs().max(), M[M.fam.str.match("^[ABCDEFH]")]["dif%"].abs().max()))
print("Top-10 coincide (teórico vs aprox):", len(set(M.nlargest(10,'final').name)&set(M.nlargest(10,'aprox').name)),"de 10")
# walk-forward con ejecución 05:00
D=pd.DataFrame(RET).loc[START:END]
fixed=("A votos todo/nada","20/60/120/250 ≥3/4")
for lb in [None,4]:
    out=[]
    for y in range(2017,2027):
        hist=D.loc[:f"{y-1}-12-31"]
        if lb: hist=hist.loc[f"{y-lb}-01-01":]
        best=(1+hist).prod().idxmax(); out.append(D.loc[f"{y}-01-01":f"{y}-12-31",best])
    wf=pd.concat(out)
    print(f"Walk-forward 05:00 ({'historia completa' if not lb else 'últimos 4 años'}) 2017→: {(1+wf).prod():.1f}× | V3 fija {(1+D.loc['2017':,fixed]).prod():.1f}× | HODL {H.loc['2016-12-31':].iloc[-1]/H.loc['2016-12-31':].iloc[0]:.1f}×")

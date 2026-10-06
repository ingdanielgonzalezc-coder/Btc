import sys; sys.path.insert(0, __import__("os").path.dirname(__import__("os").path.abspath(__file__)))
import pandas as pd, numpy as np
exec(open(__import__("os").path.join(__import__("os").path.dirname(__import__("os").path.abspath(__file__)),"todo_nada_maxcap.py")).read().split("res=[]")[0])   # reutiliza funciones y datos
R=pd.read_pickle("maxcap.pkl")
# reconstruir pesos de todos los candidatos (mismo orden) para walk-forward
import importlib
src=open(__import__("os").path.join(__import__("os").path.dirname(__import__("os").path.abspath(__file__)),"todo_nada_maxcap.py")).read()
src=src.replace("def add(fam,name,w,params=None):\n    s=score(eq_from_w(w)); s.update(fam=fam,name=name); res.append(s)",
                "W={}\ndef add(fam,name,w,params=None):\n    W[(fam,name)]=w.fillna(0).clip(0,1)")
src=src.split("R=pd.DataFrame(res)")[0]
exec(src)
rets={k:(w.shift(1).fillna(0)*r - w.diff().abs().fillna(0)*COST).loc[START:] for k,w in W.items() if k[1] not in ("HODL",)}
D=pd.DataFrame(rets)
fixed=("A votos todo/nada","20/60/120/250 ≥3/4")
for lookback_years in [None,4]:
    out=[]; picks=[]
    for y in range(2017,2027):
        hist=D.loc[:f"{y-1}-12-31"]
        if lookback_years: hist=hist.loc[f"{y-lookback_years}-01-01":]
        best=(1+hist).prod().idxmax(); picks.append((y,best[1]))
        out.append(D.loc[f"{y}-01-01":f"{y}-12-31",best])
    wf=pd.concat(out); fx=D.loc["2017-01-01":,fixed]; hd=px.loc["2016-12-31":].pct_change().dropna()
    lab="historia completa" if not lookback_years else f"últimos {lookback_years} años"
    print(f"\nWalk-forward ({lab}) 2017–2026: elegir cada año el mejor de {D.shape[1]} → {(1+wf).prod():.1f}×  | todo/nada fijo 20/60/120/250 {(1+fx).prod():.1f}× | HODL {(1+hd).prod():.1f}×")
    print("  elecciones:", picks)
# vecindad: votos ≥3/4 (o 75%) en todos los sets
print("\nVotos todo/nada, umbral ~75%, por set de plazos:")
print(R[(R.fam=="A votos todo/nada")&(R.name.str.contains("≥3/4|≥4/5|≥5/6"))][["name","final","maxdd","OOS","wins","med_ratio"]].round(2).to_string(index=False))
print("\nPrecio > SMA N:"); print(R[R.fam=="C precio>SMA"][["name","final","maxdd","OOS","wins","med_ratio"]].round(2).to_string(index=False))

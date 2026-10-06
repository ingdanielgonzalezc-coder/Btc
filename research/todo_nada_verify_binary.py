import sys; sys.path.insert(0, __import__("os").path.dirname(__import__("os").path.abspath(__file__)))
import pandas as pd, numpy as np, lib
px=lib.load_prices()
# 1) Implementación independiente, vectorizada, sin lib.simulate
def binary_equity(px, lbs=(20,60,120,250), thr=0.75, cost=0.0015, start="2014-01-01", end=None, lag=0):
    tr=pd.concat([(px>px.shift(L)).astype(float) for L in lbs],axis=1).mean(axis=1)
    w=(tr>=thr-1e-12).astype(float).shift(lag)           # decisión al cierre t
    w=w.loc[start:end]; r=px.pct_change().loc[start:end]
    wp=w.shift(1).fillna(0)                              # posición de ayer gana el retorno de hoy
    turn=w.diff().abs().fillna(w.iloc[0])
    eq=(1+wp*r.fillna(0)-turn*cost).cumprod()
    return eq
e=binary_equity(px); h=px.loc["2014-01-01":]/px.loc["2014-01-01":].iloc[0]
print("Independiente: todo/nada ≥3 desde 2014: %.1f× | HODL %.1f×"%(e.iloc[-1],h.iloc[-1]))
# 2) Desfase de 1 día (decidir con el cierre de ayer) — prueba anti-lookahead
print("Con 1 día extra de retraso: %.1f×"%binary_equity(px,lag=1).iloc[-1])
# 3) Vecindad de parámetros
print("\nVecindad (capital final desde 2014, 15 pb):")
for lbs in [(20,60,120,250),(10,30,60,120),(30,90,180,365),(15,50,100,200),(25,75,150,300),(20,50,100,200),(40,80,160,320)]:
    print(lbs, " ".join(f"thr{t}: {binary_equity(px,lbs,t).iloc[-1]:7.0f}×" for t in (0.5,0.75,1.0)))
# 4) Costos
print("\nCostos:", {c: round(binary_equity(px,cost=c/1e4).iloc[-1]) for c in (7,15,30,50,100)})
# 5) Por sub-periodo (múltiplo y vs HODL)
print("\nTramos:")
for a,b in [("2014-01-01","2017-12-31"),("2018-01-01","2021-12-31"),("2022-01-01",None),("2018-01-01",None)]:
    eb=binary_equity(px,start=a,end=b); hb=px.loc[a:b]/px.loc[a:b].iloc[0]
    print(f"{a[:4]}–{(b or '2026')[:4]}: todo/nada {eb.iloc[-1]:.1f}×  HODL {hb.iloc[-1]:.1f}×  peor caída {(eb/eb.cummax()-1).min():.0%} vs {(hb/hb.cummax()-1).min():.0%}")
# 6) Fin de periodo variable: ¿la ventaja depende de la fecha de hoy?
print("\nTerminando en distintas fechas (inicio 2014):")
for end in ["2017-12-17","2018-12-15","2021-11-10","2022-11-21","2024-03-14","2026-10-05"]:
    eb=binary_equity(px,end=end); hb=px.loc["2014-01-01":end]/px.loc["2014-01-01"]
    print(f"hasta {end}: todo/nada {eb.iloc[-1]:.0f}×  HODL {hb.iloc[-1]:.0f}×")

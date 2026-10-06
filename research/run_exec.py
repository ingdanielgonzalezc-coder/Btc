import sys; sys.path.insert(0, __import__("os").path.dirname(__import__("os").path.abspath(__file__)))
import pandas as pd, numpy as np, lib
from cands import px, tgt, VS, dc, t5
ex=pd.read_csv("data/exec_prices.csv",index_col=0,parse_dates=True)
held=lib.band_held(tgt); c4=(dc*VS).clip(0,1)
for name in [None,"x0005","x0100","x0500","x1200"]:
    e=None if name is None else ex[name].reindex(px.index)
    r0=lib.summarize(lib.simulate(px,held,cost=0.0015,start="2022-01-01",exec_px=e))
    r4=lib.summarize(lib.simulate(px,c4,cost=0.0015,start="2022-01-01",exec_px=e,rebalance="band",band=0.10))
    f0=lib.summarize(lib.simulate(px,held,cost=0.0015,start="2014-01-01",exec_px=e))
    f4=lib.summarize(lib.simulate(px,c4,cost=0.0015,start="2014-01-01",exec_px=e,rebalance="band",band=0.10))
    print(f"{name or 'cierre'}: OOS C0 {r0['Sharpe']:.3f}/{r0['CAGR']:.3f}  C4 {r4['Sharpe']:.3f}/{r4['CAGR']:.3f} | FULL C0 {f0['Sharpe']:.3f}/{f0['CAGR']:.3f} C4 {f4['Sharpe']:.3f}/{f4['CAGR']:.3f}")

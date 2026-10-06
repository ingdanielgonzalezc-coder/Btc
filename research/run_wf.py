import sys; sys.path.insert(0, __import__("os").path.dirname(__import__("os").path.abspath(__file__)))
import pandas as pd, numpy as np, lib
from cands import px, VS
cfg={}
for lbs in [(10,30,60,120),(20,60,120,250),(30,90,180,365),(20,60,120),(60,120,250)]:
    for tv in [0.4,0.5,0.6]:
        t,_,_=lib.v21_target(px,lookbacks=lbs,target_vol=tv)
        cfg[f"vote{lbs}_tv{tv}"]=lib.simulate(px,lib.band_held(t),cost=0.0015,start="2014-01-01").equity.pct_change()
    d=lib.donchian_ensemble(px,lbs)
    cfg[f"donch{lbs}"]=lib.simulate(px,(d*VS).clip(0,1),cost=0.0015,start="2014-01-01",rebalance="band",band=0.10).equity.pct_change()
R=pd.DataFrame(cfg).fillna(0)
wf=[]; picks=[]
for y in range(2018,2027):
    hist=R.loc[:f"{y-1}-12-31"]; sr=hist.mean()/hist.std()
    best=sr.idxmax(); picks.append((y,best)); wf.append(R.loc[f"{y}-01-01":f"{y}-12-31",best])
wf=pd.concat(wf)
base=R["vote(20, 60, 120, 250)_tv0.5"].loc["2018-01-01":]
def sh(r): return r.mean()/r.std()*np.sqrt(365)
print("Walk-forward 2018-2026 Sharpe %.3f vs v2.1 fijo %.3f"%(sh(wf),sh(base)))
print("OOS 2022+: WF %.3f vs fijo %.3f"%(sh(wf.loc['2022':]),sh(base.loc['2022':])))
for p in picks: print(p)
print(lib.boot_sharpe_diff(wf.loc['2018':],base.loc['2018':],B=1000))
R.to_pickle("grid_returns.pkl")

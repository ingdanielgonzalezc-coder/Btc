import sys; sys.path.insert(0, __import__("os").path.dirname(__import__("os").path.abspath(__file__)))
import pandas as pd, numpy as np, lib
from cands import CANDS
pd.set_option("display.width",220); pd.set_option("display.float_format",lambda x:f"{x:,.3f}")
oos={k:f("2022-01-01",None) for k,f in CANDS.items()}
full={k:f("2014-01-01",None) for k,f in CANDS.items()}
tab=pd.DataFrame({k:lib.summarize(v) for k,v in oos.items()}).T
h=lib.hodl(lib.load_prices(),"2022-01-01"); hm=lib.metrics(h)
print("OOS 2022-2026:"); print(tab[["CAGR","Vol","Sharpe","MaxDD","Calmar","Exposure","TradesPY","TurnoverPY","CostPY","Final"]])
print("HODL OOS: CAGR %.3f Sharpe %.3f MaxDD %.3f Final %.3f"%(hm["CAGR"],hm["Sharpe"],hm["MaxDD"],hm["Final"]))
tf=pd.DataFrame({k:lib.summarize(v) for k,v in full.items()}).T
print("FULL 2014-2026:"); print(tf[["CAGR","Sharpe","MaxDD","Calmar","TurnoverPY"]])
ra=oos["C4"].equity.pct_change().dropna(); rb=oos["C0"].equity.pct_change().dropna()
print("Bootstrap ΔSharpe C4−C0 OOS:", lib.boot_sharpe_diff(ra,rb,B=2000))
fa=full["C4"].equity.pct_change().dropna(); fb=full["C0"].equity.pct_change().dropna()
print("Bootstrap ΔSharpe C4−C0 FULL:", lib.boot_sharpe_diff(fa,fb,B=1000))
# DSR on IS selection (N=6) and on OOS
isr={k:f("2014-01-01","2021-12-31").equity.pct_change().dropna() for k,f in CANDS.items()}
srs=np.array([r.mean()/r.std() for r in isr.values()])
print("DSR C4 IS N=6:", lib.deflated_sharpe(isr["C4"],6,srs.var(ddof=1)))
print("DSR C0 IS N=666 (var from 6):", lib.deflated_sharpe(isr["C0"],666,srs.var(ddof=1)))
print("Sharpe SE OOS C4/C0:", lib.sharpe_se(ra), lib.sharpe_se(rb))
# cost sensitivity OOS
for c in [0.0007,0.0015,0.003,0.005,0.01]:
    print(f"{c*1e4:.0f}bps OOS Sharpe C0 {lib.summarize(CANDS['C0']('2022-01-01',None,c))['Sharpe']:.2f}  C4 {lib.summarize(CANDS['C4']('2022-01-01',None,c))['Sharpe']:.2f}")
pd.to_pickle({"oos":oos,"full":full},"res_cands.pkl")

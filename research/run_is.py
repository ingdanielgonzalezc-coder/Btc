import sys; sys.path.insert(0, __import__("os").path.dirname(__import__("os").path.abspath(__file__)))
import pandas as pd, numpy as np, lib
from cands import CANDS
pd.set_option("display.width",220); pd.set_option("display.float_format",lambda x:f"{x:,.3f}")
rows={}
for k,f in CANDS.items():
    rows[k]=lib.summarize(f("2014-01-01","2021-12-31"))
print(pd.DataFrame(rows).T[["Sharpe","MaxDD","Calmar","TurnoverPY"]])

"""Cono esperado para el dashboard: percentiles del capital simulado por bootstrap
estacionario (bloque medio 20 días) de los retornos diarios 2022–2026 de cada versión,
con los supuestos del motor (7 pb, cash 4%). Escribe ../dashboard/src/cone.json."""
import os, sys, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np, lib
from cands import px, held_v21, target_v3

H, STEP, B, BLOCK = 1095, 5, 4000, 20
rng = np.random.default_rng(2026)
out = {"horizon_days": list(range(0, H + 1, STEP)), "pcts": [5, 25, 50, 75, 95],
       "source": "bootstrap estacionario de retornos diarios 2022-01-01..2026-10-05, 7 pb, cash 4%"}
for name, tgt, kw in [("v21", held_v21, {}), ("v3", target_v3, {})]:
    r = lib.simulate(px, tgt, cost=0.0007, cash_apy=0.04, start="2022-01-01", **kw).equity.pct_change().dropna().values
    n = len(r); paths = np.empty((B, H))
    for b in range(B):
        idx = np.empty(H, dtype=int); i = rng.integers(n)
        for t in range(H):                      # bootstrap estacionario: largo H, población n
            idx[t] = i
            i = rng.integers(n) if rng.random() < 1.0 / BLOCK else (i + 1) % n
        paths[b] = np.cumprod(1 + r[idx])
    paths = np.hstack([np.ones((B, 1)), paths])[:, ::STEP]
    out[name] = {str(p): [round(float(v), 4) for v in np.percentile(paths, p, axis=0)] for p in out["pcts"]}
dst = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "dashboard", "src", "cone.json")
json.dump(out, open(dst, "w"), separators=(",", ":"))
print("ok", dst, {k: out[k]["50"][-1] for k in ("v21", "v3")})

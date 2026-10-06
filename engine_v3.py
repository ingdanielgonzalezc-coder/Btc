"""
engine_v3.py — Motor V3 del paper trading BTC: TODO O NADA (corre en paralelo a v2.1)
================================================================================
Regla: 100% BTC cuando al menos 3 de los 4 plazos (20/60/120/250 días) están al alza
(precio de hoy > precio de hace L días); 0% (cash) cuando quedan 2 o menos.

  - El voto por plazo es EXACTAMENTE el trend_score de v2.1 (mismos plazos, misma
    comparación estricta). V3 solo cambia qué se hace con él: no hay escalones ni
    vol-targeting; o se está completo o se está fuera.
  - Rebalanceo solo cuando el objetivo cambia (0 ↔ 1). Entre cambios, nada.

Objetivo explícito: maximizar el capital final, aceptando caídas mayores que v2.1.
Backtest Bitstamp 2014–2026, 15 pb: 486× vs 114× HODL vs 118× v2.1; peor caída −60%.
Ver ESPECIFICACION_v3.md y research/run_todo_nada.py.

Contabilidad: la de v2.1 (units + cash, arranque desde cash, sin rebase, sin
apalancamiento, ejecución al cierre). Determinismo: estado recomputado desde el día 0.

Registro reconstruido: PAPER_START_V3 se fijó en 2026-08-17 (mismo inicio que v2.1)
para comparar ambas en el gráfico. Las filas con fecha < LIVE_FROM_V3 se calcularon
DESPUÉS de los hechos (columna live = 0). Son deterministas, pero no son evidencia
forward: la comparación honesta empieza en LIVE_FROM_V3.
"""

import numpy as np
import pandas as pd

# ===== Parámetros (compartidos con v2.1 para comparar like-for-like) =====
LOOKBACKS  = (20, 60, 120, 250)
FEE        = 0.0004
SLIP       = 0.0003
STABLE_APY = 0.04
ANN        = 365

# ===== Parámetro propio de V3 (congelado) =====
MIN_VOTES  = 3            # plazos al alza necesarios para estar 100% invertido

# ===== Despliegue =====
PAPER_START_V3 = "2026-08-17"   # = PAPER_START_V21, para comparar en el mismo gráfico
LIVE_FROM_V3   = "2026-10-06"   # primera vela registrada en vivo (cierra 00:00 UTC del 07-10)
WARMUP_DAYS    = 420
SHEET_TAB_V3   = "track_record_v3"

COLUMNS_V3 = [
    "date", "btc_price", "price_source",
    "votes_up", "trend_score", "target_weight",
    "weight_pre", "weight_post", "action", "trade_pct", "trade_cost",
    "units", "cash", "equity",
    "daily_return", "hodl_equity", "cash_equity", "drawdown",
    "live", "code_sha", "generated_at_utc",
]
PROVENANCE_COLS = frozenset({"code_sha", "generated_at_utc"})

_ROUND = {
    "btc_price": 2, "votes_up": 0, "trend_score": 6, "target_weight": 6,
    "weight_pre": 6, "weight_post": 6, "trade_pct": 6, "trade_cost": 10,
    "units": 10, "cash": 10, "equity": 10,
    "daily_return": 8, "hodl_equity": 8, "cash_equity": 8, "drawdown": 8, "live": 0,
}

CASH_D = (1 + STABLE_APY) ** (1 / ANN) - 1
COST_R = FEE + SLIP
_EPS = 1e-9


# ============================================================================
# SEÑAL
# ============================================================================
def compute_signal_v3(precios):
    if not precios.index.is_monotonic_increasing:
        raise ValueError("serie de precios desordenada")
    if precios.index.has_duplicates:
        raise ValueError("serie de precios con fechas duplicadas")
    votes = pd.concat([(precios > precios.shift(L)).astype(float) for L in LOOKBACKS], axis=1)
    votes_up = votes.sum(axis=1)
    sig = pd.DataFrame({
        "btc_price": precios,
        "daily_return": precios.pct_change(),
        "votes_up": votes_up,
        "trend_score": votes.mean(axis=1),
        "target_weight": (votes_up >= MIN_VOTES).astype(float),
    })
    sig.index.name = "date"
    return sig


# ============================================================================
# CONTABILIDAD (v2.1 §4, con rebalanceo solo al cambiar el objetivo 0 ↔ 1)
# ============================================================================
def run_accounting_v3(sig):
    n = len(sig)
    cols = ["weight_pre", "weight_post", "trade_pct", "trade_cost",
            "units", "cash", "equity", "hodl_equity", "cash_equity"]
    if n == 0:
        return pd.DataFrame(columns=cols, index=sig.index)
    px = sig["btc_price"].to_numpy(dtype=float)
    tw = sig["target_weight"].to_numpy(dtype=float)
    ret = sig["daily_return"].to_numpy(dtype=float)
    out = {c: np.zeros(n) for c in cols}
    units, cash = 0.0, 1.0

    for t in range(n):
        if t > 0:
            cash *= (1 + CASH_D)
        eq_pre = units * px[t] + cash
        w_pre = units * px[t] / eq_pre
        dv = cost = 0.0
        if t == 0 or tw[t] != tw[t - 1]:
            dv = tw[t] * eq_pre - units * px[t]
            if dv > 0.0:                                   # sin apalancamiento
                dv = min(dv, cash / (1.0 + COST_R))
            cost = abs(dv) * COST_R
            units += dv / px[t]
            cash -= dv + cost
        eq = units * px[t] + cash
        out["weight_pre"][t] = w_pre
        out["weight_post"][t] = units * px[t] / eq
        out["trade_pct"][t] = dv / eq_pre
        out["trade_cost"][t] = cost
        out["units"][t] = units
        out["cash"][t] = cash
        out["equity"][t] = eq
        if t == 0:
            out["hodl_equity"][0] = 1.0 - COST_R
            out["cash_equity"][0] = 1.0
        else:
            out["hodl_equity"][t] = out["hodl_equity"][t - 1] * (1 + ret[t])
            out["cash_equity"][t] = out["cash_equity"][t - 1] * (1 + CASH_D)

    acc = pd.DataFrame(out, index=sig.index)
    acc["drawdown"] = acc["equity"] / acc["equity"].cummax() - 1
    return acc


def compute_track_record_v3(precios, paper_start, price_source="",
                            code_sha="", generated_at_utc="", live_from=None):
    live_from = pd.Timestamp(live_from or LIVE_FROM_V3)
    sig = compute_signal_v3(precios)
    sig = sig.iloc[max(LOOKBACKS):]
    sig = sig[sig.index >= pd.Timestamp(paper_start)]
    acc = run_accounting_v3(sig)
    df = pd.concat([sig, acc], axis=1)
    df["action"] = np.where(df["trade_pct"] > _EPS, "COMPRAR",
                     np.where(df["trade_pct"] < -_EPS, "VENDER", "MANTENER"))
    df["live"] = (df.index >= live_from).astype(float)
    df["price_source"] = price_source
    df["code_sha"] = code_sha
    df["generated_at_utc"] = generated_at_utc
    df.index.name = "date"
    return df


# ============================================================================
# SERIALIZACIÓN E INTEGRIDAD (misma lógica que engine_v21 v2.1.1)
# ============================================================================
def _safe(value, ndigits):
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return ""
    v = round(float(value), ndigits)
    return int(v) if ndigits == 0 else v


def df_to_rows_v3(tr):
    rows = []
    for date, r in tr.iterrows():
        row = [pd.Timestamp(date).strftime("%Y-%m-%d")]
        for col in COLUMNS_V3[1:]:
            row.append(_safe(r[col], _ROUND[col]) if col in _ROUND else str(r[col]))
        rows.append(row)
    return rows


def new_rows_v3(tr, existing_dates):
    existing = set(existing_dates)
    return [row for row in df_to_rows_v3(tr) if row[0] not in existing]


def _cell_equal(col, sheet_val, new_val):
    if col not in _ROUND:
        return str(sheet_val) == str(new_val)
    if sheet_val in ("", None) or new_val in ("", None):
        return str(sheet_val or "") == str(new_val or "")
    try:
        a, b = float(sheet_val), float(new_val)
    except (TypeError, ValueError):
        return False
    return abs(a - b) <= 0.5 * 10 ** -_ROUND[col]


def rows_mismatch_v3(recomputed, sheet_rows):
    by_date = {r[0]: r for r in sheet_rows}
    diffs = []
    for row in recomputed:
        ref = by_date.get(row[0])
        if ref is None:
            continue
        for i, col in enumerate(COLUMNS_V3):
            if col in PROVENANCE_COLS:
                continue
            sheet_val = ref[i] if i < len(ref) else ""
            if not _cell_equal(col, sheet_val, row[i]):
                diffs.append((row[0], col, str(sheet_val), str(row[i])))
    return diffs

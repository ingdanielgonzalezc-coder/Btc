"""
engine_v3.py — Motor V3 del paper trading BTC (challenger, corre en paralelo a v2.1)
================================================================================
Señal: ensemble de 4 canales Donchian (20/60/120/250 días) × vol-targeting 50%.
  - Cada canal ENTRA cuando el cierre supera el máximo de los N cierres previos
    y SALE cuando el cierre cae bajo el mínimo de los N/2 cierres previos
    (histéresis incorporada: entrar exige más que mantenerse).
  - donchian_score = promedio de los 4 estados (0, .25, .5, .75, 1).
  - target = score × min(1, 0.50 / vol_EWMA30)  — mismo vol-targeting que v2.1.

Contabilidad: la de v2.1 (units + cash, arranque desde cash, sin rebase) con UNA
diferencia de rebalanceo: se opera cuando |target − peso REAL| > BAND, y se va
al target completo. La banda mide la posición real (Gârleanu–Pedersen), no un
objetivo teórico; eso es lo que baja el turnover de ~14 a ~5 vueltas/año.

Comportamiento conocido (idéntico al backtest que justificó la versión):
  - con target < BAND desde una posición nula, no se compra;
  - una posición residual < BAND puede quedar abierta con target 0.
  En 2014–2026 ocurrió 46 de 4.661 días, siempre con peso < 10%.

Determinismo: igual que v2.1. Estado recomputado desde el día 0 en cada corrida.
Selección: pre-registrada (PREREG_v3_candidatos.md), ver ESPECIFICACION_v3.md.
"""

import numpy as np
import pandas as pd

# ===== Parámetros compartidos con v2.1 (comparación like-for-like) =====
TARGET_VOL = 0.50
EWMA_SPAN  = 30
CAP        = 1.0
BAND       = 0.10
FEE        = 0.0004
SLIP       = 0.0003
STABLE_APY = 0.04
ANN        = 365

# ===== Parámetros propios de V3 (congelados) =====
LOOKBACKS  = (20, 60, 120, 250)
EXIT_FRAC  = 0.5          # salida = mínimo de N·EXIT_FRAC cierres previos
EXIT_MIN   = 5

# ===== Despliegue — congelar al lanzar (debe ser POSTERIOR al push) =====
PAPER_START_V3 = "2026-10-12"
WARMUP_DAYS    = 420
SHEET_TAB_V3   = "track_record_v3"

COLUMNS_V3 = [
    "date", "btc_price", "price_source",
    "d20", "d60", "d120", "d250", "donchian_score", "vol_scalar", "target_weight",
    "next_buy_above", "next_sell_below",
    "weight_pre", "weight_post", "action", "trade_pct", "trade_cost",
    "units", "cash", "equity",
    "daily_return", "hodl_equity", "cash_equity", "drawdown",
    "code_sha", "generated_at_utc",
]
PROVENANCE_COLS = frozenset({"code_sha", "generated_at_utc"})

_ROUND = {
    "btc_price": 2, "d20": 0, "d60": 0, "d120": 0, "d250": 0,
    "donchian_score": 6, "vol_scalar": 6, "target_weight": 6,
    "next_buy_above": 2, "next_sell_below": 2,
    "weight_pre": 6, "weight_post": 6, "trade_pct": 6, "trade_cost": 10,
    "units": 10, "cash": 10, "equity": 10,
    "daily_return": 8, "hodl_equity": 8, "cash_equity": 8, "drawdown": 8,
}

CASH_D = (1 + STABLE_APY) ** (1 / ANN) - 1
COST_R = FEE + SLIP
_EPS_ACTION = 1e-9


def exit_window(n):
    return max(int(n * EXIT_FRAC), EXIT_MIN)


# ============================================================================
# SEÑAL
# ============================================================================
def donchian_states(precios):
    """Estado 0/1 por canal. Path-dependent: recorre la serie completa descargada.
    Sin lookahead: el día t solo compara contra cierres t-1 y anteriores."""
    px = precios.to_numpy(dtype=float)
    out = {}
    for n in LOOKBACKS:
        hi = precios.shift(1).rolling(n).max().to_numpy()
        lo = precios.shift(1).rolling(exit_window(n)).min().to_numpy()
        on, st = 0.0, np.zeros(len(px))
        for t in range(len(px)):
            if np.isnan(hi[t]):
                st[t] = 0.0
                continue
            if on == 0.0 and px[t] > hi[t]:
                on = 1.0
            elif on == 1.0 and px[t] < lo[t]:
                on = 0.0
            st[t] = on
        out[f"d{n}"] = st
    return pd.DataFrame(out, index=precios.index)


def next_levels(precios, states):
    """Umbrales para el CIERRE DE MAÑANA, conocidos hoy (para el dashboard):
       next_buy_above  = menor máximo-N entre canales apagados (NaN si todos encendidos)
       next_sell_below = mayor mínimo-N/2 entre canales encendidos (NaN si todos apagados)
    Un cierre mañana > next_buy_above enciende al menos un canal; < next_sell_below
    apaga al menos uno."""
    buy = pd.Series(np.inf, index=precios.index)
    sell = pd.Series(-np.inf, index=precios.index)
    for n in LOOKBACKS:
        hi_tomorrow = precios.rolling(n).max()                 # incluye el cierre de hoy
        lo_tomorrow = precios.rolling(exit_window(n)).min()
        off = states[f"d{n}"] == 0.0
        buy = buy.where(~off, np.minimum(buy, hi_tomorrow))
        sell = sell.where(off, np.maximum(sell, lo_tomorrow))
    return buy.replace(np.inf, np.nan), sell.replace(-np.inf, np.nan)


def compute_signal_v3(precios):
    if not precios.index.is_monotonic_increasing:
        raise ValueError("serie de precios desordenada")
    if precios.index.has_duplicates:
        raise ValueError("serie de precios con fechas duplicadas")

    ret = precios.pct_change()
    states = donchian_states(precios)
    score = states.mean(axis=1)
    vol = ret.ewm(span=EWMA_SPAN).std() * np.sqrt(ANN)
    vol_scalar = (TARGET_VOL / vol).clip(upper=CAP)
    target = (score * vol_scalar.fillna(0.0)).clip(0.0, CAP).fillna(0.0)
    buy, sell = next_levels(precios, states)

    sig = pd.DataFrame({
        "btc_price": precios, "daily_return": ret,
        **{c: states[c] for c in states.columns},
        "donchian_score": score, "vol_scalar": vol_scalar, "target_weight": target,
        "next_buy_above": buy, "next_sell_below": sell,
    })
    sig.index.name = "date"
    return sig


# ============================================================================
# CONTABILIDAD
# ============================================================================
def run_accounting_v3(sig):
    """Como v2.1 (§4 de su spec) salvo la regla de rebalanceo:
    operar cuando |target − peso real| > BAND, al target completo."""
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
        if abs(tw[t] - w_pre) > BAND:
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
                            code_sha="", generated_at_utc=""):
    sig = compute_signal_v3(precios)
    sig = sig.iloc[max(LOOKBACKS):]
    sig = sig[sig.index >= pd.Timestamp(paper_start)]
    acc = run_accounting_v3(sig)
    df = pd.concat([sig, acc], axis=1)
    df["action"] = np.where(df["trade_pct"] > _EPS_ACTION, "COMPRAR",
                     np.where(df["trade_pct"] < -_EPS_ACTION, "VENDER", "MANTENER"))
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

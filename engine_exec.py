"""
engine_exec.py — Registro de EJECUCIÓN ATRASADA para v2.1 y V3 (no reemplaza a ninguno)
================================================================================
Los registros oficiales operan al cierre de la vela (00:00 UTC), un precio que no
estaba disponible cuando se conoció la señal: el cron corre horas después. Este
registro aplica EXACTAMENTE las mismas señales, pero ejecuta cada operación al precio
de apertura de la vela HORARIA de Coinbase de las EXEC_HOUR_UTC del día siguiente.

  - Reproducible: las velas horarias se pueden volver a descargar, así que el registro
    se recomputa desde cero igual que v2.1 (determinismo, guarda de consistencia).
  - Sin estado nuevo de señal: v2.1 usa su signal_weight congelado y opera cuando
    cambia; V3 usa su target_weight y opera cuando cambia. Nada de esto toca los motores.

Orden de eventos por fila (fecha D):
  1. Cierre D (00:00 UTC del día D+1): se marca el capital con las tenencias que había
     ANTES de operar -> equity_close, weight_close.
  2. EXEC_HOUR_UTC del día D+1: si la señal cambió, se opera a exec_price -> trade_pct,
     trade_cost, units, cash; equity_post = capital justo después de operar.
Una fila D solo existe cuando su exec_price ya existe (la vela horaria ya abrió).

HODL comparable: compra en la ejecución del día 0, pagando el mismo costo, marcado al cierre.
"""

import numpy as np
import pandas as pd

import engine_v21 as e21
import engine_v3 as e3

EXEC_HOUR_UTC = 5            # mediana real del cron (meta_runs: ~5 h después del cierre)
FEE, SLIP = e21.FEE, e21.SLIP
COST_R = FEE + SLIP
CASH_D = e21.CASH_D
PAPER_START_EXEC = e21.PAPER_START_V21      # 2026-08-17, igual que v2.1 y V3
LIVE_FROM_EXEC = e3.LIVE_FROM_V3            # filas anteriores = reconstruidas
SHEET_TAB_EXEC = "track_record_exec"
VERSIONS = ("v21", "v3")

COLUMNS_EXEC = [
    "date", "version", "btc_close", "exec_time_utc", "exec_price",
    "target_weight", "weight_close", "trade_pct", "trade_cost",
    "units", "cash", "equity_close", "equity_post", "hodl_close", "drawdown",
    "live", "code_sha", "generated_at_utc",
]
PROVENANCE_COLS = frozenset({"code_sha", "generated_at_utc"})
_ROUND = {
    "btc_close": 2, "exec_price": 2, "target_weight": 6, "weight_close": 6,
    "trade_pct": 6, "trade_cost": 10, "units": 10, "cash": 10,
    "equity_close": 10, "equity_post": 10, "hodl_close": 8, "drawdown": 8, "live": 0,
}


# ============================================================================
# Precio de ejecución
# ============================================================================
def exec_prices_from_hourly(hourly_open, dates, hour=EXEC_HOUR_UTC):
    """hourly_open: Serie indexada por el INICIO de cada vela horaria (UTC naive).
    Devuelve, para cada fecha D, la apertura de la vela de las `hour` del día D+1
    (NaN si esa vela aún no existe)."""
    when = pd.DatetimeIndex(dates) + pd.Timedelta(days=1) + pd.Timedelta(hours=hour)
    return pd.Series(hourly_open.reindex(when).values, index=pd.DatetimeIndex(dates))


def targets(precios, version):
    """Objetivo diario de cada versión, calculado con SU motor congelado."""
    if version == "v21":
        sig = e21.compute_signal(precios)
        return sig["signal_weight"]
    if version == "v3":
        return e3.compute_signal_v3(precios)["target_weight"]
    raise ValueError(version)


# ============================================================================
# Contabilidad con ejecución atrasada
# ============================================================================
def run_exec_accounting(close, target, exec_px):
    """close, target, exec_px: Series alineadas por fecha (desde el día 0 del registro).
    Opera cuando el objetivo cambia (y el día 0), al exec_px de esa fila."""
    n = len(close)
    p = close.to_numpy(dtype=float)
    tw = target.to_numpy(dtype=float)
    ep = exec_px.to_numpy(dtype=float)
    if n and not np.all(np.isfinite(ep)):
        raise ValueError("falta precio de ejecución dentro del registro")
    cols = ["weight_close", "trade_pct", "trade_cost", "units", "cash",
            "equity_close", "equity_post", "hodl_close"]
    out = {c: np.zeros(n) for c in cols}
    units, cash = 0.0, 1.0
    h_units = 0.0
    for t in range(n):
        if t > 0:
            cash *= (1 + CASH_D)
        # 1) marca al cierre, antes de operar
        eq_c = units * p[t] + cash
        out["equity_close"][t] = eq_c
        out["weight_close"][t] = units * p[t] / eq_c
        out["hodl_close"][t] = h_units * p[t] if t > 0 else 1.0
        # 2) ejecución atrasada
        dv = cost = 0.0
        e_pre = units * ep[t] + cash
        if t == 0 or tw[t] != tw[t - 1]:
            dv = tw[t] * e_pre - units * ep[t]
            if dv > 0.0:
                dv = min(dv, cash / (1.0 + COST_R))
            cost = abs(dv) * COST_R
            units += dv / ep[t]
            cash -= dv + cost
        if t == 0:                                   # HODL: compra todo en la ejecución del día 0
            h_units = 1.0 / (ep[0] * (1.0 + COST_R))
        out["trade_pct"][t] = dv / e_pre
        out["trade_cost"][t] = cost
        out["units"][t] = units
        out["cash"][t] = cash
        out["equity_post"][t] = units * ep[t] + cash
    acc = pd.DataFrame(out, index=close.index)
    acc["drawdown"] = acc["equity_close"] / np.maximum.accumulate(
        np.maximum(acc["equity_close"].to_numpy(), 1.0)) - 1
    return acc


def compute_exec_record(precios, hourly_open, version, paper_start=PAPER_START_EXEC,
                        code_sha="", generated_at_utc="", live_from=LIVE_FROM_EXEC,
                        hour=EXEC_HOUR_UTC):
    tg = targets(precios, version)
    tg = tg.iloc[max(e21.LOOKBACKS):]
    tg = tg[tg.index >= pd.Timestamp(paper_start)]
    close = precios.reindex(tg.index)
    ex = exec_prices_from_hourly(hourly_open, tg.index, hour)
    # solo hasta la última fecha cuya ejecución ya ocurrió; un hueco intermedio es error
    avail = ex.notna().to_numpy()
    if avail.any():
        last = int(np.flatnonzero(avail)[-1])
        if not avail[: last + 1].all():
            missing = ex.index[: last + 1][~avail[: last + 1]]
            raise ValueError(f"faltan velas horarias de ejecución: {[d.strftime('%Y-%m-%d') for d in missing[:10]]}")
        n = last + 1
    else:
        n = 0
    tg, close, ex = tg.iloc[:n], close.iloc[:n], ex.iloc[:n]
    acc = run_exec_accounting(close, tg, ex)
    df = pd.DataFrame({
        "version": version, "btc_close": close, "exec_price": ex, "target_weight": tg,
        "exec_time_utc": [(d + pd.Timedelta(days=1, hours=hour)).strftime("%Y-%m-%d %H:%M") for d in tg.index],
    }, index=tg.index)
    df = pd.concat([df, acc], axis=1)
    df["live"] = (df.index >= pd.Timestamp(live_from)).astype(float)
    df["code_sha"] = code_sha
    df["generated_at_utc"] = generated_at_utc
    df.index.name = "date"
    return df


# ============================================================================
# Serialización e integridad (clave = fecha + versión)
# ============================================================================
def _safe(value, nd):
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return ""
    v = round(float(value), nd)
    return int(v) if nd == 0 else v


def df_to_rows_exec(df):
    rows = []
    for date, r in df.iterrows():
        row = [pd.Timestamp(date).strftime("%Y-%m-%d")]
        for col in COLUMNS_EXEC[1:]:
            row.append(_safe(r[col], _ROUND[col]) if col in _ROUND else str(r[col]))
        rows.append(row)
    return rows


def _key(row):
    return (str(row[0]), str(row[1]))


def new_rows_exec(df, existing_rows):
    have = {_key(r) for r in existing_rows}
    return [r for r in df_to_rows_exec(df) if _key(r) not in have]


def _cell_equal(col, a, b):
    if col not in _ROUND:
        return str(a) == str(b)
    if a in ("", None) or b in ("", None):
        return str(a or "") == str(b or "")
    try:
        return abs(float(a) - float(b)) <= 0.5 * 10 ** -_ROUND[col]
    except (TypeError, ValueError):
        return False


def rows_mismatch_exec(recomputed, sheet_rows):
    by_key = {_key(r): r for r in sheet_rows if len(r) >= 2}
    diffs = []
    for row in recomputed:
        ref = by_key.get(_key(row))
        if ref is None:
            continue
        for i, col in enumerate(COLUMNS_EXEC):
            if col in PROVENANCE_COLS:
                continue
            a = ref[i] if i < len(ref) else ""
            if not _cell_equal(col, a, row[i]):
                diffs.append((row[0], row[1], col, str(a), str(row[i])))
    return diffs

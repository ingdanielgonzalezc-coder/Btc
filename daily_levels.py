"""
daily_levels.py — Pestaña `next_levels` para el dashboard
================================================================================
Escribe, cada día, los precios de cierre que harían cambiar la señal MAÑANA en
v2.1 y en V3, más los supuestos del motor (APY del cash, costo por turnover).

No es un registro: se sobrescribe completa en cada corrida y nada la lee de vuelta.
No toca ningún motor; solo llama a sus funciones públicas. Corre con
continue-on-error: si falla, el dashboard muestra el último valor publicado.

Formato largo (section, key, value), fácil de extender sin romper el parser:
    meta | date        | 2026-10-05
    v21  | L250_state  | 0
    v21  | L250_ref    | 84513.2      # mañana el plazo vota arriba si cierra > ref
    v3   | L20_state   | 1
    v3   | L20_entry   | 86594.94     # canal apagado: se enciende si cierra > entry
    v3   | L20_exit    | 83456.74     # canal encendido: se apaga si cierra < exit
"""

import os

import pandas as pd

import daily_run_v21 as io21
import engine_v21 as e21
import engine_v3 as e3

LEVELS_TAB = "next_levels"
LEVELS_COLUMNS = ["section", "key", "value"]


def _fmt(x, nd=6):
    if x is None or (isinstance(x, float) and pd.isna(x)):
        return ""
    if isinstance(x, (bool,)):
        return int(x)
    if isinstance(x, (int,)):
        return x
    return round(float(x), nd)


def build_levels(precios, generated_at_utc="", code_sha=""):
    """Filas (section, key, value). `precios` debe empezar en o antes del inicio de
    descarga de v2.1 (PAPER_START_V21 − WARMUP) para reproducir su `held` exacto."""
    start21 = pd.Timestamp(e21.PAPER_START_V21) - pd.Timedelta(days=e21.WARMUP_DAYS)
    start3 = pd.Timestamp(e3.PAPER_START_V3) - pd.Timedelta(days=e3.WARMUP_DAYS)
    p21 = precios[precios.index >= start21]
    p3 = precios[precios.index >= start3]

    rows = []
    last = p21.index[-1]
    price = float(p21.iloc[-1])
    rows += [
        ("meta", "date", last.strftime("%Y-%m-%d")),
        ("meta", "price", _fmt(price, 2)),
        ("meta", "stable_apy", e21.STABLE_APY),
        ("meta", "cost_bps", round((e21.FEE + e21.SLIP) * 1e4, 4)),
        ("meta", "band", e21.BAND),
        ("meta", "generated_at_utc", generated_at_utc),
        ("meta", "code_sha", code_sha),
    ]

    # ---- v2.1: mañana compara P_{t+1} con P_{t+1-L} = p21[-L]
    s21 = e21.compute_signal(p21).iloc[-1]
    rows += [
        ("v21", "signal", _fmt(s21["signal_weight"])),
        ("v21", "trend", _fmt(s21["trend_score"])),
        ("v21", "vol_scalar", _fmt(s21["vol_scalar"])),
        ("v21", "target", _fmt(s21["target_weight"])),
    ]
    for L in e21.LOOKBACKS:
        rows += [
            ("v21", f"L{L}_state", int(p21.iloc[-1] > p21.iloc[-1 - L])),
            ("v21", f"L{L}_ref", _fmt(p21.iloc[-L], 2)),
        ]

    # ---- V3: estados path-dependent desde SU inicio de descarga
    sig3 = e3.compute_signal_v3(p3)
    s3 = sig3.iloc[-1]
    rows += [
        ("v3", "score", _fmt(s3["donchian_score"])),
        ("v3", "target", _fmt(s3["target_weight"])),
        ("v3", "vol_scalar", _fmt(s3["vol_scalar"])),
    ]
    tr3 = e3.compute_track_record_v3(p3, e3.PAPER_START_V3)
    rows.append(("v3", "weight", _fmt(tr3["weight_post"].iloc[-1]) if len(tr3) else ""))
    for L in e3.LOOKBACKS:
        on = int(s3[f"d{L}"] == 1.0)
        rows += [
            ("v3", f"L{L}_state", on),
            ("v3", f"L{L}_entry", _fmt(p3.iloc[-L:].max(), 2)),
            ("v3", f"L{L}_exit", _fmt(p3.iloc[-e3.exit_window(L):].min(), 2)),
        ]
    return [list(r) for r in rows]


def main():
    run_at = pd.Timestamp.now(tz="UTC").strftime("%Y-%m-%d %H:%M:%S")
    sha = os.environ.get("GITHUB_SHA", "")[:12]
    precios, _ = io21.fetch_prices()
    rows = build_levels(precios, run_at, sha)

    sh = io21._open_sheet()
    ws = io21._worksheet(sh, LEVELS_TAB, LEVELS_COLUMNS)
    ws.clear()
    ws.update(values=[LEVELS_COLUMNS] + rows, range_name="A1", value_input_option="RAW")
    print(f"OK | next_levels: {len(rows)} filas para el cierre posterior a {rows[0][2]}")


if __name__ == "__main__":
    main()

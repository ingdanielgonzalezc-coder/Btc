"""Tests del simulador de investigación (research/lib.py). Datos sintéticos, sin red.
Correr: cd research && python -m pytest -q test_lib_simulate.py"""
import os, sys
import numpy as np
import pandas as pd
import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.dirname(HERE))
import lib                      # noqa: E402
import engine_v21 as e21        # noqa: E402


def series(vals, start="2026-01-01"):
    return pd.Series(vals, index=pd.date_range(start, periods=len(vals), freq="D"), dtype=float)


def test_theoretical_matches_engine_v21():
    rng = np.random.default_rng(3)
    px = series(50000 * np.exp(np.cumsum(rng.normal(0.0005, 0.03, 700))), "2024-01-01")
    start = px.index[600]
    ref = e21.compute_track_record_v21(px, start)
    tgt, _, _ = lib.v21_target(px)
    res = lib.simulate(px, lib.band_held(tgt), cost=e21.COST_R, cash_apy=e21.STABLE_APY, start=start)
    np.testing.assert_allclose(res.equity.values, ref.equity.values, rtol=0, atol=1e-12)


def test_delayed_marks_before_trading_and_trades_at_exec_price():
    px = series([100, 100, 110, 110])
    ex = series([105, 100, 120, 110])          # precio de ejecución tras cada cierre
    tg = series([1, 1, 1, 1])
    r = lib.simulate(px, tg, cost=0.0, start=px.index[0], exec_px=ex)
    # día 0: se marca en cash (1,0) y luego se compra a 105 -> 1/105 unidades
    assert r.equity.iloc[0] == pytest.approx(1.0)
    assert r.equity.iloc[1] == pytest.approx(100 / 105)
    assert r.equity.iloc[2] == pytest.approx(110 / 105)


def test_delayed_last_row_does_not_trade():
    px = series([100, 100, 100])
    ex = series([100, 100, 100])
    tg = series([0, 0, 1])                     # la señal de comprar llega en el último cierre
    r = lib.simulate(px, tg, cost=0.001, start=px.index[0], exec_px=ex)
    assert r.turnover.iloc[-1] == 0 and r.cost.iloc[-1] == 0
    assert r.equity.iloc[-1] == pytest.approx(1.0)


def test_delayed_missing_exec_price_raises_only_when_trading():
    px = series([100, 101, 102, 103])
    ex = series([100, np.nan, 102, 103])
    with pytest.raises(ValueError, match="falta precio de ejecución"):
        lib.simulate(px, series([0, 1, 1, 1]), start=px.index[0], exec_px=ex)
    lib.simulate(px, series([1, 1, 1, 1]), start=px.index[0], exec_px=ex)   # sin operar ese día: OK

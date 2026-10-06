"""
test_engine_v3.py — Suite de V3 todo/nada. Falla => el paso V3 del workflow no escribe.

test_matches_reference_backtest ata el motor de producción a la implementación con
la que se evaluó la regla (research/run_todo_nada.py). Si diverge, el backtest no aplica.
"""

import numpy as np
import pandas as pd
import pytest

import daily_run_v3 as io3
import engine_v21 as e21
import engine_v3 as e3


def make_prices(n=900, seed=7, start="2024-01-01", drift=0.0006, vol=0.03):
    rng = np.random.default_rng(seed)
    px = 50000 * np.exp(np.cumsum(rng.normal(drift, vol, n)))
    return pd.Series(px, index=pd.date_range(start, periods=n, freq="D"))


# --------------------------------------------------------------------------
# Referencia: la implementación vectorizada del backtest (copia literal)
# --------------------------------------------------------------------------
def ref_equity(px, start, cost):
    tr = pd.concat([(px > px.shift(L)).astype(float) for L in (20, 60, 120, 250)], axis=1).mean(axis=1)
    w = (tr >= 0.75 - 1e-12).astype(float).loc[start:]
    r = px.pct_change().loc[start:]
    wp = w.shift(1).fillna(0)
    turn = w.diff().abs().fillna(w.iloc[0])
    return (1 + wp * r.fillna(0) - turn * cost).cumprod()


@pytest.mark.parametrize("seed", [1, 7, 42])
def test_matches_reference_backtest(seed):
    """Sin cash ni límite de financiamiento, el motor debe dar la curva del backtest."""
    px = make_prices(seed=seed)
    start = px.index[600]
    old = (e3.CASH_D, e3.COST_R)
    try:
        e3.CASH_D = 0.0
        tr = e3.compute_track_record_v3(px, start)
    finally:
        e3.CASH_D, e3.COST_R = old
    ref = ref_equity(px, start, e3.COST_R)
    # Diferencias de segundo orden y conocidas: el motor cobra el costo sobre el capital
    # ya marcado al cierre (no el de ayer) y paga la compra con el propio cash
    # (sin apalancamiento). Por operación son ~costo×retorno del día; se acotan.
    np.testing.assert_allclose(tr["equity"].values, ref.values, rtol=1e-3)
    tr_ref = pd.concat([(px > px.shift(L)).astype(float) for L in (20, 60, 120, 250)], axis=1).mean(axis=1)
    np.testing.assert_array_equal(tr["target_weight"].values,
                                  (tr_ref.loc[start:] >= 0.75 - 1e-12).astype(float).values)


def test_votes_equal_v21_trend():
    """V3 usa exactamente el trend_score de v2.1; solo cambia el mapeo a peso."""
    px = make_prices()
    a = e3.compute_signal_v3(px)["trend_score"]
    b = e21.compute_signal(px)["trend_score"]
    pd.testing.assert_series_equal(a, b, check_names=False)
    assert e3.LOOKBACKS == e21.LOOKBACKS


def test_target_is_all_or_nothing():
    sig = e3.compute_signal_v3(make_prices())
    assert set(sig["target_weight"].unique()) <= {0.0, 1.0}
    on = sig["votes_up"] >= e3.MIN_VOTES
    assert (sig.loc[on, "target_weight"] == 1.0).all()
    assert (sig.loc[~on, "target_weight"] == 0.0).all()


def test_shared_params_match_v21():
    for p in ["FEE", "SLIP", "STABLE_APY", "ANN", "LOOKBACKS"]:
        assert getattr(e3, p) == getattr(e21, p), p
    assert e3.PAPER_START_V3 == e21.PAPER_START_V21


def test_no_lookahead_prefix():
    px = make_prices(seed=3)
    full = e3.compute_signal_v3(px)
    short = e3.compute_signal_v3(px.iloc[:700])
    pd.testing.assert_frame_equal(full.iloc[:700], short)


def test_unsorted_and_duplicates_raise():
    px = make_prices(n=300)
    with pytest.raises(ValueError, match="desordenada"):
        e3.compute_signal_v3(px.iloc[::-1])
    with pytest.raises(ValueError, match="duplicadas"):
        e3.compute_signal_v3(pd.concat([px, px.iloc[[5]]]).sort_index())


# --------------------------------------------------------------------------
# Contabilidad
# --------------------------------------------------------------------------
def _sig(targets, prices):
    idx = pd.date_range("2026-01-01", periods=len(targets), freq="D")
    px = pd.Series(prices, index=idx, dtype=float)
    return pd.DataFrame({"btc_price": px, "daily_return": px.pct_change(),
                         "target_weight": pd.Series(targets, index=idx, dtype=float)})


def test_full_entry_without_leverage():
    acc = e3.run_accounting_v3(_sig([1, 1], [60000, 61000]))
    assert acc["cash"].iloc[0] == pytest.approx(0.0, abs=1e-15)
    assert acc["weight_post"].iloc[0] == pytest.approx(1.0, rel=1e-12)
    assert acc["equity"].iloc[0] == pytest.approx(1 - e3.COST_R / (1 + e3.COST_R), rel=1e-12)


def test_full_exit_and_no_trade_without_change():
    acc = e3.run_accounting_v3(_sig([1, 1, 1, 0, 0], [100, 110, 95, 105, 120]))
    assert (acc["trade_pct"].iloc[1:3].abs() < 1e-15).all()       # sin cambio, sin trade
    assert acc["units"].iloc[3] == pytest.approx(0.0, abs=1e-15)    # salida completa
    assert acc["weight_post"].iloc[4] == 0.0


def test_return_lands_next_day():
    acc = e3.run_accounting_v3(_sig([0, 1, 1], [100, 100, 110]))
    assert acc["equity"].iloc[2] / acc["equity"].iloc[1] == pytest.approx(1.10, rel=1e-6)


def test_equity_identity():
    px = make_prices(seed=5, vol=0.06)
    tr = e3.compute_track_record_v3(px, px.index[600])
    np.testing.assert_allclose((tr["units"] * tr["btc_price"] + tr["cash"]).values,
                               tr["equity"].values, rtol=0, atol=1e-12)
    assert (tr["cash"] >= -1e-15).all() and (tr["units"] >= -1e-15).all()


def test_determinism_and_prefix():
    px = make_prices(seed=21)
    a = e3.compute_track_record_v3(px, px.index[600])
    b = e3.compute_track_record_v3(px.iloc[:-10], px.index[600])
    pd.testing.assert_frame_equal(a.iloc[:len(b)], b)


def test_live_flag_marks_reconstructed_rows():
    px = make_prices(seed=4)
    start, live = px.index[600], px.index[650]
    tr = e3.compute_track_record_v3(px, start, live_from=live)
    assert (tr.loc[tr.index < live, "live"] == 0).all()
    assert (tr.loc[tr.index >= live, "live"] == 1).all()


def test_empty_window():
    px = make_prices(n=400)
    tr = e3.compute_track_record_v3(px, px.index[-1] + pd.Timedelta(days=3))
    assert len(tr) == 0 and e3.df_to_rows_v3(tr) == []


# --------------------------------------------------------------------------
# Serialización e integridad
# --------------------------------------------------------------------------
def _tr(sha="a", ts="2026-10-07 00:31:00", drop=0):
    px = make_prices(seed=9)
    if drop:
        px = px.iloc[:-drop]
    return e3.compute_track_record_v3(px, "2025-09-01", "coinbase", sha, ts, live_from="2026-01-01")


def test_rows_shape_and_idempotent():
    tr = _tr()
    rows = e3.df_to_rows_v3(tr)
    assert all(len(r) == len(e3.COLUMNS_V3) for r in rows)
    assert e3.new_rows_v3(tr, [r[0] for r in rows]) == []
    assert len(e3.new_rows_v3(tr, [r[0] for r in rows[:-2]])) == 2


def test_consistency_ignores_provenance_detects_change():
    sheet = e3.df_to_rows_v3(_tr("aaa", "2026-10-07 00:31:00", drop=1))
    today = _tr("bbb", "2026-10-08 00:31:00")
    ok, diffs, _ = io3.verify_consistency_v3(today, sheet)
    assert ok, diffs
    forked = [list(r) for r in sheet]
    i = e3.COLUMNS_V3.index("equity")
    forked[-1][i] = float(forked[-1][i]) + 1e-10
    ok, diffs, _ = io3.verify_consistency_v3(today, forked)
    assert not ok and diffs[0][1] == "equity"


def test_integer_cells_roundtrip():
    tr = _tr()
    sheet = [[int(v) if isinstance(v, float) and v.is_integer() else v for v in r]
             for r in e3.df_to_rows_v3(tr)]
    ok, diffs, _ = io3.verify_consistency_v3(tr, sheet)
    assert ok, diffs

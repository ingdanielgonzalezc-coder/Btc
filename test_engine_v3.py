"""
test_engine_v3.py — Suite de V3. Falla => el paso V3 del workflow no escribe.

El test central es test_matches_reference_backtest: el motor de producción debe
reproducir exactamente la implementación de investigación con la que se eligió V3
(PREREG_v3_candidatos.md). Si diverge, la evidencia del backtest no aplica.
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
# Implementación de referencia (copia literal de la usada en el backtest)
# --------------------------------------------------------------------------
def ref_donchian(px, lookbacks=(20, 60, 120, 250)):
    states = []
    for L in lookbacks:
        hi = px.shift(1).rolling(L).max(); lo = px.shift(1).rolling(max(L // 2, 5)).min()
        on, out = 0.0, []
        for p, h, l in zip(px.values, hi.values, lo.values):
            if np.isnan(h):
                out.append(0.0); continue
            if on == 0.0 and p > h: on = 1.0
            elif on == 1.0 and p < l: on = 0.0
            out.append(on)
        states.append(pd.Series(out, index=px.index))
    return pd.concat(states, axis=1).mean(axis=1)


def ref_simulate_band(px, target, cost, cash_d, band):
    p = px.values; tw = target.values; n = len(p)
    units, cash = 0.0, 1.0; eq = np.empty(n)
    for t in range(n):
        if t > 0: cash *= (1 + cash_d)
        e_pre = units * p[t] + cash; w_pre = units * p[t] / e_pre
        if abs(tw[t] - w_pre) > band:
            dv = tw[t] * e_pre - units * p[t]
            if dv > 0: dv = min(dv, cash / (1 + cost))
            units += dv / p[t]; cash -= dv + abs(dv) * cost
        eq[t] = units * p[t] + cash
    return pd.Series(eq, index=px.index)


@pytest.mark.parametrize("seed", [1, 7, 42])
def test_matches_reference_backtest(seed):
    px = make_prices(seed=seed)
    start = px.index[600]
    tr = e3.compute_track_record_v3(px, start)
    # señal
    np.testing.assert_array_equal(
        ref_donchian(px).loc[tr.index].values, tr["donchian_score"].values)
    # contabilidad
    eq = ref_simulate_band(px.loc[start:], tr["target_weight"], e3.COST_R, e3.CASH_D, e3.BAND)
    np.testing.assert_allclose(eq.values, tr["equity"].values, rtol=0, atol=1e-12)


def test_shared_params_match_v21():
    for p in ["TARGET_VOL", "EWMA_SPAN", "CAP", "BAND", "FEE", "SLIP", "STABLE_APY", "ANN"]:
        assert getattr(e3, p) == getattr(e21, p), p


def test_vol_scalar_identical_to_v21():
    px = make_prices()
    a = e3.compute_signal_v3(px)["vol_scalar"]
    b = e21.compute_signal(px)["vol_scalar"]
    pd.testing.assert_series_equal(a, b, check_names=False)


# --------------------------------------------------------------------------
# Señal
# --------------------------------------------------------------------------
def test_no_lookahead_prefix():
    """La señal del día t no puede depender de precios posteriores a t."""
    px = make_prices(seed=3)
    full = e3.compute_signal_v3(px)
    short = e3.compute_signal_v3(px.iloc[:700])
    cols = ["d20", "d60", "d120", "d250", "donchian_score", "target_weight"]
    pd.testing.assert_frame_equal(full[cols].iloc[:700], short[cols])


def test_hysteresis_enter_high_exit_low():
    idx = pd.date_range("2025-01-01", periods=60, freq="D")
    p = np.full(60, 100.0)
    p[25] = 101.0          # rompe el máximo de 20 -> entra
    p[26:35] = 99.5        # cae bajo el mínimo de los 10 cierres previos (100)
    px = pd.Series(p, index=idx)
    st = e3.donchian_states(px)["d20"]
    assert st.iloc[24] == 0.0 and st.iloc[25] == 1.0
    # 99.5 < mínimo de los 10 previos (100) -> sale al día siguiente del quiebre
    assert st.iloc[26] == 0.0


def test_hysteresis_holds_inside_channel():
    idx = pd.date_range("2025-01-01", periods=60, freq="D")
    p = np.full(60, 100.0)
    p[25:] = 110.0         # entra el 25 y se queda plano: no rompe el mínimo
    px = pd.Series(p, index=idx)
    st = e3.donchian_states(px)["d20"]
    assert (st.iloc[25:] == 1.0).all()


def test_next_levels_are_actionable():
    """Un cierre mañana sobre next_buy_above enciende >= 1 canal; bajo next_sell_below apaga >= 1."""
    px = make_prices(seed=11, n=700)
    sig = e3.compute_signal_v3(px)
    t = 650
    today = sig.iloc[t]
    nxt = px.index[t] + pd.Timedelta(days=1)
    base = px.iloc[: t + 1]
    if not np.isnan(today["next_buy_above"]):
        up = pd.concat([base, pd.Series([today["next_buy_above"] * 1.0001], index=[nxt])])
        assert e3.compute_signal_v3(up)["donchian_score"].iloc[-1] > today["donchian_score"]
    if not np.isnan(today["next_sell_below"]):
        dn = pd.concat([base, pd.Series([today["next_sell_below"] * 0.9999], index=[nxt])])
        assert e3.compute_signal_v3(dn)["donchian_score"].iloc[-1] < today["donchian_score"]


def test_unsorted_and_duplicates_raise():
    px = make_prices(n=300)
    with pytest.raises(ValueError, match="desordenada"):
        e3.compute_signal_v3(px.iloc[::-1])
    with pytest.raises(ValueError, match="duplicadas"):
        e3.compute_signal_v3(pd.concat([px, px.iloc[[5]]]).sort_index())


# --------------------------------------------------------------------------
# Contabilidad
# --------------------------------------------------------------------------
def _sig(weights, prices):
    idx = pd.date_range("2026-01-01", periods=len(weights), freq="D")
    px = pd.Series(prices, index=idx, dtype=float)
    return pd.DataFrame({"btc_price": px, "daily_return": px.pct_change(),
                         "target_weight": pd.Series(weights, index=idx, dtype=float)})


def test_starts_from_cash_and_pays_entry():
    acc = e3.run_accounting_v3(_sig([0.5, 0.5], [60000, 61000]))
    assert acc["weight_pre"].iloc[0] == 0.0
    assert acc["equity"].iloc[0] == pytest.approx(1 - 0.5 * e3.COST_R, rel=1e-12)


def test_band_on_actual_weight():
    # target 0.5 constante; el precio sube y el peso real deriva sobre 0.6 -> rebalancea
    acc = e3.run_accounting_v3(_sig([0.5] * 4, [100, 110, 125, 150]))
    w = acc["weight_pre"].values
    trades = acc["trade_pct"].abs().values > 1e-12
    for t in range(1, 4):
        assert trades[t] == (abs(0.5 - w[t]) > e3.BAND)
    assert trades[1:].any(), "fixture inválida: nunca cruzó la banda"


def test_no_trade_inside_band():
    acc = e3.run_accounting_v3(_sig([0.5, 0.55, 0.45, 0.58], [100, 100, 100, 100]))
    assert (acc["trade_pct"].iloc[1:].abs() < 1e-15).all()


def test_equity_identity_and_no_leverage():
    px = make_prices(seed=5, vol=0.06)
    tr = e3.compute_track_record_v3(px, px.index[600])
    np.testing.assert_allclose((tr["units"] * tr["btc_price"] + tr["cash"]).values,
                               tr["equity"].values, rtol=0, atol=1e-12)
    assert (tr["cash"] >= -1e-15).all() and (tr["units"] >= -1e-15).all()
    assert (tr["weight_post"] <= e3.CAP + 1e-12).all()


def test_determinism_and_prefix():
    px = make_prices(seed=21)
    a = e3.compute_track_record_v3(px, px.index[600])
    b = e3.compute_track_record_v3(px.iloc[:-10], px.index[600])
    pd.testing.assert_frame_equal(a.iloc[:len(b)], b)


def test_empty_window():
    px = make_prices(n=400)
    tr = e3.compute_track_record_v3(px, px.index[-1] + pd.Timedelta(days=3))
    assert len(tr) == 0 and e3.df_to_rows_v3(tr) == []


# --------------------------------------------------------------------------
# Serialización e integridad
# --------------------------------------------------------------------------
def _tr(sha="a", ts="2026-10-12 00:31:00", drop=0):
    px = make_prices(seed=9)
    if drop:
        px = px.iloc[:-drop]
    return e3.compute_track_record_v3(px, "2025-09-01", "coinbase", sha, ts)


def test_rows_shape_and_idempotent():
    tr = _tr()
    rows = e3.df_to_rows_v3(tr)
    assert all(len(r) == len(e3.COLUMNS_V3) for r in rows)
    assert e3.new_rows_v3(tr, [r[0] for r in rows]) == []
    assert len(e3.new_rows_v3(tr, [r[0] for r in rows[:-2]])) == 2


def test_consistency_ignores_provenance_detects_change():
    sheet = e3.df_to_rows_v3(_tr("aaa", "2026-10-12 00:31:00", drop=1))
    today = _tr("bbb", "2026-10-13 00:31:00")
    ok, diffs, n = io3.verify_consistency_v3(today, sheet)
    assert ok, diffs
    forked = [list(r) for r in sheet]
    forked[-1][e3.COLUMNS_V3.index("equity")] = float(forked[-1][e3.COLUMNS_V3.index("equity")]) + 1e-10
    ok, diffs, _ = io3.verify_consistency_v3(today, forked)
    assert not ok and diffs[0][1] == "equity"


def test_integer_and_empty_cells_roundtrip():
    """d20..d250 se escriben como enteros; next_* pueden quedar vacíos."""
    tr = _tr()
    sheet = []
    for r in e3.df_to_rows_v3(tr):
        sheet.append([int(v) if isinstance(v, float) and v.is_integer() else v for v in r])
    ok, diffs, _ = io3.verify_consistency_v3(tr, sheet)
    assert ok, diffs

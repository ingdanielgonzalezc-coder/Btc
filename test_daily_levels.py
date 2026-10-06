"""Tests de daily_levels: los umbrales publicados deben predecir la señal de mañana."""

import numpy as np
import pandas as pd

import daily_levels as dl
import engine_v21 as e21
import engine_v3 as e3


def make_prices(seed=4, end="2026-10-05", n=520):
    rng = np.random.default_rng(seed)
    idx = pd.date_range(end=end, periods=n, freq="D")
    return pd.Series(60000 * np.exp(np.cumsum(rng.normal(0.0008, 0.03, n))), index=idx)


def as_dict(rows):
    return {(s, k): v for s, k, v in rows}


def tomorrow(px, price):
    nxt = px.index[-1] + pd.Timedelta(days=1)
    return pd.concat([px, pd.Series([price], index=[nxt])])


def test_v21_refs_predict_tomorrow_votes():
    px = make_prices()
    d = as_dict(dl.build_levels(px))
    start = pd.Timestamp(e21.PAPER_START_V21) - pd.Timedelta(days=e21.WARMUP_DAYS)
    p21 = px[px.index >= start]
    for L in e21.LOOKBACKS:
        ref = d[("v21", f"L{L}_ref")]
        for mult, expected in [(1.0001, True), (0.9999, False)]:
            nxt = tomorrow(p21, ref * mult)
            assert (nxt.iloc[-1] > nxt.iloc[-1 - L]) == expected


def test_v21_signal_matches_engine():
    px = make_prices(seed=8)
    d = as_dict(dl.build_levels(px))
    start = pd.Timestamp(e21.PAPER_START_V21) - pd.Timedelta(days=e21.WARMUP_DAYS)
    sig = e21.compute_signal(px[px.index >= start]).iloc[-1]
    assert d[("v21", "signal")] == round(float(sig["signal_weight"]), 6)


def test_v3_refs_predict_tomorrow_target():
    """Con los refs publicados, el objetivo de V3 de mañana se puede anticipar."""
    px = make_prices(seed=12)
    d = as_dict(dl.build_levels(px))
    start = pd.Timestamp(e3.PAPER_START_V3) - pd.Timedelta(days=e3.WARMUP_DAYS)
    p3 = px[px.index >= start]
    refs = [d[("v3", f"L{L}_ref")] for L in e3.LOOKBACKS]
    for price in sorted(refs) + [max(refs) * 1.05, min(refs) * 0.95]:
        for p in (price * 1.0001, price * 0.9999):
            expected = float(sum(p > r for r in refs) >= e3.MIN_VOTES)
            got = e3.compute_signal_v3(tomorrow(p3, p))["target_weight"].iloc[-1]
            assert got == expected


def test_meta_and_shape():
    rows = dl.build_levels(make_prices(), "2026-10-06 00:31:00", "abc")
    d = as_dict(rows)
    assert all(len(r) == 3 for r in rows)
    assert d[("meta", "cost_bps")] == 7.0
    assert d[("meta", "stable_apy")] == e21.STABLE_APY
    assert d[("meta", "date")] == "2026-10-05"

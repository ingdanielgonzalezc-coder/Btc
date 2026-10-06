"""Tests del registro de ejecución atrasada. Sin red: velas horarias sintéticas."""
import os, sys
import numpy as np
import pandas as pd
import pytest

import daily_run_exec as io_ex
import engine_exec as ex
import engine_v21 as e21

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "research"))
import lib  # noqa: E402  (simulador de investigación: referencia independiente)


def make_data(n=700, seed=5):
    rng = np.random.default_rng(seed)
    days = pd.date_range("2024-11-01", periods=n, freq="D")
    daily = pd.Series(60000 * np.exp(np.cumsum(rng.normal(0.0008, 0.03, n))), index=days)
    hours = pd.date_range(days[0], days[-1] + pd.Timedelta(days=1, hours=23), freq="h")
    # apertura horaria = cierre diario anterior × ruido intradía
    base = daily.reindex(hours.normalize() - pd.Timedelta(days=1)).to_numpy()
    hourly = pd.Series(base * np.exp(rng.normal(0, 0.004, len(hours))), index=hours)
    return daily, hourly


def test_exec_price_is_next_day_hour():
    daily, hourly = make_data(n=300)
    d = daily.index[100:103]
    got = ex.exec_prices_from_hourly(hourly, d)
    for day in d:
        assert got[day] == hourly[day + pd.Timedelta(days=1, hours=ex.EXEC_HOUR_UTC)]


@pytest.mark.parametrize("version", ["v21", "v3"])
def test_matches_research_simulator(version, monkeypatch):
    """La contabilidad atrasada coincide con lib.simulate (implementación independiente)."""
    daily, hourly = make_data()
    start = daily.index[400]
    monkeypatch.setattr(ex, "CASH_D", 0.0)
    rec = ex.compute_exec_record(daily, hourly, version, paper_start=start)
    tg = ex.targets(daily, version)
    exec_px = ex.exec_prices_from_hourly(hourly, daily.index)
    ref = lib.simulate(daily, tg, cost=ex.COST_R, cash_apy=0.0, start=start,
                       end=rec.index[-1], exec_px=exec_px)
    np.testing.assert_allclose(rec["equity_close"].values, ref.equity.values, rtol=0, atol=1e-12)


def test_v21_uses_frozen_signal():
    daily, _ = make_data()
    pd.testing.assert_series_equal(ex.targets(daily, "v21"), e21.compute_signal(daily)["signal_weight"],
                                   check_names=False)


def test_rows_stop_at_last_available_execution_and_gaps_raise():
    daily, hourly = make_data()
    start = daily.index[400]
    cut = hourly[hourly.index < daily.index[-3] + pd.Timedelta(days=1, hours=ex.EXEC_HOUR_UTC)]
    rec = ex.compute_exec_record(daily, cut, "v3", paper_start=start)
    assert rec.index[-1] == daily.index[-4]
    holed = hourly.drop(daily.index[450] + pd.Timedelta(days=1, hours=ex.EXEC_HOUR_UTC))
    with pytest.raises(ValueError, match="faltan velas horarias"):
        ex.compute_exec_record(daily, holed, "v3", paper_start=start)


def test_marks_before_trading_and_hodl_pays_entry():
    daily, hourly = make_data()
    start = daily.index[400]
    rec = ex.compute_exec_record(daily, hourly, "v3", paper_start=start)
    assert rec["equity_close"].iloc[0] == pytest.approx(1.0)        # día 0: aún en cash
    assert rec["hodl_close"].iloc[0] == pytest.approx(1.0)
    h1 = daily.iloc[401] / (rec["exec_price"].iloc[0] * (1 + ex.COST_R))
    assert rec["hodl_close"].iloc[1] == pytest.approx(h1)
    np.testing.assert_allclose((rec["units"] * rec["exec_price"] + rec["cash"]).values,
                               rec["equity_post"].values, rtol=0, atol=1e-12)


def test_idempotent_and_consistency():
    daily, hourly = make_data()
    start = daily.index[400]
    df = pd.concat([ex.compute_exec_record(daily, hourly, v, paper_start=start, generated_at_utc="a") for v in ex.VERSIONS])
    rows = ex.df_to_rows_exec(df)
    assert ex.new_rows_exec(df, rows) == []
    ok, diffs, n = io_ex.verify_consistency_exec(df, rows)
    assert ok and n > 0
    df2 = pd.concat([ex.compute_exec_record(daily, hourly, v, paper_start=start, generated_at_utc="b") for v in ex.VERSIONS])
    assert io_ex.verify_consistency_exec(df2, rows)[0]                 # procedencia no cuenta
    bad = [list(r) for r in rows]; bad[-1][ex.COLUMNS_EXEC.index("equity_close")] += 1e-9
    assert not io_ex.verify_consistency_exec(df, bad)[0]

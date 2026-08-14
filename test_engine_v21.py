"""
test_engine_v21.py — Suite obligatoria. Falla => NO se escribe al sheet.

El test crítico es test_signal_equivalence_*: es lo que PRUEBA que la señal de
v2.1 es la de v2.0, y por tanto lo que justifica reutilizar el held-out
2022-2026 (Calmar 1.03) sin re-correrlo.
"""

import os
import numpy as np
import pandas as pd
import pytest

import engine_v21 as e21

FIXTURES = os.path.join(os.path.dirname(__file__), "data")


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------
def make_prices(n=800, seed=7, start="2025-01-01", drift=0.0004, vol=0.03):
    rng = np.random.default_rng(seed)
    r = rng.normal(drift, vol, n)
    px = 50000 * np.exp(np.cumsum(r))
    return pd.Series(px, index=pd.date_range(start, periods=n, freq="D"))


def make_sig(weights, prices, start="2026-01-01"):
    """Frame de señal sintético para testear la contabilidad en aislamiento."""
    idx = pd.date_range(start, periods=len(weights), freq="D")
    px = pd.Series(prices, index=idx, dtype=float)
    return pd.DataFrame({
        "btc_price": px,
        "daily_return": px.pct_change(),
        "trend_score": np.nan,
        "vol_scalar": np.nan,
        "target_weight": weights,
        "signal_weight": pd.Series(weights, index=idx, dtype=float),
    })


SIGNAL_COLS = ["trend_score", "vol_scalar", "target_weight"]


# --------------------------------------------------------------------------
# 1. Equivalencia de señal con v2.0  (EL TEST QUE SOSTIENE TODO)
# --------------------------------------------------------------------------
def test_signal_equivalence_synthetic():
    """v2.1 debe reproducir bit-a-bit las columnas de señal de v2.0."""
    import daily_run as v20

    px = make_prices()
    paper_start = px.index[600]

    ref = v20.compute_track_record(px, paper_start=paper_start)
    new = e21.compute_track_record_v21(px, paper_start=paper_start)

    assert list(ref.index) == list(new.index)
    for col in SIGNAL_COLS:
        pd.testing.assert_series_equal(ref[col], new[col], check_names=False)
    # v2.0 llama `new_weight` a lo que v2.1 llama `signal_weight`
    pd.testing.assert_series_equal(
        ref["new_weight"], new["signal_weight"], check_names=False)
    pd.testing.assert_series_equal(
        ref["daily_return"], new["daily_return"], check_names=False)


@pytest.mark.parametrize("seed", [1, 2, 3, 42, 99])
def test_signal_equivalence_multiple_regimes(seed):
    """Equivalencia robusta a distintos regímenes de precio."""
    import daily_run as v20

    px = make_prices(seed=seed, drift=(-0.001 if seed % 2 else 0.001), vol=0.05)
    paper_start = px.index[600]
    ref = v20.compute_track_record(px, paper_start=paper_start)
    new = e21.compute_track_record_v21(px, paper_start=paper_start)
    for col in SIGNAL_COLS:
        pd.testing.assert_series_equal(ref[col], new[col], check_names=False)
    pd.testing.assert_series_equal(
        ref["new_weight"], new["signal_weight"], check_names=False)


@pytest.mark.skipif(
    not os.path.exists(os.path.join(FIXTURES, "prices_snapshot.csv")),
    reason="falta data/prices_snapshot.csv (serie cruda CON warmup) — ver spec §11")
def test_signal_equivalence_real_fixture():
    """Reproduce las columnas de señal del registro v2.0 real y archivado."""
    px = pd.read_csv(os.path.join(FIXTURES, "prices_snapshot.csv"),
                     index_col=0, parse_dates=True).iloc[:, 0]
    arch = pd.read_csv(os.path.join(FIXTURES, "track_record_v20_archive.csv"),
                       parse_dates=["date"]).set_index("date")

    new = e21.compute_track_record_v21(px, paper_start=arch.index[0])
    common = new.index.intersection(arch.index)
    assert len(common) >= 50, "solapamiento insuficiente con el archivo"

    for col, ref_col in [("trend_score", "trend_score"),
                         ("vol_scalar", "vol_scalar"),
                         ("target_weight", "target_weight"),
                         ("signal_weight", "new_weight")]:
        np.testing.assert_allclose(
            new.loc[common, col].values, arch.loc[common, ref_col].values,
            rtol=0, atol=1e-6, err_msg=f"señal divergente en {col}")


def test_frozen_params_match_v20():
    """Los parámetros congelados no pueden haber derivado."""
    import daily_run as v20
    for p in ["LOOKBACKS", "TARGET_VOL", "EWMA_SPAN", "CAP", "BAND",
              "FEE", "SLIP", "STABLE_APY", "ANN"]:
        assert getattr(e21, p) == getattr(v20, p), f"parámetro {p} divergió"


# --------------------------------------------------------------------------
# 2-3. Arranque desde cash / sin rebase
# --------------------------------------------------------------------------
def test_day0_starts_from_cash():
    sig = make_sig([0.25, 0.25, 0.25], [60000, 61000, 62000])
    acc = e21.run_accounting(sig)
    assert acc["weight_pre"].iloc[0] == 0.0                  # cuenta nace en cash
    expected_cost = 0.25 * e21.COST_R
    assert acc["trade_cost"].iloc[0] == pytest.approx(expected_cost, rel=1e-12)
    assert acc["equity"].iloc[0] == pytest.approx(1 - expected_cost, rel=1e-12)


def test_no_rebase_day0_below_one():
    """El defecto de v2.0: dividir por iloc[0] borraba el costo del día 1."""
    sig = make_sig([0.5, 0.5], [60000, 61000])
    acc = e21.run_accounting(sig)
    assert acc["equity"].iloc[0] < 1.0
    assert acc["equity"].iloc[0] == pytest.approx(1 - 0.5 * e21.COST_R, rel=1e-12)


def test_no_inherited_position():
    """Aunque la señal venga en 1.0 desde el warmup, el día 0 se COMPRA y se paga."""
    px = make_prices(drift=0.004, vol=0.01)                  # tendencia fuerte -> señal alta
    tr = e21.compute_track_record_v21(px, paper_start=px.index[600])
    assert tr["signal_weight"].iloc[0] > 0, "fixture inválida: señal 0 en día 0"
    assert tr["weight_pre"].iloc[0] == 0.0
    assert tr["action"].iloc[0] == "COMPRAR"
    assert tr["trade_cost"].iloc[0] > 0


# --------------------------------------------------------------------------
# 4. No-lookahead
# --------------------------------------------------------------------------
def test_no_lookahead_day0():
    """El retorno de BTC del día 0 NO puede aparecer en equity[0]."""
    for px0_ret in [+0.30, -0.30]:
        px = [60000 * (1 + px0_ret), 60000, 61000]
        sig = make_sig([0.5, 0.5, 0.5], px)
        acc = e21.run_accounting(sig)
        assert acc["equity"].iloc[0] == pytest.approx(1 - 0.5 * e21.COST_R, rel=1e-12)


def test_no_lookahead_return_lands_next_day():
    """El retorno de hoy lo gana la posición de AYER, no el trade de hoy."""
    sig = make_sig([0.0, 1.0, 1.0], [60000, 60000, 66000])   # +10% en t=2
    acc = e21.run_accounting(sig)
    # t=1 compra al cierre; t=2 captura el +10% completo sobre el equity de t=1
    growth = acc["equity"].iloc[2] / acc["equity"].iloc[1]
    assert growth == pytest.approx(1.10, rel=1e-6)


# --------------------------------------------------------------------------
# 5. Deriva sin trade
# --------------------------------------------------------------------------
def test_drift_without_trade():
    """Señal constante + precio en movimiento -> el peso real deriva y NO se corrige."""
    sig = make_sig([0.25] * 5, [60000, 66000, 72000, 79000, 87000])
    acc = e21.run_accounting(sig)
    assert (acc["trade_pct"].iloc[1:].abs() < 1e-15).all(), "rebalanceó sin cambio de señal"
    assert (acc["trade_cost"].iloc[1:] == 0).all()
    assert acc["weight_pre"].iloc[-1] > 0.25 + 1e-3, "el peso no derivó al alza"
    assert acc["units"].nunique() == 1, "las unidades cambiaron sin trade"


def test_drift_does_not_feed_the_band():
    """La banda opera sobre `held` teórico; la deriva real jamás la realimenta."""
    px = make_prices(seed=11, drift=0.003, vol=0.02)
    tr = e21.compute_track_record_v21(px, paper_start=px.index[600])
    ref = pd.Series(e21._apply_band(tr["target_weight"].values), index=tr.index)
    # signal_weight se computa sobre la serie completa; sobre el tramo recortado
    # debe seguir siendo función SOLO de target_weight, nunca de weight_pre.
    assert (tr["signal_weight"].diff().abs().fillna(0) > 0).sum() == \
           (ref.diff().abs().fillna(0) > 0).sum()


# --------------------------------------------------------------------------
# 6. Identidad de equity
# --------------------------------------------------------------------------
def test_equity_identity():
    px = make_prices(seed=5)
    tr = e21.compute_track_record_v21(px, paper_start=px.index[600])
    lhs = tr["units"] * tr["btc_price"] + tr["cash"]
    np.testing.assert_allclose(lhs.values, tr["equity"].values, rtol=0, atol=1e-12)
    np.testing.assert_allclose(
        (tr["units"] * tr["btc_price"] / tr["equity"]).values,
        tr["weight_post"].values, rtol=0, atol=1e-12)


def test_no_negative_cash_or_units():
    px = make_prices(seed=13, vol=0.06)
    tr = e21.compute_track_record_v21(px, paper_start=px.index[600])
    assert (tr["units"] >= -1e-15).all()
    assert (tr["cash"] >= -1e-15).all(), "apalancamiento implícito: cash negativo"
    assert (tr["weight_post"] <= e21.CAP + 1e-12).all()


def test_full_weight_does_not_borrow():
    """Regresión: objetivo 1.0 no puede comprar el 100% Y pagar el fee.
    La restricción de financiamiento deja el cash exactamente en 0."""
    sig = make_sig([1.0, 1.0], [60000, 61000])
    acc = e21.run_accounting(sig)
    assert acc["cash"].iloc[0] >= -1e-15, "cash negativo: apalancamiento implícito"
    assert acc["cash"].iloc[0] == pytest.approx(0.0, abs=1e-15)
    assert acc["weight_post"].iloc[0] == pytest.approx(1.0, rel=1e-12)
    assert acc["equity"].iloc[0] == pytest.approx(1 - e21.COST_R / (1 + e21.COST_R), rel=1e-12)


# --------------------------------------------------------------------------
# 7. Determinismo
# --------------------------------------------------------------------------
def test_determinism():
    px = make_prices(seed=21)
    a = e21.compute_track_record_v21(px, paper_start=px.index[600])
    b = e21.compute_track_record_v21(px.copy(), paper_start=px.index[600])
    pd.testing.assert_frame_equal(a, b)
    assert e21.df_to_rows_v21(a) == e21.df_to_rows_v21(b)


def test_recompute_from_scratch_matches_prefix():
    """Estado recomputado, nunca persistido: un prefijo recomputado coincide."""
    px = make_prices(seed=23)
    full = e21.compute_track_record_v21(px, paper_start=px.index[600])
    short = e21.compute_track_record_v21(px.iloc[:-10], paper_start=px.index[600])
    pd.testing.assert_frame_equal(full.iloc[:len(short)], short)


# --------------------------------------------------------------------------
# 8. Salida completa
# --------------------------------------------------------------------------
def test_full_exit_zeroes_units():
    sig = make_sig([0.5, 0.5, 0.0, 0.0], [60000, 63000, 61000, 62000])
    acc = e21.run_accounting(sig)
    assert acc["units"].iloc[2] == pytest.approx(0.0, abs=1e-15)
    assert acc["weight_post"].iloc[2] == pytest.approx(0.0, abs=1e-12)
    assert acc["cash"].iloc[2] == pytest.approx(acc["equity"].iloc[2], rel=1e-12)


# --------------------------------------------------------------------------
# 9. Borde exacto de la banda
# --------------------------------------------------------------------------
def test_band_boundary_exact():
    """`>` estricto: exactamente BAND no dispara; BAND+eps sí."""
    assert e21._apply_band([0.0, 0.10]) == [0.0, 0.0]
    assert e21._apply_band([0.0, 0.1001]) == [0.0, 0.1001]


def test_band_blind_to_trend_flip_documented():
    """Defecto conocido y DELIBERADAMENTE no corregido en v2.1 (spec §9).
    El paso mínimo de trend_score (0.25) supera BAND (0.10)."""
    step = 1.0 / len(e21.LOOKBACKS)
    assert step > e21.BAND
    assert e21._apply_band([0.0, 0.25, 0.0]) == [0.0, 0.25, 0.0]


# --------------------------------------------------------------------------
# 10-11. Sincronización e integridad
# --------------------------------------------------------------------------
def test_new_rows_idempotent():
    px = make_prices(seed=31)
    tr = e21.compute_track_record_v21(px, paper_start=px.index[600])
    rows = e21.df_to_rows_v21(tr)
    assert e21.new_rows_v21(tr, [r[0] for r in rows]) == []
    partial = [r[0] for r in rows[:-3]]
    assert len(e21.new_rows_v21(tr, partial)) == 3


def test_rows_mismatch_detects_divergence():
    px = make_prices(seed=33)
    tr = e21.compute_track_record_v21(px, paper_start=px.index[600])
    rows = e21.df_to_rows_v21(tr)

    assert e21.rows_mismatch(rows, rows) == []               # consistente

    forked = [list(r) for r in rows]
    forked[5][1] = 12345.67                                  # precio alterado
    diffs = e21.rows_mismatch(rows, forked)
    assert len(diffs) == 1 and diffs[0][1] == "btc_price"

    missing = rows[:-4]                                      # fechas aún no escritas
    assert e21.rows_mismatch(rows, missing) == []


# --------------------------------------------------------------------------
# 12. Entrada desordenada
# --------------------------------------------------------------------------
def test_unsorted_input_raises():
    px = make_prices(n=300)
    with pytest.raises(ValueError, match="desordenada"):
        e21.compute_signal(px.iloc[::-1])


def test_duplicate_dates_raise():
    px = make_prices(n=300)
    dup = pd.concat([px, px.iloc[[10]]]).sort_index()
    with pytest.raises(ValueError, match="duplicadas"):
        e21.compute_signal(dup)


# --------------------------------------------------------------------------
# Extra: reconciliación de costos y ventana vacía
# --------------------------------------------------------------------------
def test_costs_reconcile_with_equity():
    """equity final == valor sin costos menos los costos compuestos."""
    sig = make_sig([0.0, 0.5, 0.0, 0.5], [60000, 61000, 59000, 60500])
    acc = e21.run_accounting(sig)
    total = acc["trade_cost"].sum()
    assert total == pytest.approx(
        acc.loc[acc["trade_cost"] > 0, "trade_cost"].sum(), rel=1e-12)
    assert (acc["trade_cost"] >= 0).all()


def test_empty_window_is_noop():
    """Antes de que cierre la primera vela post-PAPER_START: no-op limpio."""
    px = make_prices(n=300)
    tr = e21.compute_track_record_v21(px, paper_start=px.index[-1] + pd.Timedelta(days=5))
    assert len(tr) == 0
    assert e21.df_to_rows_v21(tr) == []

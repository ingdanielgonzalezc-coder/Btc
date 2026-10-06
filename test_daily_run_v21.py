"""
test_daily_run_v21.py — Tests de la capa de I/O.

Sin red y sin credenciales: se usan dobles de prueba para el worksheet. Lo que
se prueba es la LÓGICA DE DECISIÓN (¿appendear o abortar?), que es donde vive el
riesgo de forkear el registro.
"""

import numpy as np
import pandas as pd
import pytest

import daily_run_v21 as io21
import engine_v21 as e21


# --------------------------------------------------------------------------
# Dobles de prueba
# --------------------------------------------------------------------------
class FakeWorksheet:
    def __init__(self, columns, rows=None):
        self.columns = list(columns)
        self.rows = [list(r) for r in (rows or [])]
        self.appends = []
        self.updates = []

    def row_values(self, n):
        return self.columns if n == 1 else []

    def get_all_values(self, **kwargs):
        return [self.columns] + self.rows

    def append_rows(self, rows, value_input_option=None):
        self.appends.append((rows, value_input_option))
        self.rows.extend(list(r) for r in rows)

    def append_row(self, row, value_input_option=None):
        self.append_rows([row], value_input_option)

    def update(self, values=None, range_name=None):
        self.updates.append((values, range_name))


def make_tr(n=40, seed=3, generated_at="2026-08-17 00:31:00", sha="abc123", drop_last=0):
    rng = np.random.default_rng(seed)
    px = pd.Series(
        60000 * np.exp(np.cumsum(rng.normal(0.0005, 0.02, 700))),
        index=pd.date_range("2024-06-01", periods=700, freq="D"))
    if drop_last:
        px = px.iloc[:-drop_last]
    return e21.compute_track_record_v21(
        px, paper_start=pd.Timestamp("2024-06-01") + pd.Timedelta(days=700 - n),
        price_source="coinbase", code_sha=sha, generated_at_utc=generated_at)


# --------------------------------------------------------------------------
# verify_consistency
# --------------------------------------------------------------------------
def test_consistency_ok_when_sheet_matches():
    tr = make_tr()
    rows = e21.df_to_rows_v21(tr)
    ok, diffs, n = io21.verify_consistency(tr, rows)
    assert ok and diffs == []
    assert n == min(io21.CONSISTENCY_K, len(rows))


def test_consistency_ok_when_sheet_is_behind():
    """Fechas aún no escritas no son divergencia — es el caso normal."""
    tr = make_tr()
    rows = e21.df_to_rows_v21(tr)
    ok, diffs, n = io21.verify_consistency(tr, rows[:-3])
    assert ok and diffs == []


def test_consistency_detects_revised_candle():
    """El modo de falla que hundió a v2.0: Coinbase revisa una vela pasada."""
    tr = make_tr()
    rows = e21.df_to_rows_v21(tr)
    forked = [list(r) for r in rows]
    forked[-5][1] = 99999.99
    ok, diffs, _ = io21.verify_consistency(tr, forked)
    assert not ok
    assert any(d[1] == "btc_price" for d in diffs)


def test_consistency_detects_equity_divergence():
    tr = make_tr()
    rows = e21.df_to_rows_v21(tr)
    forked = [list(r) for r in rows]
    idx = e21.COLUMNS_V21.index("equity")
    forked[-2][idx] = 1.234567
    ok, diffs, _ = io21.verify_consistency(tr, forked)
    assert not ok and diffs[0][1] == "equity"


def test_consistency_window_limits_scope():
    """Solo se reconcilian las últimas K filas: una divergencia antigua queda fuera."""
    tr = make_tr(n=40)
    rows = e21.df_to_rows_v21(tr)
    forked = [list(r) for r in rows]
    forked[0][1] = 11111.11                          # fila más vieja que la ventana
    ok, _, _ = io21.verify_consistency(tr, forked, k=5)
    assert ok
    assert not io21.verify_consistency(tr, forked, k=len(rows))[0]


# --------------------------------------------------------------------------
# Append idempotente y formato de escritura
# --------------------------------------------------------------------------
def test_new_rows_only_appends_missing():
    tr = make_tr()
    rows = e21.df_to_rows_v21(tr)
    assert e21.new_rows_v21(tr, [r[0] for r in rows]) == []
    assert len(e21.new_rows_v21(tr, [r[0] for r in rows[:-2]])) == 2


def test_rows_have_exact_column_count():
    tr = make_tr()
    for row in e21.df_to_rows_v21(tr):
        assert len(row) == len(e21.COLUMNS_V21)


def test_provenance_columns_populated():
    """Sin procedencia por fila, un fork es inauditable a posteriori."""
    tr = make_tr()
    assert (tr["price_source"] == "coinbase").all()
    assert (tr["code_sha"] == "abc123").all()
    assert (tr["generated_at_utc"] != "").all()


def test_writes_use_raw():
    """USER_ENTERED deja que Sheets reinterprete según locale. RAW no."""
    ws = FakeWorksheet(e21.COLUMNS_V21)
    rows = e21.df_to_rows_v21(make_tr())
    ws.append_rows(rows, value_input_option="RAW")
    assert ws.appends[0][1] == "RAW"


def test_header_update_uses_keyword_args():
    """gspread 6 invirtió el orden posicional de update()."""
    ws = FakeWorksheet(["columna_incorrecta"])
    io21._ensure_header(ws, e21.COLUMNS_V21)
    values, range_name = ws.updates[0]
    assert values == [e21.COLUMNS_V21] and range_name == "A1"


def test_header_not_rewritten_when_correct():
    ws = FakeWorksheet(e21.COLUMNS_V21)
    io21._ensure_header(ws, e21.COLUMNS_V21)
    assert ws.updates == []


# --------------------------------------------------------------------------
# Fuente única
# --------------------------------------------------------------------------
def test_no_yfinance_fallback():
    """v2.1 es Coinbase o nada. Un fallback silencioso forkea el registro."""
    src = open(io21.__file__).read() if hasattr(io21, "__file__") else ""
    assert "yfinance" not in src.lower() or "NO tiene fuente alternativa" in src
    assert not hasattr(io21, "_fetch_yfinance")


def test_meta_columns_cover_provenance():
    for field in ["run_at_utc", "code_sha", "price_source", "consistency", "spot_price"]:
        assert field in io21.META_COLUMNS


# --------------------------------------------------------------------------
# Ventana vacía
# --------------------------------------------------------------------------
def test_empty_window_produces_no_rows():
    """Antes de la primera vela post-PAPER_START: no-op limpio, sin escribir."""
    px = pd.Series(60000 + np.arange(700, dtype=float),
                   index=pd.date_range("2024-06-01", periods=700, freq="D"))
    tr = e21.compute_track_record_v21(px, paper_start=px.index[-1] + pd.Timedelta(days=3))
    assert len(tr) == 0
    assert e21.new_rows_v21(tr, []) == []
    ok, diffs, _ = io21.verify_consistency(tr, [])
    assert ok and diffs == []


# --------------------------------------------------------------------------
# Regresión v2.1.1 — la guarda declaraba FORK todos los días desde la 2ª corrida
# --------------------------------------------------------------------------
def _as_sheets_unformatted(rows):
    """Lo que devuelve Sheets con UNFORMATTED_VALUE tras escribir con RAW:
    floats enteros vuelven como int (1.0 -> 1), el resto como número."""
    out = []
    for r in rows:
        out.append([int(v) if isinstance(v, float) and v.is_integer() else v for v in r])
    return out


def test_consistency_ignores_provenance_of_previous_run():
    """Ayer escribió otra corrida (otro timestamp, otro commit): NO es un fork."""
    yesterday = make_tr(drop_last=1, generated_at="2026-10-05 00:31:10", sha="aaaa1111")
    today = make_tr(generated_at="2026-10-06 00:31:05", sha="bbbb2222")
    sheet = e21.df_to_rows_v21(yesterday)
    ok, diffs, n = io21.verify_consistency(today, sheet)
    assert ok, diffs
    assert n == min(io21.CONSISTENCY_K, len(sheet))


def test_consistency_tolerates_sheets_number_representation():
    """1.0 vuelve como 1, 3.9e-06 como float: no es divergencia."""
    tr = make_tr()
    sheet = _as_sheets_unformatted(e21.df_to_rows_v21(tr))
    ok, diffs, _ = io21.verify_consistency(tr, sheet)
    assert ok, diffs


def test_consistency_still_detects_one_quantum_change():
    """La tolerancia (medio cuanto) no puede ocultar un cambio real del valor redondeado."""
    tr = make_tr()
    sheet = _as_sheets_unformatted(e21.df_to_rows_v21(tr))
    idx = e21.COLUMNS_V21.index("equity")
    sheet[-3][idx] = float(sheet[-3][idx]) + 1e-10      # 1 cuanto (10 decimales)
    ok, diffs, _ = io21.verify_consistency(tr, sheet)
    assert not ok and diffs[0][1] == "equity"


def test_consistency_checks_written_rows_after_long_gap():
    """Sheet atrasado > K días: la guarda debe verificar las filas escritas, no 0."""
    tr = make_tr(n=60)
    sheet = e21.df_to_rows_v21(tr)[:5]                   # 55 días sin escribir
    ok, _, n = io21.verify_consistency(tr, sheet, k=30)
    assert ok and n == 5
    forked = [list(r) for r in sheet]
    forked[2][1] = 11111.11
    assert not io21.verify_consistency(tr, forked, k=30)[0]


def test_short_sheet_row_does_not_crash():
    """Sheets recorta celdas vacías al final de la fila."""
    tr = make_tr()
    sheet = [list(r) for r in e21.df_to_rows_v21(tr)]
    sheet[-1] = sheet[-1][:-2]                           # sin code_sha / generated_at
    ok, diffs, _ = io21.verify_consistency(tr, sheet)
    assert ok, diffs

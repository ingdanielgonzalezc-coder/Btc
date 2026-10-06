"""
daily_run_v3.py — Capa de I/O de V3 todo/nada (en paralelo a v2.1)
================================================================================
Misma infraestructura que daily_run_v21.py: Coinbase como fuente única, guarda de
consistencia antes de escribir, RAW, procedencia por fila. Escribe en su propia
pestaña (`track_record_v3`) y su propio log (`meta_runs_v3`).

Un fallo de V3 nunca bloquea a v2.1: el workflow lo corre con continue-on-error.
"""

import os

import pandas as pd

import daily_run_v21 as io21
import engine_v3 as e3

CONSISTENCY_K = 30
META_TAB_V3 = "meta_runs_v3"


def _download_start():
    return (pd.Timestamp(e3.PAPER_START_V3)
            - pd.Timedelta(days=e3.WARMUP_DAYS)).strftime("%Y-%m-%d")


def fetch_prices():
    """Coinbase, velas diarias cerradas desde PAPER_START_V3 − WARMUP_DAYS."""
    start, end = pd.Timestamp(_download_start()), io21._today_utc()
    chunk = pd.Timedelta(days=290)
    rows, cursor = {}, start
    while cursor < end:
        c_end = min(cursor + chunk, end)
        url = (f"https://api.exchange.coinbase.com/products/{io21.PRICE_TICKER}/candles"
               f"?granularity=86400"
               f"&start={cursor.strftime('%Y-%m-%dT%H:%M:%SZ')}"
               f"&end={c_end.strftime('%Y-%m-%dT%H:%M:%SZ')}")
        data = io21._http_json(url)
        if isinstance(data, dict):
            raise RuntimeError(f"Coinbase: {data.get('message', data)}")
        for candle in data:
            rows[pd.Timestamp(candle[0], unit="s")] = candle[4]
        cursor = c_end
    if not rows:
        raise RuntimeError("Coinbase no devolvió velas")
    close = io21._clean_close_series(pd.Series(rows).sort_index())
    if len(close) < max(e3.LOOKBACKS) + 5:
        raise RuntimeError(f"Coinbase devolvió {len(close)} velas; insuficiente")
    return close, "coinbase"


def verify_consistency_v3(tr, sheet_rows, k=CONSISTENCY_K):
    dates_in_sheet = {r[0] for r in sheet_rows}
    recomputed = [r for r in e3.df_to_rows_v3(tr) if r[0] in dates_in_sheet]
    if k:
        recomputed = recomputed[-k:]
    diffs = e3.rows_mismatch_v3(recomputed, sheet_rows)
    return (not diffs), diffs, len(recomputed)


def _worksheet_v3(sh):
    """Pestaña de V3. Si existe con OTRO esquema y sin filas de datos (quedó de la
    V3 Donchian, que nunca escribió), se limpia entera para no dejar columnas
    viejas a la derecha. Con filas de datos nunca se toca: eso sería un fork."""
    import gspread
    try:
        ws = sh.worksheet(e3.SHEET_TAB_V3)
    except gspread.WorksheetNotFound:
        ws = sh.add_worksheet(title=e3.SHEET_TAB_V3, rows=2000, cols=len(e3.COLUMNS_V3))
    if ws.row_values(1) != e3.COLUMNS_V3 and not io21._sheet_rows(ws):
        ws.clear()
    return io21._ensure_header(ws, e3.COLUMNS_V3)


def log_meta_run_v3(sh, **fields):
    try:
        ws = io21._worksheet(sh, META_TAB_V3, io21.META_COLUMNS)
        ws.append_row([str(fields.get(c, "")) for c in io21.META_COLUMNS],
                      value_input_option="RAW")
    except Exception as exc:                        # noqa: BLE001
        print(f"  aviso: no se pudo escribir {META_TAB_V3} ({exc})")


def main():
    run_at = pd.Timestamp.now(tz="UTC").strftime("%Y-%m-%d %H:%M:%S")
    sha = os.environ.get("GITHUB_SHA", "")[:12]

    precios, source = fetch_prices()
    spot = io21.fetch_spot()
    tr = e3.compute_track_record_v3(precios, paper_start=e3.PAPER_START_V3,
                                    price_source=source, code_sha=sha,
                                    generated_at_utc=run_at)

    sh = io21._open_sheet()
    ws = _worksheet_v3(sh)
    existing = io21._sheet_rows(ws)
    meta = dict(run_at_utc=run_at, code_sha=sha, price_source=source,
                last_candle=precios.index[-1].strftime("%Y-%m-%d"),
                rows_in_sheet=len(existing),
                spot_price=spot if spot is not None else "")

    ok, diffs, n_checked = verify_consistency_v3(tr, existing)
    if not ok:
        print(f"V3 FORK DETECTADO — {len(diffs)} celda(s):")
        for d in diffs[:20]:
            print("  ", d)
        log_meta_run_v3(sh, **meta, rows_added=0,
                        consistency=f"FORK ({len(diffs)} celdas)", note="abortada")
        raise SystemExit(1)

    to_add = e3.new_rows_v3(tr, [r[0] for r in existing])
    if to_add:
        ws.append_rows(to_add, value_input_option="RAW")
    log_meta_run_v3(sh, **meta, rows_added=len(to_add),
                    consistency=f"OK ({n_checked}/{len(tr)})", note="")

    print(f"OK | V3: {len(tr)} filas | sheet tenía {len(existing)} | +{len(to_add)} nuevas")
    if len(tr) > 0:
        last = tr.iloc[-1]
        n_rec = int((tr["live"] == 0).sum())
        print(f"Hoy ({tr.index[-1].date()}): {last['action']} | "
              f"plazos al alza={int(last['votes_up'])}/4 objetivo={last['target_weight']:.0f} "
              f"w_real={last['weight_post']:.4f} | px={last['btc_price']:.0f} | "
              f"equity={last['equity']:.6f} | filas reconstruidas={n_rec}")
    else:
        print(f"Aún no hay velas cerradas desde PAPER_START_V3 ({e3.PAPER_START_V3}).")


if __name__ == "__main__":
    main()

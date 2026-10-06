"""
daily_run_exec.py — I/O del registro de ejecución atrasada (pestaña track_record_exec)
================================================================================
Descarga velas diarias (validadas, igual que v2.1) y velas HORARIAS de Coinbase desde
el inicio del registro; recomputa v2.1 y V3 con ejecución a las EXEC_HOUR_UTC del día
siguiente; guarda de consistencia; append idempotente por (fecha, versión).
Corre con continue-on-error: nunca bloquea a los registros oficiales.
"""

import os
import time

import pandas as pd

import daily_run_v21 as io21
import engine_exec as ex

CONSISTENCY_K = 60          # últimas filas (ambas versiones) a reconciliar


def fetch_hourly_open(start, end):
    """Aperturas de velas horarias Coinbase en [start, end). Máx 300 por request."""
    rows, cursor, chunk = {}, pd.Timestamp(start), pd.Timedelta(hours=290)
    end = pd.Timestamp(end)
    while cursor < end:
        c_end = min(cursor + chunk, end)
        url = (f"https://api.exchange.coinbase.com/products/{io21.PRICE_TICKER}/candles"
               f"?granularity=3600"
               f"&start={cursor.strftime('%Y-%m-%dT%H:%M:%SZ')}"
               f"&end={c_end.strftime('%Y-%m-%dT%H:%M:%SZ')}")
        data = io21._http_json(url)
        if isinstance(data, dict):
            raise RuntimeError(f"Coinbase: {data.get('message', data)}")
        for c in data:                                   # [time, low, high, open, close, volume]
            rows[pd.Timestamp(c[0], unit="s")] = c[3]
        cursor = c_end
        time.sleep(0.15)
    s = pd.Series(rows, dtype="float64").sort_index()
    return s[~s.index.duplicated(keep="last")]


def verify_consistency_exec(df_all, sheet_rows, k=CONSISTENCY_K):
    keys = {(r[0], r[1]) for r in sheet_rows if len(r) >= 2}
    recomputed = [r for r in ex.df_to_rows_exec(df_all) if (r[0], r[1]) in keys]
    recomputed = sorted(recomputed, key=lambda r: (r[0], r[1]))[-k:] if k else recomputed
    diffs = ex.rows_mismatch_exec(recomputed, sheet_rows)
    return (not diffs), diffs, len(recomputed)


def main():
    run_at = pd.Timestamp.now(tz="UTC").strftime("%Y-%m-%d %H:%M:%S")
    sha = os.environ.get("GITHUB_SHA", "")[:12]
    precios, _ = io21.fetch_prices()
    hourly = fetch_hourly_open(pd.Timestamp(ex.PAPER_START_EXEC) + pd.Timedelta(days=1),
                               pd.Timestamp.now(tz="UTC").tz_localize(None).floor("h") + pd.Timedelta(hours=1))
    df_all = pd.concat([ex.compute_exec_record(precios, hourly, v, code_sha=sha, generated_at_utc=run_at)
                        for v in ex.VERSIONS]).sort_index(kind="stable")

    sh = io21._open_sheet()
    ws = io21._worksheet(sh, ex.SHEET_TAB_EXEC, ex.COLUMNS_EXEC)
    existing = io21._sheet_rows(ws)
    ok, diffs, n = verify_consistency_exec(df_all, existing)
    if not ok:
        print(f"EJECUCIÓN: FORK — {len(diffs)} celda(s)")
        for d in diffs[:20]:
            print("  ", d)
        raise SystemExit(1)
    to_add = ex.new_rows_exec(df_all, existing)
    if to_add:
        ws.append_rows(sorted(to_add, key=lambda r: (r[0], r[1])), value_input_option="RAW")
    print(f"OK | ejecución {ex.EXEC_HOUR_UTC:02d}:00 UTC: {len(df_all)} filas | sheet tenía {len(existing)} | "
          f"+{len(to_add)} nuevas | consistencia OK ({n})")
    for v in ex.VERSIONS:
        d = df_all[df_all["version"] == v]
        if len(d):
            last = d.iloc[-1]
            print(f"  {v}: hasta {d.index[-1].date()} | capital al cierre {last['equity_close']:.6f} | "
                  f"HODL {last['hodl_close']:.6f}")


if __name__ == "__main__":
    main()

"""
daily_run_v21.py — Capa de I/O de v2.1
================================================================================
Orquesta: fetch (Coinbase única fuente) -> engine_v21 -> guarda de consistencia
-> append idempotente al Sheet -> registro de procedencia en `meta_runs`.

Toda la lógica de estrategia y contabilidad vive en engine_v21.py. Este archivo
solo mueve datos. Las funciones puras (rows_mismatch, new_rows_v21) están allá y
ya tienen tests.

DIFERENCIAS CLAVE CON v2.0 (daily_run.py):

  1. FUENTE ÚNICA. Coinbase y nada más. v2.0 tenía fallback a yfinance, y el
     cambio de fuente a mitad del registro fue una de las razones para archivarlo.
     Si Coinbase falla: NO se escribe. El gap-fill repara mañana.

  2. GUARDA DE CONSISTENCIA. Antes de appendear se recomputan las últimas K filas
     y se comparan contra el Sheet como strings exactos. Mismatch => NO appendear,
     exit 1. Nunca sobrescribir en silencio: una divergencia es un fork del
     registro y la decide un humano.

  3. RAW. value_input_option="RAW" evita que Sheets reinterprete valores según
     locale. Elimina de raíz la clase de bug de la coma decimal.

  4. meta_runs. Una fila por corrida con procedencia: SHA, fuente, timestamp, y
     el precio SPOT al momento de correr. Ese último campo acumula la
     distribución empírica del implementation shortfall — el gap entre el cierre
     de señal (00:00 UTC) y la ejecución real (cron 00:30+ UTC). Es MEDICIÓN, no
     entra al motor: el registro debe seguir siendo recomputable.

v2.0 sigue corriendo en paralelo desde daily_run.py, en su propia pestaña.
"""

import json
import os
import urllib.request

import numpy as np
import pandas as pd

import engine_v21 as e21

PRICE_TICKER  = "BTC-USD"
CONSISTENCY_K = 30          # últimas K filas a reconciliar en cada corrida
META_TAB      = "meta_runs"
META_COLUMNS  = [
    "run_at_utc", "code_sha", "price_source", "last_candle",
    "rows_in_sheet", "rows_added", "consistency", "spot_price", "note",
]


# ============================================================================
# FETCH — Coinbase única fuente canónica
# ============================================================================
def _download_start():
    return (pd.Timestamp(e21.PAPER_START_V21)
            - pd.Timedelta(days=e21.WARMUP_DAYS)).strftime("%Y-%m-%d")


def _today_utc():
    """Medianoche UTC de hoy, naive — frontera para descartar la vela en curso."""
    return pd.Timestamp.now(tz="UTC").normalize().tz_localize(None)


def _clean_close_series(close):
    idx = pd.to_datetime(close.index)
    if getattr(idx, "tz", None) is not None:
        idx = idx.tz_convert("UTC").tz_localize(None)
    close.index = idx.normalize()
    close = close[~close.index.duplicated(keep="last")].sort_index().dropna()
    close = close[close.index < _today_utc()]      # SOLO velas cerradas
    return close.astype(float)


def _http_json(url, timeout=30):
    req = urllib.request.Request(url, headers={"User-Agent": "btc-paper-v21/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


def fetch_prices():
    """
    Coinbase Exchange, velas diarias. Máx ~300 por request -> páginas de 290.
    Devuelve (serie de cierres cerrados, "coinbase").
    Lanza si falla: v2.1 NO tiene fuente alternativa, por diseño.
    """
    start, end = pd.Timestamp(_download_start()), _today_utc()
    chunk = pd.Timedelta(days=290)
    rows, cursor = {}, start

    while cursor < end:
        c_end = min(cursor + chunk, end)
        url = (f"https://api.exchange.coinbase.com/products/{PRICE_TICKER}/candles"
               f"?granularity=86400"
               f"&start={cursor.strftime('%Y-%m-%dT%H:%M:%SZ')}"
               f"&end={c_end.strftime('%Y-%m-%dT%H:%M:%SZ')}")
        data = _http_json(url)
        if isinstance(data, dict):                  # error: {"message": ...}
            raise RuntimeError(f"Coinbase: {data.get('message', data)}")
        for candle in data:                         # [time, low, high, open, close, volume]
            rows[pd.Timestamp(candle[0], unit="s")] = candle[4]
        cursor = c_end

    if not rows:
        raise RuntimeError("Coinbase no devolvió velas")

    close = _clean_close_series(pd.Series(rows).sort_index())
    if len(close) < max(e21.LOOKBACKS) + 5:
        raise RuntimeError(
            f"Coinbase devolvió {len(close)} velas; se requieren "
            f"{max(e21.LOOKBACKS) + 5} para computar la señal")
    return close, "coinbase"


def fetch_spot():
    """Precio spot al momento de la corrida. Best-effort: solo alimenta meta_runs,
    nunca el motor. Un fallo aquí no puede tumbar la corrida."""
    try:
        tick = _http_json(
            f"https://api.exchange.coinbase.com/products/{PRICE_TICKER}/ticker",
            timeout=10)
        return float(tick["price"])
    except Exception as exc:                        # noqa: BLE001
        print(f"  aviso: spot no disponible ({exc})")
        return None


# ============================================================================
# SHEET
# ============================================================================
def _open_sheet():
    import gspread
    from google.oauth2.service_account import Credentials

    creds = Credentials.from_service_account_info(
        json.loads(os.environ["GOOGLE_SERVICE_ACCOUNT_JSON"]),
        scopes=["https://www.googleapis.com/auth/spreadsheets"])
    return gspread.authorize(creds).open_by_key(os.environ["SHEET_ID"])


def _ensure_header(ws, columns):
    """Escribe el header si no coincide. Sin dependencia de gspread -> testeable."""
    if ws.row_values(1) != columns:
        # keyword args: gspread 6 invirtió el orden posicional de update()
        ws.update(values=[columns], range_name="A1")
    return ws


def _worksheet(sh, title, columns):
    import gspread
    try:
        ws = sh.worksheet(title)
    except gspread.WorksheetNotFound:
        ws = sh.add_worksheet(title=title, rows=2000, cols=len(columns))
    return _ensure_header(ws, columns)


def _sheet_rows(ws):
    """Todas las filas de datos del Sheet, sin header."""
    values = ws.get_all_values()
    return [r for r in values[1:] if r and r[0]]


def verify_consistency(tr, sheet_rows, k=CONSISTENCY_K):
    """
    Reconcilia las últimas k filas recomputadas contra lo ya escrito.

    Detecta el modo de falla que hundió a v2.0: el Sheet solo comparaba FECHAS,
    así que una vela revisada por Coinbase o un cambio de fuente producía un fork
    silencioso e inauditable.

    Devuelve (ok: bool, diffs: list, n_checked: int).
    """
    recomputed = e21.df_to_rows_v21(tr)[-k:] if k else e21.df_to_rows_v21(tr)
    diffs = e21.rows_mismatch(recomputed, sheet_rows)
    dates_in_sheet = {r[0] for r in sheet_rows}
    n_checked = sum(1 for r in recomputed if r[0] in dates_in_sheet)
    return (not diffs), diffs, n_checked


def log_meta_run(sh, **fields):
    """Append a meta_runs. Best-effort: si falla, no puede tumbar la corrida."""
    try:
        ws = _worksheet(sh, META_TAB, META_COLUMNS)
        ws.append_row([str(fields.get(c, "")) for c in META_COLUMNS],
                      value_input_option="RAW")
    except Exception as exc:                        # noqa: BLE001
        print(f"  aviso: no se pudo escribir meta_runs ({exc})")


# ============================================================================
def main():
    run_at = pd.Timestamp.now(tz="UTC").strftime("%Y-%m-%d %H:%M:%S")
    sha = os.environ.get("GITHUB_SHA", "")[:12]

    precios, source = fetch_prices()
    spot = fetch_spot()
    last_candle = precios.index[-1].strftime("%Y-%m-%d")

    tr = e21.compute_track_record_v21(
        precios, paper_start=e21.PAPER_START_V21,
        price_source=source, code_sha=sha, generated_at_utc=run_at)

    sh = _open_sheet()
    ws = _worksheet(sh, e21.SHEET_TAB_V21, e21.COLUMNS_V21)
    existing = _sheet_rows(ws)

    meta = dict(run_at_utc=run_at, code_sha=sha, price_source=source,
                last_candle=last_candle, rows_in_sheet=len(existing),
                spot_price=spot if spot is not None else "")

    # --- guarda de integridad: corre ANTES de escribir nada ---
    ok, diffs, n_checked = verify_consistency(tr, existing)
    if not ok:
        print(f"FORK DETECTADO — {len(diffs)} celda(s) divergen del Sheet:")
        for date, col, sheet_val, recomputed_val in diffs[:20]:
            print(f"  {date} {col}: sheet={sheet_val!r} recomputado={recomputed_val!r}")
        if len(diffs) > 20:
            print(f"  … y {len(diffs) - 20} más")
        print("NO se appendeó nada. Revisar a mano: puede ser una vela revisada "
              "por Coinbase o un cambio de código. La decisión es humana.")
        log_meta_run(sh, **meta, rows_added=0,
                     consistency=f"FORK ({len(diffs)} celdas)",
                     note="ejecución abortada")
        raise SystemExit(1)

    to_add = e21.new_rows_v21(tr, [r[0] for r in existing])
    if to_add:
        ws.append_rows(to_add, value_input_option="RAW")

    log_meta_run(sh, **meta, rows_added=len(to_add),
                 consistency=f"OK ({n_checked}/{len(tr)})", note="")

    print(f"OK | v2.1: {len(tr)} filas | sheet tenía {len(existing)} | "
          f"+{len(to_add)} nuevas | consistencia OK ({n_checked} filas) | "
          f"fuente {source}")

    if len(tr) > 0:
        last = tr.iloc[-1]
        print(f"Hoy ({tr.index[-1].date()}): {last['action']} | "
              f"signal_w={last['signal_weight']:.2f} "
              f"w_real={last['weight_post']:.4f} | "
              f"px={last['btc_price']:.0f} | equity={last['equity']:.6f}")
        if spot and to_add and abs(last["trade_pct"]) > 1e-9:
            gap = spot / last["btc_price"] - 1
            print(f"  shortfall estimado: cierre={last['btc_price']:.0f} "
                  f"spot={spot:.0f} ({gap * 100:+.2f}%)")
    else:
        print(f"Aún no hay velas cerradas desde PAPER_START_V21 "
              f"({e21.PAPER_START_V21}); la primera fila aparecerá al cerrar su vela.")


if __name__ == "__main__":
    main()

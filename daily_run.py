"""
daily_run.py — Paper trading de la estrategia BTC (componente 1: cómputo diario)
================================================================================
Corre una vez al día en GitHub Actions:
  1. Baja cierres diarios de BTC desde una FECHA DE INICIO FIJA (yfinance primaria,
     Coinbase de fallback) y descarta la vela del día en curso.
  2. Corre el MOTOR ÚNICO `compute_track_record` (lógica congelada, sección 2.5 del
     handoff) -> DataFrame con una fila por día.
  3. Lee las fechas ya presentes en el Google Sheet y appendea SOLO las filas nuevas
     (idempotente y robusto a gaps).

La lógica y los parámetros de la sección 2 del handoff están CONGELADOS y validados.
Este archivo construye la infraestructura alrededor; NO los modifica.

Variables de entorno requeridas (secrets de GitHub):
  GOOGLE_SERVICE_ACCOUNT_JSON  -> contenido JSON de la clave de la service account
  SHEET_ID                     -> id del Google Sheet
"""

import os
import json
import datetime as dt

import numpy as np
import pandas as pd

# ===== PARÁMETROS CONGELADOS (NO modificar / NO re-optimizar) — handoff 2.1 =====
LOOKBACKS  = (20, 60, 120, 250)
TARGET_VOL = 0.50
EWMA_SPAN  = 30
CAP        = 1.0
BAND       = 0.10
FEE        = 0.0004
SLIP       = 0.0003
STABLE_APY = 0.04
ANN        = 365

# ===== CONFIG DEL DESPLIEGUE (esto sí se ajusta) =====
# Día en que "enciendes" el paper trading: el track record arranca aquí, equity = 1.0.
# Ponlo en tu fecha real de lanzamiento. Debe quedar FIJO una vez en producción
# (si lo mueves, las filas pasadas del sheet dejan de cuadrar con una corrida fresca).
PAPER_START = "2026-06-06"

# Cuánta historia bajar ANTES de PAPER_START solo para el warmup de la señal.
# 250 es el mínimo (lookback más largo); usamos 420 para que la EWMA quede estable.
# DOWNLOAD_START es determinista porque PAPER_START es fijo.
WARMUP_DAYS    = 420
SHEET_TAB      = "track_record"
PRICE_TICKER   = "BTC-USD"

# Orden EXACTO de columnas del sheet — handoff sección 6.
COLUMNS = [
    "date", "btc_price", "trend_score", "vol_scalar", "target_weight",
    "prev_weight", "new_weight", "action", "trade_pct", "daily_return",
    "strat_equity", "hodl_equity", "drawdown",
]


# ============================================================================
# MOTOR ÚNICO — fuente de verdad (handoff sección 2.5, congelado)
# ============================================================================
def compute_track_record(precios, paper_start=None):
    """
    precios: pd.Series de cierres diarios SOLO de velas cerradas, índice de fechas,
             desde una FECHA DE INICIO FIJA (no ventana rodante).
    Devuelve un DataFrame con una fila por día y todas las columnas del sheet.
    Determinista: las filas pasadas NO cambian entre corridas.
    El peso de AYER gana el retorno de HOY (sin lookahead); el costo se carga el
    MISMO día del trade (weight.diff()).
    """
    ret = precios.pct_change()
    trend = pd.concat([(precios > precios.shift(L)).astype(float) for L in LOOKBACKS],
                      axis=1).mean(axis=1)
    vol = ret.ewm(span=EWMA_SPAN).std() * np.sqrt(ANN)
    vol_scalar = (TARGET_VOL / vol).clip(upper=CAP)
    target = (trend * vol_scalar).clip(0.0, CAP).fillna(0.0)
    # banda de no-trade: al romper > BAND, salta al objetivo completo
    held, w = 0.0, []
    for tw in target.values:
        if abs(tw - held) > BAND:
            held = tw
        w.append(held)
    weight = pd.Series(w, index=precios.index)
    wl = weight.shift(1)
    cash_d = (1 + STABLE_APY) ** (1 / ANN) - 1
    strat_ret = wl * ret + (1 - wl) * cash_d - weight.diff().abs() * (FEE + SLIP)
    chg = weight.diff().fillna(weight)            # primer día: cambio = peso inicial
    action = np.where(chg > 1e-9, "COMPRAR", np.where(chg < -1e-9, "VENDER", "MANTENER"))
    df = pd.DataFrame({
        "btc_price": precios, "trend_score": trend, "vol_scalar": vol_scalar,
        "target_weight": target, "prev_weight": wl, "new_weight": weight,
        "action": action, "trade_pct": weight.diff(), "daily_return": ret,
        "strat_ret": strat_ret,
    })
    df.index.name = "date"
    # descartar warmup POR POSICIÓN: la señal con shift(250) usa historia incompleta.
    # (OJO: precios > precios.shift(L) da False, no NaN, así que dropna NO sirve aquí.)
    df = df.iloc[max(LOOKBACKS):]
    if paper_start is not None:                    # curva "desde que arranqué el paper"
        df = df[df.index >= paper_start]
    # equities DESPUÉS de recortar, para que arranquen ~1.0 en la primera fila válida.
    # (OJO: usar ret.fillna(0), no (1+ret).fillna(0), que pondría el primer factor en 0.)
    df["strat_ret"] = df["strat_ret"].fillna(0.0)
    df["strat_equity"] = (1 + df["strat_ret"]).cumprod()
    df["hodl_equity"]  = (1 + df["daily_return"].fillna(0.0)).cumprod()
    # Robustez (no cambia la lógica): el día que enciendes, la última vela cerrada es
    # la de AYER, así que la ventana >= PAPER_START puede estar vacía hasta mañana.
    # Sin este guard, el re-basado .iloc[0] crashea. Ventana vacía -> no-op limpio.
    if paper_start is not None and len(df) > 0:    # normalizar a exactamente 1.0 en el inicio
        df["strat_equity"] /= df["strat_equity"].iloc[0]
        df["hodl_equity"]  /= df["hodl_equity"].iloc[0]
    df["drawdown"] = df["strat_equity"] / df["strat_equity"].cummax() - 1
    return df.drop(columns="strat_ret")


# ============================================================================
# FUENTE DE PRECIO (handoff 5.2) — geo-abierta; OKX/Binance fallan en runners US
# ============================================================================
def _download_start():
    return (pd.Timestamp(PAPER_START) - pd.Timedelta(days=WARMUP_DAYS)).strftime("%Y-%m-%d")


def _today_utc():
    # medianoche UTC de hoy, naive — frontera para descartar la vela en curso
    return pd.Timestamp.now(tz="UTC").normalize().tz_localize(None)


def _clean_close_series(close):
    """Normaliza índice a fechas naive, ordena, dedup y descarta la vela del día en curso."""
    idx = pd.to_datetime(close.index)
    if getattr(idx, "tz", None) is not None:
        idx = idx.tz_convert("UTC").tz_localize(None)
    close.index = idx.normalize()
    close = close[~close.index.duplicated(keep="last")].sort_index().dropna()
    close = close[close.index < _today_utc()]     # handoff 5.1.2 / checklist: solo velas cerradas
    return close.astype(float)


def _fetch_yfinance():
    import yfinance as yf
    df = yf.download(PRICE_TICKER, start=_download_start(), interval="1d",
                     auto_adjust=True, progress=False)
    if df is None or len(df) == 0:
        raise RuntimeError("yfinance devolvió vacío")
    close = df["Close"]
    if isinstance(close, pd.DataFrame):            # columnas MultiIndex en yfinance reciente
        close = close.iloc[:, 0]
    return _clean_close_series(close.copy())


def _fetch_coinbase():
    """Fallback geo-abierto. Endpoint público de velas diarias (máx ~300 por request)."""
    import urllib.request

    start = pd.Timestamp(_download_start())
    end = _today_utc()
    chunk = pd.Timedelta(days=290)                 # < 300 velas por request
    rows = {}
    cursor = start
    while cursor < end:
        c_end = min(cursor + chunk, end)
        url = (f"https://api.exchange.coinbase.com/products/{PRICE_TICKER}/candles"
               f"?granularity=86400&start={cursor.isoformat()}&end={c_end.isoformat()}")
        req = urllib.request.Request(url, headers={"User-Agent": "btc-paper/1.0"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode())
        for candle in data:                        # [time, low, high, open, close, volume]
            ts = pd.Timestamp(candle[0], unit="s")
            rows[ts] = candle[4]
        cursor = c_end
    if not rows:
        raise RuntimeError("Coinbase no devolvió velas")
    close = pd.Series(rows).sort_index()
    return _clean_close_series(close)


def fetch_prices():
    """yfinance primaria; Coinbase de fallback. Devuelve pd.Series de cierres cerrados."""
    try:
        close = _fetch_yfinance()
        if len(close) >= max(LOOKBACKS) + 5:
            return close
        print("yfinance devolvió pocos datos; intentando Coinbase…")
    except Exception as e:                          # noqa: BLE001
        print(f"yfinance falló ({e}); intentando Coinbase…")
    return _fetch_coinbase()


# ============================================================================
# SINCRONIZACIÓN AL SHEET — append idempotente, robusto a gaps (handoff 5.1 / 6)
# ============================================================================
def _safe(value, ndigits):
    """Float redondeado, o '' si es NaN (para que el sheet no muestre 'NaN')."""
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return ""
    return round(float(value), ndigits)


def df_to_rows(tr):
    """DataFrame del motor -> lista de filas en el ORDEN EXACTO de COLUMNS."""
    rows = []
    for date, r in tr.iterrows():
        rows.append([
            pd.Timestamp(date).strftime("%Y-%m-%d"),
            _safe(r["btc_price"], 2),
            _safe(r["trend_score"], 6),
            _safe(r["vol_scalar"], 6),
            _safe(r["target_weight"], 6),
            _safe(r["prev_weight"], 6),
            _safe(r["new_weight"], 6),
            str(r["action"]),
            _safe(r["trade_pct"], 6),
            _safe(r["daily_return"], 8),
            _safe(r["strat_equity"], 8),
            _safe(r["hodl_equity"], 8),
            _safe(r["drawdown"], 8),
        ])
    return rows


def new_rows(tr, existing_dates):
    """Filas cuya fecha (col 0) NO está ya en el sheet. Pura -> testeable sin gspread."""
    existing = set(existing_dates)
    return [row for row in df_to_rows(tr) if row[0] not in existing]


def _open_worksheet():
    import gspread
    from google.oauth2.service_account import Credentials

    creds_info = json.loads(os.environ["GOOGLE_SERVICE_ACCOUNT_JSON"])
    scopes = ["https://www.googleapis.com/auth/spreadsheets"]
    creds = Credentials.from_service_account_info(creds_info, scopes=scopes)
    gc = gspread.authorize(creds)
    sh = gc.open_by_key(os.environ["SHEET_ID"])
    try:
        ws = sh.worksheet(SHEET_TAB)
    except gspread.WorksheetNotFound:
        ws = sh.add_worksheet(title=SHEET_TAB, rows=2000, cols=len(COLUMNS))
    return ws


def _ensure_header(ws):
    header = ws.row_values(1)
    if header != COLUMNS:
        ws.update("A1", [COLUMNS])


def _existing_dates(ws):
    col = ws.col_values(1)                          # columna 'date' incluyendo header
    return [d for d in col[1:] if d]                # sin header, sin vacíos


def sync_to_sheet(tr):
    ws = _open_worksheet()
    _ensure_header(ws)
    existing = _existing_dates(ws)
    to_add = new_rows(tr, existing)
    if to_add:
        ws.append_rows(to_add, value_input_option="USER_ENTERED")
    return len(to_add), len(existing)


# ============================================================================
def main():
    precios = fetch_prices()
    tr = compute_track_record(precios, paper_start=pd.Timestamp(PAPER_START))
    added, had = sync_to_sheet(tr)                  # crea header aunque tr esté vacío
    print(f"OK | track record: {len(tr)} filas | sheet tenía {had} fechas | +{added} nuevas")
    if len(tr) > 0:
        last = tr.iloc[-1]
        print(f"Hoy ({tr.index[-1].date()}): {last['action']} | "
              f"target={last['target_weight']:.2f} new_w={last['new_weight']:.2f} "
              f"px={last['btc_price']:.0f}")
    else:
        print(f"Aún no hay velas cerradas desde PAPER_START ({PAPER_START}); "
              f"la primera fila aparecerá cuando cierre su vela.")


if __name__ == "__main__":
    main()

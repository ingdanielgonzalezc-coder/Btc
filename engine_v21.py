"""
engine_v21.py — Motor v2.1 del paper trading BTC
================================================================================
Dos capas estrictamente separadas:

  Capa 1 (CONGELADA)  compute_signal()   — bit-idéntica a v2.0. NO tocar.
  Capa 2 (NUEVA)      run_accounting()   — unidades + cash, arranque desde cash,
                                           sin rebase, deriva real del peso.

La señal se computa sobre la serie COMPLETA (warmup incluido) porque el estado
de la banda y la EWMA dependen del inicio de la descarga. La contabilidad corre
SOLO desde PAPER_START: eso es lo que elimina la posición heredada de v2.0.

Determinismo: el estado (units, cash) es interno al cómputo y se reconstruye
desde el día 0 en cada corrida. NUNCA se persiste entre corridas.

Ver ESPECIFICACION_v2.1.md para el detalle de cada decisión de diseño.
"""

import numpy as np
import pandas as pd

# ===== PARÁMETROS CONGELADOS — idénticos a v2.0, no re-optimizar =====
LOOKBACKS  = (20, 60, 120, 250)
TARGET_VOL = 0.50
EWMA_SPAN  = 30
CAP        = 1.0
BAND       = 0.10
FEE        = 0.0004
SLIP       = 0.0003
STABLE_APY = 0.04
ANN        = 365

# ===== CONFIG DEL DESPLIEGUE — congelar al lanzar =====
# CONFIRMAR antes del primer push. Debe ser POSTERIOR al commit que congela v2.1
# (§12 de la spec: el commit precede al registro, con GitHub como testigo).
PAPER_START_V21 = "2026-08-10"
WARMUP_DAYS     = 420
SHEET_TAB_V21   = "track_record_v21"

COLUMNS_V21 = [
    "date", "btc_price", "price_source",
    "trend_score", "vol_scalar", "target_weight", "signal_weight",
    "weight_pre", "weight_post", "action", "trade_pct", "trade_cost",
    "units", "cash", "equity",
    "daily_return", "hodl_equity", "cash_equity", "drawdown",
    "code_sha", "generated_at_utc",
]

_ROUND = {
    "btc_price": 2, "trend_score": 6, "vol_scalar": 6, "target_weight": 6,
    "signal_weight": 6, "weight_pre": 6, "weight_post": 6, "trade_pct": 6,
    "trade_cost": 10, "units": 10, "cash": 10, "equity": 10,
    "daily_return": 8, "hodl_equity": 8, "cash_equity": 8, "drawdown": 8,
}

CASH_D = (1 + STABLE_APY) ** (1 / ANN) - 1
COST_R = FEE + SLIP
_EPS_SIGNAL = 1e-12   # comparación de cambio de señal
_EPS_ACTION = 1e-9    # umbral de etiquetado COMPRAR/VENDER


# ============================================================================
# CAPA 1 — SEÑAL (CONGELADA, bit-idéntica a v2.0)
# ============================================================================
def _apply_band(target_values):
    """Banda de no-trade. Extraída para testear el borde exacto de BAND.
    Comparación `>` ESTRICTA: un salto de exactamente 0.10 NO dispara."""
    held, out = 0.0, []
    for tw in target_values:
        if abs(tw - held) > BAND:
            held = tw
        out.append(held)
    return out


def compute_signal(precios):
    """
    CONGELADA — cualquier cambio aquí es un cambio de señal y exige v-entero nuevo.
    Corre sobre la serie COMPLETA (warmup incluido): la trayectoria de `held` y la
    ponderación de la EWMA dependen de dónde empieza la serie.
    """
    if not precios.index.is_monotonic_increasing:
        raise ValueError("serie de precios desordenada")
    if precios.index.has_duplicates:
        raise ValueError("serie de precios con fechas duplicadas")

    ret = precios.pct_change()
    # OJO: `precios > precios.shift(L)` devuelve False (no NaN) en el warmup;
    # por eso el descarte es POR POSICIÓN más abajo, no con dropna().
    trend = pd.concat(
        [(precios > precios.shift(L)).astype(float) for L in LOOKBACKS], axis=1
    ).mean(axis=1)
    vol = ret.ewm(span=EWMA_SPAN).std() * np.sqrt(ANN)        # adjust=True (default)
    vol_scalar = (TARGET_VOL / vol).clip(upper=CAP)
    target = (trend * vol_scalar).clip(0.0, CAP).fillna(0.0)
    signal_weight = pd.Series(_apply_band(target.values), index=precios.index)

    sig = pd.DataFrame({
        "btc_price": precios,
        "daily_return": ret,
        "trend_score": trend,
        "vol_scalar": vol_scalar,
        "target_weight": target,
        "signal_weight": signal_weight,
    })
    sig.index.name = "date"
    return sig


# ============================================================================
# CAPA 2 — CONTABILIDAD (NUEVA)
# ============================================================================
def run_accounting(sig):
    """
    sig: DataFrame de compute_signal() YA recortado al tramo del track record.
         La primera fila es el día 0 (fundación de la cuenta).

    Cuenta nace con equity=1.0, 100% cash, 0 unidades. Ejecuta la señal del
    cierre del día 0 pagando el costo -> equity[0] = 1 - cost. SIN rebase.

    Rebalanceo SOLO cuando la señal congelada cambia (§4.4): entre cambios el
    peso real deriva con el precio y no se corrige. La deriva NUNCA realimenta
    la banda.
    """
    n = len(sig)
    cols = ["weight_pre", "weight_post", "trade_pct", "trade_cost",
            "units", "cash", "equity", "hodl_equity", "cash_equity"]
    if n == 0:
        return pd.DataFrame(columns=cols, index=sig.index)

    px = sig["btc_price"].to_numpy(dtype=float)
    sw = sig["signal_weight"].to_numpy(dtype=float)
    ret = sig["daily_return"].to_numpy(dtype=float)

    out = {c: np.zeros(n) for c in cols}
    units, cash = 0.0, 1.0

    for t in range(n):
        if t == 0:
            eq_pre = units * px[0] + cash              # = 1.0
            w_pre = 0.0
            traded = True                              # ejecución inicial
        else:
            cash *= (1 + CASH_D)                       # devengo del día
            eq_pre = units * px[t] + cash              # mark-to-market al cierre de hoy
            w_pre = units * px[t] / eq_pre             # peso REAL, ya derivado
            traded = abs(sw[t] - sw[t - 1]) > _EPS_SIGNAL

        dv = cost = 0.0
        if traded:
            dv = sw[t] * eq_pre - units * px[t]
            # Restricción de financiamiento: una compra debe pagar el activo Y el
            # costo con el cash disponible -> dv*(1+COST_R) <= cash. Sin esto, un
            # objetivo de 1.0 dejaría el cash negativo (apalancamiento implícito).
            # Solo muerde en el extremo; al tope el cash queda exactamente en 0.
            if dv > 0.0:
                dv = min(dv, cash / (1.0 + COST_R))
            cost = abs(dv) * COST_R
            units += dv / px[t]
            cash -= dv + cost

        eq = units * px[t] + cash
        out["weight_pre"][t] = w_pre
        out["weight_post"][t] = units * px[t] / eq
        out["trade_pct"][t] = dv / eq_pre
        out["trade_cost"][t] = cost
        out["units"][t] = units
        out["cash"][t] = cash
        out["equity"][t] = eq

        # Benchmarks. HODL compra en el día 0 pagando el mismo costo una vez
        # (like-for-like: ambas estrategias nacen en cash). Cash no paga nada.
        if t == 0:
            out["hodl_equity"][0] = 1.0 - COST_R
            out["cash_equity"][0] = 1.0
        else:
            out["hodl_equity"][t] = out["hodl_equity"][t - 1] * (1 + ret[t])
            out["cash_equity"][t] = out["cash_equity"][t - 1] * (1 + CASH_D)

    acc = pd.DataFrame(out, index=sig.index)
    acc["drawdown"] = acc["equity"] / acc["equity"].cummax() - 1
    return acc


def compute_track_record_v21(precios, paper_start, price_source="",
                             code_sha="", generated_at_utc=""):
    """Orquesta capa 1 + capa 2. Determinista: mismos precios -> mismas filas."""
    sig = compute_signal(precios)
    sig = sig.iloc[max(LOOKBACKS):]                    # descarte de warmup POR POSICIÓN
    sig = sig[sig.index >= pd.Timestamp(paper_start)]  # la contabilidad arranca aquí

    acc = run_accounting(sig)
    df = pd.concat([sig, acc], axis=1)
    df["action"] = np.where(df["trade_pct"] > _EPS_ACTION, "COMPRAR",
                     np.where(df["trade_pct"] < -_EPS_ACTION, "VENDER", "MANTENER"))
    df["price_source"] = price_source
    df["code_sha"] = code_sha
    df["generated_at_utc"] = generated_at_utc
    df.index.name = "date"
    return df


# ============================================================================
# SERIALIZACIÓN
# ============================================================================
def _safe(value, ndigits):
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return ""
    return round(float(value), ndigits)


def df_to_rows_v21(tr):
    """DataFrame -> filas en el ORDEN EXACTO de COLUMNS_V21."""
    rows = []
    for date, r in tr.iterrows():
        row = [pd.Timestamp(date).strftime("%Y-%m-%d")]
        for col in COLUMNS_V21[1:]:
            if col in _ROUND:
                row.append(_safe(r[col], _ROUND[col]))
            else:
                row.append(str(r[col]))
        rows.append(row)
    return rows


def new_rows_v21(tr, existing_dates):
    """Filas cuya fecha no está ya en el sheet. Pura -> testeable sin gspread."""
    existing = set(existing_dates)
    return [row for row in df_to_rows_v21(tr) if row[0] not in existing]


def rows_mismatch(recomputed, sheet_rows):
    """
    Guarda de integridad (parte pura). Compara filas recomputadas contra las del
    sheet como STRINGS EXACTOS: el redondeo de _safe es determinista, así que la
    comparación exacta es válida y evita tolerancias flotantes.

    Devuelve lista de (fecha, columna, valor_sheet, valor_recomputado).
    Vacía = consistente. Política del caller: mismatch -> NO appendear, exit 1.
    """
    by_date = {r[0]: r for r in sheet_rows}
    diffs = []
    for row in recomputed:
        ref = by_date.get(row[0])
        if ref is None:
            continue                                    # fecha aún no escrita
        for i, col in enumerate(COLUMNS_V21):
            if str(ref[i]) != str(row[i]):
                diffs.append((row[0], col, str(ref[i]), str(row[i])))
    return diffs

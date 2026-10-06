"""Backtest framework for BTC trend strategies (v2.1 replica + V3 candidates)."""
import numpy as np, pandas as pd
ANN = 365
import os
HERE = os.path.dirname(os.path.abspath(__file__))
# Datos versionados en research/datos (CC BY-SA 4.0, ver LICENCIA-DATOS.md); data/ si se regeneran
DATA = os.path.join(HERE, "data", "btc_daily_bitstamp.csv")
if not os.path.exists(DATA):
    DATA = os.path.join(HERE, "datos", "btc_daily_bitstamp.csv")

def load_prices(end="2026-10-05"):
    d = pd.read_csv(DATA, index_col=0, parse_dates=True)
    return d.loc[:end, "close"].astype(float)

# ---------------------------------------------------------------- signals
def ewm_vol(px, span=30):
    return px.pct_change().ewm(span=span).std() * np.sqrt(ANN)

def v21_target(px, lookbacks=(20,60,120,250), target_vol=0.50, span=30, cap=1.0):
    trend = pd.concat([(px > px.shift(L)).astype(float) for L in lookbacks], axis=1).mean(axis=1)
    vs = (target_vol / ewm_vol(px, span)).clip(upper=cap)
    return (trend * vs).clip(0, cap).fillna(0.0), trend, vs

def band_held(target, band=0.10):
    held, out = 0.0, []
    for tw in target.values:
        if abs(tw - held) > band: held = tw
        out.append(held)
    return pd.Series(out, index=target.index)

def cont_trend(px, lookbacks=(20,60,120,250), span=30):
    """Continuous risk-adjusted momentum per lookback, mapped to [0,1] by normal CDF.
    z_L = log(P_t/P_{t-L}) / (sigma_daily * sqrt(L))  (Baz et al. 2015 style normalisation)."""
    from scipy.stats import norm
    sd = np.log(px).diff().ewm(span=span).std()
    zs = []
    for L in lookbacks:
        z = np.log(px / px.shift(L)) / (sd * np.sqrt(L))
        zs.append(pd.Series(norm.cdf(z.values), index=px.index).where(z.notna()))
    return pd.concat(zs, axis=1).mean(axis=1)

def hysteresis(score, enter, exit_):
    """Binary state: on when score >= enter, off when score <= exit_, else keep."""
    on, out = 0.0, []
    for s in score.values:
        if np.isnan(s): out.append(0.0); continue
        if on == 0.0 and s >= enter: on = 1.0
        elif on == 1.0 and s <= exit_: on = 0.0
        out.append(on)
    return pd.Series(out, index=score.index)

def donchian_ensemble(px, lookbacks=(20,60,120,250)):
    """Zarattini et al. style: per lookback, long when close breaks N-day high, flat when it breaks
    the trailing midpoint/low; here: long after close > max(prev N), exit when close < min(prev N/2)."""
    states = []
    for L in lookbacks:
        hi = px.shift(1).rolling(L).max(); lo = px.shift(1).rolling(max(L//2, 5)).min()
        on, out = 0.0, []
        for p, h, l in zip(px.values, hi.values, lo.values):
            if np.isnan(h): out.append(0.0); continue
            if on == 0.0 and p > h: on = 1.0
            elif on == 1.0 and p < l: on = 0.0
            out.append(on)
        states.append(pd.Series(out, index=px.index))
    return pd.concat(states, axis=1).mean(axis=1)

# ---------------------------------------------------------------- accounting
def simulate(px, target, cost=0.0015, cash_apy=0.0, rebalance="on_change", band=0.0,
             partial=False, start=None, end=None, exec_px=None):
    """Units/cash accounting (v2.1 §4). Equity starts 1.0 in cash on `start`.
    target[t] is decided at close t.
      exec_px=None -> traded at close t (registro teórico, igual que los motores).
      exec_px=Series -> traded LATER at exec_px[t] (p. ej. 05:00 UTC del día t+1).
        Orden cronológico: (1) cierre t: se marca el capital con las tenencias que
        había ANTES de operar; (2) después del cierre: se opera a exec_px[t].
        Si falta exec_px[t] en un día que debe operar, se lanza error (no se rellena).
        Horizonte: el capital final es el del CIERRE del último día. Una operación
        decidida ese cierre ocurriría después del horizonte y NO se ejecuta (ni su
        costo); así el valor final y el último costo corresponden al mismo instante.
    rebalance: 'on_change' | 'band' | 'daily' (ver versión anterior)."""
    sl = slice(start, end)
    p = px.loc[sl].values; tw = target.loc[sl].values
    idx = px.loc[sl].index; n = len(p)
    delayed = exec_px is not None
    ep = exec_px.reindex(idx).values if delayed else p
    cd = (1 + cash_apy) ** (1 / ANN) - 1
    units = 0.0; cash = 1.0
    eq = np.empty(n); w = np.empty(n); turn = np.zeros(n); costs = np.zeros(n)
    prev_t = 0.0
    for t in range(n):
        if t > 0: cash *= (1 + cd)
        if delayed:                                   # (1) marca al cierre, antes de operar
            eq[t] = units * p[t] + cash
            w[t] = units * p[t] / eq[t]
        mark = ep[t]
        tgt = tw[t]
        if delayed and t == n - 1:                    # fuera del horizonte de evaluación
            prev_t = tgt
            continue
        if rebalance == "on_change": do = (t == 0) or abs(tgt - prev_t) > 1e-12
        elif rebalance == "band":
            w_now = units * p[t] / (units * p[t] + cash)
            do = abs(tgt - w_now) > band
        else: do = True
        if do:
            if delayed and not np.isfinite(mark):
                raise ValueError(f"falta precio de ejecución el {idx[t].date()}")
            e_pre = units * mark + cash
            goal = tgt
            if rebalance == "band" and partial:
                w_pre = units * mark / e_pre
                goal = min(max(tgt + np.sign(w_pre - tgt) * band, 0.0), 1.0) if abs(tgt - w_pre) > band else w_pre
            dv = goal * e_pre - units * mark
            if abs(dv) > 1e-15:
                if dv > 0: dv = min(dv, cash / (1 + cost))
                c = abs(dv) * cost
                units += dv / mark; cash -= dv + c
                turn[t] = abs(dv) / e_pre; costs[t] = c / e_pre
        prev_t = tgt
        if not delayed:                               # registro teórico: marca después de operar al cierre
            eq[t] = units * p[t] + cash
            w[t] = units * p[t] / eq[t]
    return pd.DataFrame({"equity": eq, "weight": w, "turnover": turn, "cost": costs}, index=idx)

def hodl(px, start, end=None, cost=0.0015):
    p = px.loc[start:end]
    return (1 - cost) * p / p.iloc[0]

# ---------------------------------------------------------------- metrics
def metrics(eq, cash_apy=0.0):
    r = eq.pct_change().dropna()
    yrs = len(r) / ANN
    cagr = eq.iloc[-1] ** (1 / yrs) - 1
    vol = r.std() * np.sqrt(ANN)
    ex = r - ((1 + cash_apy) ** (1 / ANN) - 1)
    sharpe = ex.mean() / r.std() * np.sqrt(ANN) if r.std() > 0 else np.nan
    dd = eq / eq.cummax() - 1
    mdd = dd.min()
    calmar = cagr / abs(mdd) if mdd < 0 else np.nan
    down = r[r < 0].std() * np.sqrt(ANN)
    sortino = r.mean() * ANN / down if down > 0 else np.nan
    return dict(CAGR=cagr, Vol=vol, Sharpe=sharpe, Sortino=sortino, MaxDD=mdd, Calmar=calmar,
                Skew=r.skew(), Kurt=r.kurt(), Years=yrs, Final=eq.iloc[-1])

def summarize(res, cash_apy=0.0):
    m = metrics(res["equity"], cash_apy)
    yrs = m["Years"]
    m.update(Exposure=res["weight"].mean(), TurnoverPY=res["turnover"].sum() / yrs,
             TradesPY=(res["turnover"] > 1e-9).sum() / yrs, CostPY=res["cost"].sum() / yrs)
    return m

# ---------------------------------------------------------------- inference
def sharpe_se(r):
    """Lo (2002)/Mertens SE of the (per-period) Sharpe, with skew/kurt adjustment, annualised."""
    from scipy.stats import skew, kurtosis
    sr = r.mean() / r.std(); n = len(r); g3 = skew(r); g4 = kurtosis(r, fisher=False)
    se = np.sqrt((1 - g3 * sr + (g4 - 1) / 4 * sr ** 2) / (n - 1))
    return sr * np.sqrt(ANN), se * np.sqrt(ANN)

def deflated_sharpe(r, n_trials, sr_trials_var):
    """Bailey & López de Prado (2014). r: daily returns of the chosen strategy.
    sr_trials_var: variance of the (per-period, non-annualised) Sharpes across trials."""
    from scipy.stats import norm, skew, kurtosis
    sr = r.mean() / r.std(); n = len(r); g3 = skew(r); g4 = kurtosis(r, fisher=False)
    emc = 0.5772156649
    sr0 = np.sqrt(sr_trials_var) * ((1 - emc) * norm.ppf(1 - 1 / n_trials) + emc * norm.ppf(1 - 1 / (n_trials * np.e)))
    z = (sr - sr0) * np.sqrt(n - 1) / np.sqrt(1 - g3 * sr + (g4 - 1) / 4 * sr ** 2)
    return norm.cdf(z), sr0 * np.sqrt(ANN)

def stationary_bootstrap_idx(n, mean_block, rng):
    idx = np.empty(n, dtype=int); i = rng.integers(n)
    p = 1.0 / mean_block
    for t in range(n):
        idx[t] = i
        i = rng.integers(n) if rng.random() < p else (i + 1) % n
    return idx

def boot_sharpe_diff(ra, rb, B=2000, block=20, seed=0):
    """Paired stationary bootstrap (Politis-Romano 1994) of annualised Sharpe(a)-Sharpe(b)."""
    rng = np.random.default_rng(seed); a = ra.values; b = rb.values; n = len(a); out = np.empty(B)
    for k in range(B):
        ix = stationary_bootstrap_idx(n, block, rng)
        x, y = a[ix], b[ix]
        out[k] = (x.mean() / x.std() - y.mean() / y.std()) * np.sqrt(ANN)
    d = (a.mean() / a.std() - b.mean() / b.std()) * np.sqrt(ANN)
    return d, np.percentile(out, [2.5, 97.5]), (out <= 0).mean()

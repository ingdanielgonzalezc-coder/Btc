/* lib.js — lógica pura del dashboard (sin React). Testeable con `node`. */

export const DEFAULTS = { stableApy: 0.04, costBps: 7, band: 0.10 };
export const MIN_DAYS_ANNUALIZED = 180;
export const STALE_AFTER_DAYS = 2;
export const RETAIL_BPS = 40;

/* ------------------------------------------------------------------ números */
export function toNum(v) {
  if (typeof v === "number") return v;
  if (v == null || v === "") return NaN;
  let s = String(v).trim().replace(/\s/g, "");
  const hasComma = s.includes(","), hasDot = s.includes(".");
  if (hasComma && hasDot) {
    s = s.lastIndexOf(",") > s.lastIndexOf(".") ? s.replace(/\./g, "").replace(",", ".") : s.replace(/,/g, "");
  } else if (hasComma) {
    s = s.replace(",", ".");
  }
  const n = parseFloat(s);
  return Number.isNaN(n) ? NaN : n;
}

/* ------------------------------------------------------------------ fechas
   La pestaña v2.0 se escribe con USER_ENTERED: Sheets puede publicarla como
   6/6/2026 (es-CL), 6/15/2026 (en-US) o un número de serie. Se normaliza todo a
   YYYY-MM-DD. Para d/m vs m/d ambiguos se elige la lectura que deja la columna
   en orden cronológico (las filas se escriben en orden). */
const pad = (n) => String(n).padStart(2, "0");
const iso = (y, m, d) => `${y}-${pad(m)}-${pad(d)}`;

function serialToIso(n) {
  const ms = Date.UTC(1899, 11, 30) + Math.round(n) * 86400000;
  const d = new Date(ms);
  return iso(d.getUTCFullYear(), d.getUTCMonth() + 1, d.getUTCDate());
}

export function normalizeDates(raw) {
  const vals = raw.map((v) => String(v ?? "").trim());
  const slash = /^(\d{1,2})[/.-](\d{1,2})[/.-](\d{4})$/;
  const parse = (v, dayFirst) => {
    if (/^\d{4}-\d{2}-\d{2}/.test(v)) return v.slice(0, 10);
    if (/^\d{5}(\.\d+)?$/.test(v)) return serialToIso(parseFloat(v));
    const m = v.match(slash);
    if (!m) return null;
    const a = +m[1], b = +m[2], y = +m[3];
    const [d, mo] = dayFirst ? [a, b] : [b, a];
    if (mo < 1 || mo > 12 || d < 1 || d > 31) return null;
    return iso(y, mo, d);
  };
  const score = (arr) => {
    let ok = 0;
    for (let i = 1; i < arr.length; i++) if (arr[i] && arr[i - 1] && arr[i] > arr[i - 1]) ok++;
    return ok - arr.filter((x) => !x).length * 10;
  };
  const dm = vals.map((v) => parse(v, true));
  const md = vals.map((v) => parse(v, false));
  return score(dm) >= score(md) ? dm : md;
}

/* ------------------------------------------------------------------ pestañas */
export function detectKind(fields) {
  const f = new Set(fields || []);
  if (f.has("donchian_score")) return "v3";
  if (f.has("signal_weight")) return "v21";
  if (f.has("strat_equity")) return "v20";
  if (f.has("run_at_utc") && f.has("consistency")) return "meta";
  if (f.has("section") && f.has("key") && f.has("value")) return "levels";
  return "unknown";
}

const pick = (row, ...keys) => {
  for (const k of keys) if (row[k] != null && row[k] !== "") return row[k];
  return undefined;
};

export function parseTrack(rows, costBps = DEFAULTS.costBps) {
  const dates = normalizeDates(rows.map((r) => r.date));
  const clean = rows
    .map((r, i) => {
      const tradePct = toNum(r.trade_pct);
      const cost = toNum(r.trade_cost);
      const signal = toNum(pick(r, "signal_weight", "new_weight", "target_weight"));
      const real = toNum(pick(r, "weight_post"));
      return {
        date: dates[i],
        btc: toNum(r.btc_price),
        trend: toNum(pick(r, "trend_score", "donchian_score")),
        volScalar: toNum(r.vol_scalar),
        target: toNum(r.target_weight),
        signal,
        weightReal: Number.isFinite(real) ? real : signal,
        action: String(r.action || "").trim().toUpperCase(),
        tradePct,
        // v2.0 no tiene trade_cost: se estima con el mismo costo del motor
        tradeCost: Number.isFinite(cost) ? cost : (Number.isFinite(tradePct) ? Math.abs(tradePct) * costBps / 1e4 : 0),
        dailyRet: toNum(r.daily_return),
        strat: toNum(pick(r, "equity", "strat_equity")),
        hodl: toNum(r.hodl_equity),
        cash: toNum(r.cash_equity),
        dd: toNum(r.drawdown),
        source: String(pick(r, "price_source") || "").trim(),
        nextBuy: toNum(r.next_buy_above),
        nextSell: toNum(r.next_sell_below),
      };
    })
    .filter((r) => r.date && Number.isFinite(r.strat));
  const byDate = new Map();
  for (const r of clean) byDate.set(r.date, r);
  return [...byDate.values()]
    .sort((a, b) => (a.date < b.date ? -1 : a.date > b.date ? 1 : 0))
    .map((r) => ({ ...r, inMarket: r.weightReal > 1e-9 }));
}

export function parseMeta(rows) {
  return rows
    .filter((r) => r.run_at_utc)
    .map((r) => {
      const run = String(r.run_at_utc).trim();
      const lc = normalizeDates([r.last_candle])[0];
      const runMs = Date.parse(run.replace(" ", "T") + "Z");
      const expected = lc ? Date.parse(lc + "T00:00:00Z") + 86400000 : NaN;
      const cons = String(r.consistency || "");
      return {
        run, runMs, lastCandle: lc, sha: String(r.code_sha || ""),
        ok: cons.startsWith("OK"), consistency: cons,
        rowsAdded: toNum(r.rows_added), spot: toNum(r.spot_price),
        delayH: Number.isFinite(runMs) && Number.isFinite(expected) ? (runMs - expected) / 3600000 : NaN,
        note: String(r.note || ""),
      };
    })
    .filter((r) => Number.isFinite(r.runMs))
    .sort((a, b) => a.runMs - b.runMs);
}

export function parseLevels(rows) {
  const out = { meta: {}, v21: {}, v3: {} };
  for (const r of rows) {
    const s = String(r.section || "").trim(), k = String(r.key || "").trim();
    if (!out[s] || !k) continue;
    const n = toNum(r.value);
    out[s][k] = Number.isFinite(n) && !/^\d{4}-\d{2}-\d{2}/.test(String(r.value)) ? n : String(r.value ?? "");
  }
  return out.meta.date ? out : null;
}

export function assumptionsFrom(levels) {
  const m = levels?.meta || {};
  const has = Number.isFinite(m.stable_apy) && Number.isFinite(m.cost_bps);
  return {
    stableApy: has ? m.stable_apy : DEFAULTS.stableApy,
    costBps: has ? m.cost_bps : DEFAULTS.costBps,
    band: Number.isFinite(m.band) ? m.band : DEFAULTS.band,
    fromSheet: has,
  };
}

/* ------------------------------------------------------------------ métricas */
export function computeMetrics(data, stableApy = DEFAULTS.stableApy) {
  if (data.length < 2) return null;
  const cashD = Math.pow(1 + stableApy, 1 / 365) - 1;
  const first = data[0], last = data[data.length - 1];
  const days = Math.max(1, (Date.parse(last.date) - Date.parse(first.date)) / 86400000);
  const ex = [];
  for (let i = 1; i < data.length; i++) ex.push(data[i].strat / data[i - 1].strat - 1 - cashD);
  const mean = ex.reduce((a, b) => a + b, 0) / ex.length;
  const sd = Math.sqrt(ex.reduce((a, b) => a + (b - mean) ** 2, 0) / Math.max(1, ex.length - 1));
  const cagr = Math.pow(last.strat / first.strat, 365 / days) - 1;
  let pk = -Infinity, hodlMaxDD = 0, spk = -Infinity, maxDD = 0;
  for (const d of data) {
    pk = Math.max(pk, d.hodl); hodlMaxDD = Math.min(hodlMaxDD, d.hodl / pk - 1);
    spk = Math.max(spk, d.strat); maxDD = Math.min(maxDD, d.strat / spk - 1);
  }
  const enough = days >= MIN_DAYS_ANNUALIZED;
  const cashTotal = Number.isFinite(last.cash) && Number.isFinite(first.cash)
    ? last.cash / first.cash - 1 : Math.pow(1 + cashD, days) - 1;
  const totalStrat = last.strat / first.strat - 1;
  const trades = data.filter((d) => Math.abs(d.tradePct) > 1e-9).length;
  const turnover = data.reduce((a, d) => a + (Number.isFinite(d.tradePct) ? Math.abs(d.tradePct) : 0), 0);
  const costBps = data.reduce((a, d) => a + (d.tradeCost || 0), 0) * 1e4;
  return {
    cagr, maxDD, hodlMaxDD, enough, days: Math.round(days), n: data.length,
    sharpe: enough && sd > 1e-9 ? (mean / sd) * Math.sqrt(365) : null,
    calmar: enough && maxDD < -1e-6 ? cagr / Math.abs(maxDD) : null,
    totalStrat, totalHodl: last.hodl / first.hodl - 1, cashTotal,
    excessOverCash: totalStrat - cashTotal,
    inMarketShare: data.filter((d) => d.inMarket).length / data.length,
    trades, turnover, costBps, retailCostBps: turnover * RETAIL_BPS,
  };
}

export function withDrawdowns(data) {
  let ps = -Infinity, ph = -Infinity;
  return data.map((d) => {
    ps = Math.max(ps, d.strat); ph = Math.max(ph, d.hodl);
    return { ...d, ddStrat: d.strat / ps - 1, ddHodl: d.hodl / ph - 1 };
  });
}

export function daysBetween(a, b) {
  return Math.round((Date.parse(b) - Date.parse(a)) / 86400000);
}

export function daysStale(lastDate, now = new Date()) {
  if (!lastDate) return null;
  const today = Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate());
  // la última vela cerrada esperada es la de AYER
  return Math.floor((today - Date.parse(lastDate + "T00:00:00Z")) / 86400000) - 1;
}

/* ------------------------------------------------------------------ cono */
export function coneAt(cone, key, day) {
  if (!cone || !cone[key]) return null;
  const hs = cone.horizon_days, step = hs[1] - hs[0];
  const i = Math.min(hs.length - 2, Math.floor(day / step));
  if (day > hs[hs.length - 1]) return null;
  const f = (day - hs[i]) / step;
  const out = {};
  for (const p of cone.pcts) {
    const arr = cone[key][String(p)];
    out[p] = arr[i] + (arr[i + 1] - arr[i]) * f;
  }
  return out;
}

/* ------------------------------------------------------------------ comparación */
export function compareSeries(tracks) {
  // tracks: {v21: data, v3: data, v20: data}; rebasa todo al inicio común (el más tardío)
  const keys = Object.keys(tracks).filter((k) => tracks[k] && tracks[k].length >= 2);
  if (!keys.length) return { rows: [], start: null, keys: [] };
  const start = keys.map((k) => tracks[k][0].date).sort().at(-1);
  const maps = {}, base = {};
  for (const k of keys) {
    maps[k] = new Map(tracks[k].map((d) => [d.date, d]));
    const b = tracks[k].filter((d) => d.date <= start).at(-1);
    base[k] = b;
  }
  const ref = keys.map((k) => tracks[k]).sort((a, b) => b.length - a.length)[0];
  const dates = [...new Set(keys.flatMap((k) => tracks[k].map((d) => d.date)))].filter((d) => d >= start).sort();
  const hb = base[keys[0]];
  const rows = dates.map((date) => {
    const row = { date };
    for (const k of keys) {
      const d = maps[k].get(date);
      if (d && base[k]) row[k] = d.strat / base[k].strat;
      if (d && hb && row.hodl == null && Number.isFinite(d.btc)) row.hodl = d.btc / hb.btc;
    }
    return row;
  });
  return { rows, start, keys, ref };
}

/* ------------------------------------------------------------------ ejecución */
export function shortfall(meta, closeByDate) {
  const pts = meta
    .map((m) => {
      const close = closeByDate.get(m.lastCandle);
      if (!Number.isFinite(m.spot) || !Number.isFinite(close)) return null;
      return { run: m.run, date: m.lastCandle, gap: m.spot / close - 1, delayH: m.delayH };
    })
    .filter(Boolean);
  if (!pts.length) return null;
  const med = (a) => { const s = [...a].sort((x, y) => x - y); const n = s.length; return n % 2 ? s[(n - 1) / 2] : (s[n / 2 - 1] + s[n / 2]) / 2; };
  const q = (a, p) => { const s = [...a].sort((x, y) => x - y); return s[Math.min(s.length - 1, Math.floor(p * s.length))]; };
  const abs = pts.map((p) => Math.abs(p.gap)), dl = pts.map((p) => p.delayH).filter(Number.isFinite);
  return {
    pts, n: pts.length,
    medAbs: med(abs), p90Abs: q(abs, 0.9),
    mean: pts.reduce((a, p) => a + p.gap, 0) / pts.length,
    medDelay: dl.length ? med(dl) : NaN, maxDelay: dl.length ? Math.max(...dl) : NaN,
  };
}

/* ------------------------------------------------------------------ salud */
export function health(meta, track, now = new Date()) {
  if (!meta || !meta.length) return null;
  const last = meta.at(-1);
  const recent = meta.slice(-30);
  let streak = 0;
  for (let i = meta.length - 1; i >= 0 && meta[i].ok; i--) streak++;
  const lastRow = track && track.length ? track.at(-1).date : null;
  const hoursSince = (now.getTime() - last.runMs) / 3600000;
  let status = "ok";
  if (!last.ok) status = "fork";
  else if (hoursSince > 36 || (lastRow && daysStale(lastRow, now) > 1)) status = "late";
  return {
    status, last, streak, hoursSince, lastRow,
    staleDays: lastRow ? daysStale(lastRow, now) : null,
    recent, forks30: recent.filter((m) => !m.ok).length,
    medDelay: (() => { const d = recent.map((m) => m.delayH).filter(Number.isFinite).sort((a, b) => a - b); return d.length ? d[Math.floor(d.length / 2)] : NaN; })(),
  };
}

/* ------------------------------------------------------------------ precios de giro
   Escenarios para el cierre de mañana, suponiendo volatilidad sin cambio.
   v2.1: cada plazo vota arriba si P > ref; la señal cambia si |target − señal| > banda.
   V3:   canal encendido se apaga si P < exit; apagado se enciende si P > entry;
         opera si |target − peso real| > banda. */
function ladder(levels, outcomeAt) {
  const lv = [...new Set(levels.filter(Number.isFinite))].sort((a, b) => a - b);
  if (!lv.length) return [];
  const probes = [lv[0] * 0.97];
  for (let i = 0; i < lv.length - 1; i++) probes.push((lv[i] + lv[i + 1]) / 2);
  probes.push(lv.at(-1) * 1.03);
  const segs = probes.map((p, i) => ({ lo: i === 0 ? null : lv[i - 1], hi: i === lv.length ? null : lv[i], ...outcomeAt(p) }));
  const merged = [];
  for (const s of segs) {
    const prev = merged.at(-1);
    if (prev && prev.action === s.action && Math.abs(prev.weight - s.weight) < 1e-9) prev.hi = s.hi;
    else merged.push({ ...s });
  }
  return merged;
}

export function scenariosV21(L, band = DEFAULTS.band) {
  if (!L || !L.v21 || !Number.isFinite(L.v21.signal)) return null;
  const v = L.v21, keys = [20, 60, 120, 250].filter((n) => Number.isFinite(v[`L${n}_ref`]));
  const refs = keys.map((n) => v[`L${n}_ref`]);
  const vs = Number.isFinite(v.vol_scalar) ? v.vol_scalar : 1;
  const held = v.signal;
  const outcomeAt = (p) => {
    const votes = refs.filter((r) => p > r).length / refs.length;
    const target = Math.min(1, Math.max(0, votes * vs));
    const trade = Math.abs(target - held) > band;
    const weight = trade ? target : held;
    return { votes, target, weight, action: trade ? (target > held ? "COMPRAR" : "VENDER") : "MANTENER" };
  };
  return {
    price: L.meta.price, date: L.meta.date, current: held, vs,
    rows: ladder(refs, outcomeAt),
    detail: keys.map((n) => ({ n, state: v[`L${n}_state`] === 1, level: v[`L${n}_ref`] })),
  };
}

export function scenariosV3(L, weightReal, band = DEFAULTS.band) {
  if (!L || !L.v3 || !Number.isFinite(L.v3.score)) return null;
  const v = L.v3, ns = [20, 60, 120, 250].filter((n) => Number.isFinite(v[`L${n}_state`]));
  const vs = Number.isFinite(v.vol_scalar) ? v.vol_scalar : 1;
  const w = Number.isFinite(weightReal) ? weightReal : (Number.isFinite(v.weight) ? v.weight : v.target);
  const ch = ns.map((n) => ({ n, on: v[`L${n}_state`] === 1, entry: v[`L${n}_entry`], exit: v[`L${n}_exit`] }));
  const outcomeAt = (p) => {
    const score = ch.filter((c) => (c.on ? !(p < c.exit) : p > c.entry)).length / ch.length;
    const target = Math.min(1, Math.max(0, score * vs));
    const trade = Math.abs(target - w) > band;
    const weight = trade ? target : w;
    return { votes: score, target, weight, action: trade ? (target > w ? "COMPRAR" : "VENDER") : "MANTENER" };
  };
  return {
    price: L.meta.price, date: L.meta.date, current: w, vs, hypothetical: !Number.isFinite(weightReal) && !Number.isFinite(v.weight),
    rows: ladder(ch.map((c) => (c.on ? c.exit : c.entry)), outcomeAt),
    detail: ch.map((c) => ({ n: c.n, state: c.on, level: c.on ? c.exit : c.entry })),
  };
}

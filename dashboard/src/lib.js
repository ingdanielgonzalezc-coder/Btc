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
  if (f.has("exec_price") && f.has("version")) return "exec";
  if (f.has("votes_up") || f.has("donchian_score")) return "v3";
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
        // v2.0 no tiene trade_cost: se estima con el costo del motor, en unidades de
        // capital inicial (= |Δpeso| × capital × costo), igual que trade_cost de v2.1/V3
        tradeCost: Number.isFinite(cost) ? cost
          : (Number.isFinite(tradePct) ? Math.abs(tradePct) * toNum(pick(r, "equity", "strat_equity")) * costBps / 1e4 : 0),
        dailyRet: toNum(r.daily_return),
        strat: toNum(pick(r, "equity", "strat_equity")),
        hodl: toNum(r.hodl_equity),
        cash: toNum(r.cash_equity),
        dd: toNum(r.drawdown),
        source: String(pick(r, "price_source") || "").trim(),
        live: r.live == null || r.live === "" ? null : toNum(r.live) === 1,
      };
    })
    .filter((r) => r.date && Number.isFinite(r.strat));
  const byDate = new Map();
  for (const r of clean) byDate.set(r.date, r);
  return [...byDate.values()]
    .sort((a, b) => (a.date < b.date ? -1 : a.date > b.date ? 1 : 0))
    .map((r) => ({ ...r, inMarket: r.weightReal > 1e-9 }));
}

/* Registro de ejecución atrasada: una pestaña con v2.1 y V3 (columna version).
   Se normaliza al mismo formato de registro: capital marcado al cierre, antes de operar. */
export function parseExec(rows) {
  const out = {};
  for (const v of ["v21", "v3"]) {
    const rs = rows.filter((r) => String(r.version).trim() === v);
    if (!rs.length) continue;
    const dates = normalizeDates(rs.map((r) => r.date));
    out[`${v}x`] = rs.map((r, i) => ({
      date: dates[i], btc: toNum(r.btc_close), strat: toNum(r.equity_close), hodl: toNum(r.hodl_close), cash: NaN,
      tradePct: toNum(r.trade_pct), tradeCost: toNum(r.trade_cost) || 0, weightReal: toNum(r.weight_close),
      signal: toNum(r.target_weight), target: toNum(r.target_weight), execPrice: toNum(r.exec_price),
      live: r.live == null || r.live === "" ? null : toNum(r.live) === 1, action: "", trend: NaN, volScalar: NaN,
    })).filter((d) => d.date && Number.isFinite(d.strat)).sort((a, b) => (a.date < b.date ? -1 : 1))
      .map((d) => ({ ...d, inMarket: d.weightReal > 1e-9 }));
  }
  return out;
}

/* Brecha entre el registro teórico (opera al cierre) y el de ejecución atrasada,
   en la última fecha común. Negativo = ejecutar tarde costó capital. */
export function execGap(theo, late) {
  if (!theo?.length || !late?.length) return null;
  const m = new Map(theo.map((d) => [d.date, d]));
  const last = [...late].reverse().find((d) => m.has(d.date));
  if (!last) return null;
  const t = m.get(last.date);
  return { date: last.date, theo: t.strat, late: last.strat, gap: last.strat / t.strat - 1 };
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
/* base: "account" = la cuenta nace con capital 1,0 en cash (v2.1, V3, v2.0), así el
   costo de la primera compra cuenta; "first" = rebasar en la primera fila (para un
   tramo, p. ej. "solo en vivo", donde la primera fila es el día anterior al tramo). */
export function computeMetrics(data, stableApy = DEFAULTS.stableApy, costBps = DEFAULTS.costBps, base = "account") {
  if (data.length < 2) return null;
  const cashD = Math.pow(1 + stableApy, 1 / 365) - 1;
  const first = data[0], last = data[data.length - 1];
  const b = base === "account" ? { strat: 1, hodl: 1, cash: 1 } : { strat: first.strat, hodl: first.hodl, cash: first.cash };
  const days = Math.max(1, (Date.parse(last.date) - Date.parse(first.date)) / 86400000);
  const ex = [];
  let prev = b.strat;
  for (let i = base === "account" ? 0 : 1; i < data.length; i++) { ex.push(data[i].strat / prev - 1 - cashD); prev = data[i].strat; }
  const mean = ex.reduce((a, x) => a + x, 0) / ex.length;
  const sd = Math.sqrt(ex.reduce((a, x) => a + (x - mean) ** 2, 0) / Math.max(1, ex.length - 1));
  const totalStrat = last.strat / b.strat - 1;
  const totalHodl = last.hodl / b.hodl - 1;
  const cagr = Math.pow(1 + totalStrat, 365 / days) - 1;
  let pk = b.strat, maxDD = 0, ph = b.hodl, hodlMaxDD = 0;
  for (const d of data) {
    pk = Math.max(pk, d.strat); maxDD = Math.min(maxDD, d.strat / pk - 1);
    ph = Math.max(ph, d.hodl); hodlMaxDD = Math.min(hodlMaxDD, d.hodl / ph - 1);
  }
  const enough = days >= MIN_DAYS_ANNUALIZED;
  const cashTotal = Number.isFinite(last.cash) && Number.isFinite(b.cash)
    ? last.cash / b.cash - 1 : Math.pow(1 + cashD, days) - 1;
  const rows = base === "account" ? data : data.slice(1);
  const trades = rows.filter((d) => Math.abs(d.tradePct) > 1e-9).length;
  const turnover = rows.reduce((a, d) => a + (Number.isFinite(d.tradePct) ? Math.abs(d.tradePct) : 0), 0);
  // costo en pb del capital INICIAL del tramo; el escenario retail escala el mismo monto
  const costBp = rows.reduce((a, d) => a + (d.tradeCost || 0), 0) / b.strat * 1e4;
  return {
    cagr, maxDD, hodlMaxDD, enough, days: Math.round(days), n: data.length,
    sharpe: enough && sd > 1e-9 ? (mean / sd) * Math.sqrt(365) : null,
    calmar: enough && maxDD < -1e-6 ? cagr / Math.abs(maxDD) : null,
    totalStrat, totalHodl, cashTotal,
    excessOverCash: totalStrat - cashTotal,
    vsHodl: (1 + totalStrat) / (1 + totalHodl) - 1,
    inMarketShare: rows.filter((d) => d.inMarket).length / rows.length,
    avgExposure: rows.reduce((a, d) => a + (Number.isFinite(d.weightReal) ? d.weightReal : 0), 0) / rows.length,
    trades, turnover, costBps: costBp, retailCostBps: costBp * RETAIL_BPS / costBps,
  };
}

/* Tramo "solo en vivo": desde el día anterior a la primera fila live (base) hasta el final. */
export function liveSlice(data) {
  if (!data?.length || data[0].live == null) return null;
  const i = data.findIndex((d) => d.live);
  if (i < 0) return [];
  return data.slice(Math.max(0, i - 1));
}

/* base "account": la cuenta nace en 1,0 (el costo de entrada es caída); "first": tramo. */
export function withDrawdowns(data, base = "account") {
  let ps = base === "account" ? 1 : -Infinity, ph = base === "account" ? 1 : -Infinity;
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
export function compareSeries(tracksIn, fromDate = null) {
  // tracks: {v21: data, v3: data, v20: data}; rebasa todo al inicio común (el más tardío).
  // fromDate: recorta todas las series desde esa fecha (p. ej. la base del tramo en vivo).
  const tracks = Object.fromEntries(Object.entries(tracksIn).map(([k, v]) => [k, fromDate && v ? v.filter((d) => d.date >= fromDate) : v]));
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
/* Brecha de ejecución de UNA versión: su registro (cierres y operaciones) y sus corridas.
   - Mercado: una observación por vela, la primera corrida válida (OK) de ese día.
   - Operaciones: cada operación del registro se vincula con la corrida que la ESCRIBIÓ
     (OK, rows_added ≥ 1, last_candle = fecha). Las filas escritas después por gap-fill o
     reconstrucción no tienen corrida propia y quedan fuera (se informan aparte). */
export function shortfall(meta, track) {
  if (!meta?.length || !track?.length) return null;
  const byDate = new Map(track.map((d) => [d.date, d]));
  const firstOk = new Map(), writer = new Map();
  for (const m of meta) {                                   // meta viene ordenado por runMs
    if (!m.ok || !Number.isFinite(m.spot) || !m.lastCandle) continue;
    if (!firstOk.has(m.lastCandle)) firstOk.set(m.lastCandle, m);
    if (m.rowsAdded >= 1 && !writer.has(m.lastCandle)) writer.set(m.lastCandle, m);
  }
  const pts = [...firstOk.values()].map((m) => {
    const d = byDate.get(m.lastCandle);
    return d && Number.isFinite(d.btc) ? { run: m.run, date: m.lastCandle, gap: m.spot / d.btc - 1, delayH: m.delayH, trade: null } : null;
  }).filter(Boolean);
  const tradeRows = track.filter((d) => Number.isFinite(d.tradePct) && Math.abs(d.tradePct) > 1e-9);
  const tr = [];
  let unmatched = 0;
  for (const d of tradeRows) {
    const m = writer.get(d.date);
    if (!m) { unmatched++; continue; }
    const gap = m.spot / d.btc - 1, side = Math.sign(d.tradePct);
    tr.push({ run: m.run, date: d.date, gap, delayH: m.delayH, trade: d.tradePct, side, costPct: side * gap, impact: side * gap * Math.abs(d.tradePct) });
  }
  const tradeDates = new Set(tr.map((t) => t.date));
  for (const p of pts) if (tradeDates.has(p.date)) p.trade = true;   // el punto de mercado ya está como operación
  if (!pts.length && !tr.length) return null;
  const med = (a) => { const x = [...a].sort((u, v) => u - v); const n = x.length; return !n ? NaN : n % 2 ? x[(n - 1) / 2] : (x[n / 2 - 1] + x[n / 2]) / 2; };
  const q = (a, p) => { const x = [...a].sort((u, v) => u - v); return x.length ? x[Math.min(x.length - 1, Math.floor(p * x.length))] : NaN; };
  const abs = pts.map((p) => Math.abs(p.gap)), dl = pts.map((p) => p.delayH).filter(Number.isFinite);
  return {
    pts: pts.filter((p) => !p.trade), n: pts.length,
    medAbs: med(abs), p90Abs: q(abs, 0.9),
    mean: pts.length ? pts.reduce((a, p) => a + p.gap, 0) / pts.length : NaN,
    medDelay: med(dl), maxDelay: dl.length ? Math.max(...dl) : NaN,
    trades: tr, nTrades: tr.length, nTradeRows: tradeRows.length, unmatched,
    tradeMeanCost: tr.length ? tr.reduce((a, p) => a + p.costPct, 0) / tr.length : NaN,
    tradeImpactBps: tr.reduce((a, p) => a + p.impact, 0) * 1e4,
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
    if (prev && prev.action === s.action && Math.abs(prev.weight - s.weight) < 1e-9) { prev.hi = s.hi; prev.votesHi = s.votes; }
    else merged.push({ ...s, votesHi: s.votes });
  }
  return merged;
}

export function scenariosV21(L, weightReal, band = DEFAULTS.band) {
  if (!L || !L.v21 || !Number.isFinite(L.v21.signal)) return null;
  const v = L.v21, keys = [20, 60, 120, 250].filter((n) => Number.isFinite(v[`L${n}_ref`]));
  const refs = keys.map((n) => v[`L${n}_ref`]);
  const vs = Number.isFinite(v.vol_scalar) ? v.vol_scalar : 1;
  const held = v.signal;                                    // dispara: cambio de SEÑAL > banda
  const real = Number.isFinite(weightReal) ? weightReal : held; // sentido: contra la posición REAL
  const outcomeAt = (p) => {
    const votes = refs.filter((r) => p > r).length / refs.length;
    const target = Math.min(1, Math.max(0, votes * vs));
    const trade = Math.abs(target - held) > band;
    const weight = trade ? target : real;
    const action = !trade || Math.abs(target - real) < 1e-9 ? "MANTENER" : (target > real ? "COMPRAR" : "VENDER");
    return { votes, target, weight, action };
  };
  return {
    price: L.meta.price, date: L.meta.date, current: held, vs,
    rows: ladder(refs, outcomeAt),
    detail: keys.map((n) => ({ n, state: v[`L${n}_state`] === 1, level: v[`L${n}_ref`] })),
  };
}

export function scenariosV3(L) {
  // V3 todo/nada: 100% si al menos min_votes plazos quedan al alza; si no, 0%.
  if (!L || !L.v3 || !Number.isFinite(L.v3.target)) return null;
  const v = L.v3, keys = [20, 60, 120, 250].filter((n) => Number.isFinite(v[`L${n}_ref`]));
  const refs = keys.map((n) => v[`L${n}_ref`]);
  const need = Number.isFinite(v.min_votes) ? v.min_votes : 3;
  const held = v.target;
  const outcomeAt = (p) => {
    const up = refs.filter((r) => p > r).length;
    const target = up >= need ? 1 : 0;
    return { votes: up / refs.length, target, weight: target, action: target === held ? "MANTENER" : (target > held ? "COMPRAR" : "VENDER") };
  };
  return {
    price: L.meta.price, date: L.meta.date, current: held, vs: 1, need,
    rows: ladder(refs, outcomeAt),
    detail: keys.map((n) => ({ n, state: v[`L${n}_state`] === 1, level: v[`L${n}_ref`] })),
  };
}

/* Primera fecha registrada en vivo (las anteriores se reconstruyeron). */
export function firstLiveDate(data) {
  if (!data || !data.length || data[0].live == null) return null;
  const d = data.find((r) => r.live);
  return d && d !== data[0] ? d.date : null;
}

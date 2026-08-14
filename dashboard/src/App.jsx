import React, { useState, useMemo, useEffect } from "react";
import Papa from "papaparse";
import {
  ResponsiveContainer, LineChart, Line, AreaChart, Area,
  XAxis, YAxis, CartesianGrid, Tooltip, ReferenceArea,
} from "recharts";

/* CSV publicado del Google Sheet. En Vercel se define como variable de entorno
   VITE_CSV_URL; en local puedes usar un archivo .env (ver .env.example).
   Apuntar a la pestaña track_record_v21 (cada pestaña tiene su propio gid). */
const ENV_URL = import.meta.env.VITE_CSV_URL || "";

/* Supuestos del motor, declarados aquí para poder mostrarlos en pantalla.
   NO son observaciones: el cash al 4% y los 7 bps por unidad de turnover son
   hipótesis del backtest. Un tercero escéptico ataca justo ahí. */
const STABLE_APY = 0.04;
const CASH_D = Math.pow(1 + STABLE_APY, 1 / 365) - 1;
const COST_BPS = 7;

/* Sharpe y Calmar anualizados sobre muestras chicas son ruido: con 39 retornos
   el Calmar daba 19. Se ocultan hasta tener muestra suficiente. */
const MIN_DAYS_ANNUALIZED = 180;

/* Días sin fila nueva antes de marcar el dato como viejo. */
const STALE_AFTER_DAYS = 2;

/* ------------------------------------------------------------------ *
 *  Helpers
 * ------------------------------------------------------------------ */
function toNum(v) {
  if (typeof v === "number") return v;
  if (v == null || v === "") return NaN;
  let s = String(v).trim().replace(/\s/g, "");
  const hasComma = s.includes(","), hasDot = s.includes(".");
  if (hasComma && hasDot) {
    s = s.lastIndexOf(",") > s.lastIndexOf(".")
      ? s.replace(/\./g, "").replace(",", ".")
      : s.replace(/,/g, "");
  } else if (hasComma) {
    s = s.replace(",", ".");
  }
  const n = parseFloat(s);
  return Number.isNaN(n) ? NaN : n;
}

const pct = (x, d = 1) => (x == null || Number.isNaN(x) ? "—" : `${(x * 100).toFixed(d)}%`);
const num = (x, d = 2) => (x == null || Number.isNaN(x) ? "—" : x.toLocaleString("en-US", { minimumFractionDigits: d, maximumFractionDigits: d }));
const money = (x) => (x == null || Number.isNaN(x) ? "—" : "$" + x.toLocaleString("en-US", { maximumFractionDigits: 0 }));

/* Lee v2.1 (equity / signal_weight / cash_equity) y v2.0 (strat_equity /
   new_weight) con el mismo código, para poder comparar ambos registros. */
function pick(row, ...keys) {
  for (const k of keys) if (row[k] != null && row[k] !== "") return row[k];
  return undefined;
}

function parseRows(rows) {
  const clean = rows
    .filter((r) => r.date)
    .map((r) => {
      const weightSignal = toNum(pick(r, "signal_weight", "new_weight"));
      const weightReal = toNum(pick(r, "weight_post"));
      return {
        date: String(r.date).trim(),
        btc: toNum(r.btc_price),
        trend: toNum(r.trend_score),
        volScalar: toNum(r.vol_scalar),
        target: toNum(r.target_weight),
        weight: weightSignal,
        // v2.1 expone el peso REAL (deriva con el precio); v2.0 solo el teórico
        weightReal: Number.isFinite(weightReal) ? weightReal : weightSignal,
        action: String(r.action || "").trim().toUpperCase(),
        tradePct: toNum(r.trade_pct),
        dailyRet: toNum(r.daily_return),
        strat: toNum(pick(r, "equity", "strat_equity")),
        hodl: toNum(r.hodl_equity),
        cash: toNum(pick(r, "cash_equity")),
        dd: toNum(r.drawdown),
        source: String(pick(r, "price_source") || "").trim(),
      };
    })
    .filter((r) => Number.isFinite(r.strat));

  /* FIX CRÍTICO. El gap-fill del motor appendea la fecha faltante al FINAL del
     Sheet, así que el orden de llegada no es cronológico. computeMetrics y
     marketSpans asumen data[0] = inicio y data[n-1] = fin: sin ordenar, un solo
     hueco rellenado corrompe CAGR, retorno total, spans y gráficos.
     Se ordena y se deduplica por fecha (gana la última aparición). */
  const byDate = new Map();
  for (const r of clean) byDate.set(r.date, r);
  return [...byDate.values()]
    .sort((a, b) => (a.date < b.date ? -1 : a.date > b.date ? 1 : 0))
    .map((r) => ({ ...r, inMarket: r.weightReal > 1e-9 }));
}

function computeMetrics(data) {
  if (data.length < 2) return null;
  const first = data[0], last = data[data.length - 1];
  const days = Math.max(1, (new Date(last.date) - new Date(first.date)) / 86400000);

  const stratRets = [];
  for (let i = 1; i < data.length; i++) stratRets.push(data[i].strat / data[i - 1].strat - 1);

  /* Sharpe EN EXCESO sobre el cash. Sin restarlo, en régimen defensivo el
     numerador es el APY asumido y el denominador es ruido de los pocos días
     con exposición: el número deja de significar algo (daba 6.60 cuando el
     exceso real era -4.75). */
  const excess = stratRets.map((r) => r - CASH_D);
  const mean = excess.reduce((a, b) => a + b, 0) / excess.length;
  const variance = excess.reduce((a, b) => a + (b - mean) ** 2, 0) / Math.max(1, excess.length - 1);
  const std = Math.sqrt(variance);

  const cagr = Math.pow(last.strat / first.strat, 365 / days) - 1;
  const hodlCagr = Math.pow(last.hodl / first.hodl, 365 / days) - 1;
  const maxDD = Math.min(0, ...data.map((d) => d.dd));

  // Drawdown de HODL en O(n) con peak acumulado (antes era O(n²)).
  let peak = -Infinity, hodlMaxDD = 0;
  for (const d of data) {
    peak = Math.max(peak, d.hodl);
    hodlMaxDD = Math.min(hodlMaxDD, d.hodl / peak - 1);
  }

  const inMarketShare = data.filter((d) => d.inMarket).length / data.length;
  const enoughSample = days >= MIN_DAYS_ANNUALIZED;

  /* Retorno del cash: preferir la columna del motor (v2.1); si no está,
     reconstruirlo con el mismo APY asumido. */
  const cashTotal = Number.isFinite(last.cash) && Number.isFinite(first.cash)
    ? last.cash / first.cash - 1
    : Math.pow(1 + CASH_D, days) - 1;
  const totalStrat = last.strat / first.strat - 1;

  return {
    cagr, hodlCagr, maxDD, hodlMaxDD, inMarketShare, enoughSample,
    sharpe: enoughSample && std > 1e-9 ? (mean / std) * Math.sqrt(365) : null,
    calmar: enoughSample && maxDD < -1e-6 ? cagr / Math.abs(maxDD) : null,
    totalStrat,
    totalHodl: last.hodl / first.hodl - 1,
    cashTotal,
    // Lo que aportó realmente operar, contra no haber hecho nada.
    excessOverCash: totalStrat - cashTotal,
    days: Math.round(days), n: data.length,
  };
}

function marketSpans(data) {
  const spans = [];
  let start = null;
  for (let i = 0; i < data.length; i++) {
    if (data[i].inMarket && start === null) start = data[i].date;
    if ((!data[i].inMarket || i === data.length - 1) && start !== null) {
      spans.push([start, data[i].inMarket ? data[i].date : data[i - 1].date]);
      start = null;
    }
  }
  return spans;
}

/* Días desde la última fila. Una herramienta de decisión debe decir si el dato
   que muestra sigue vigente. */
function daysStale(lastDate) {
  if (!lastDate) return null;
  const then = new Date(lastDate + "T00:00:00Z");
  const today = new Date();
  const utcToday = Date.UTC(today.getUTCFullYear(), today.getUTCMonth(), today.getUTCDate());
  return Math.floor((utcToday - then.getTime()) / 86400000);
}

/* ------------------------------------------------------------------ *
 *  Styles
 * ------------------------------------------------------------------ */
const STYLES = `
@import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;700&family=IBM+Plex+Mono:wght@400;500;600&display=swap');
.btcd { --ink:#0E1320; --panel:#151B2B; --panel2:#1B2336; --line:#28324d;
  --text:#E7EBF3; --muted:#8B95AB; --gold:#E8B33B; --steel:#6FB3D6;
  --buy:#54B98A; --sell:#D98B6A; --hold:#8B95AB;
  background:var(--ink); color:var(--text); min-height:100vh;
  font-family:'IBM Plex Mono',ui-monospace,monospace; padding:20px; max-width:1100px; margin:0 auto; }
.btcd * { box-sizing:border-box; }
.btcd .display { font-family:'Space Grotesk',sans-serif; }
.btcd .eyebrow { font-size:11px; letter-spacing:.18em; text-transform:uppercase; color:var(--muted); }
.btcd .panel { background:var(--panel); border:1px solid var(--line); border-radius:10px; }
.btcd .grid { display:grid; gap:14px; }
.btcd .metric-val { font-family:'Space Grotesk',sans-serif; font-weight:700; }
.btcd input { font-family:'IBM Plex Mono',monospace; }
.btcd .tick { font-size:11px; fill:var(--muted); }
.btcd button:focus-visible, .btcd input:focus-visible { outline:2px solid var(--gold); outline-offset:1px; }
@media (max-width:720px){ .btcd { padding:12px; } }
`;

function StatusBadge({ inMarket }) {
  return (
    <span style={{
      fontSize: 12, fontWeight: 600, letterSpacing: ".08em", padding: "5px 12px",
      borderRadius: 999, border: `1px solid ${inMarket ? "var(--gold)" : "var(--line)"}`,
      color: inMarket ? "var(--gold)" : "var(--muted)",
      background: inMarket ? "rgba(232,179,59,.10)" : "transparent",
    }}>
      ● {inMarket ? "IN MARKET" : "IN CASH"}
    </span>
  );
}

function StaleBadge({ stale }) {
  if (stale == null || stale <= STALE_AFTER_DAYS) return null;
  return (
    <span style={{
      fontSize: 11, fontWeight: 600, letterSpacing: ".08em", padding: "4px 10px",
      borderRadius: 999, border: "1px solid var(--sell)", color: "var(--sell)",
      background: "rgba(217,139,106,.10)", marginLeft: 8,
    }}>
      ● STALE · {stale}d
    </span>
  );
}

function WeightGauge({ weight }) {
  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", fontSize: 11, color: "var(--muted)" }}>
        <span>POSITION</span><span>{pct(weight, 0)} BTC</span>
      </div>
      <div style={{ height: 8, background: "var(--panel2)", borderRadius: 6, marginTop: 6, overflow: "hidden" }}>
        <div style={{ width: `${Math.min(100, Math.max(0, weight * 100))}%`, height: "100%",
          background: "linear-gradient(90deg,#E8B33B,#f0c463)", borderRadius: 6 }} />
      </div>
    </div>
  );
}

function Metric({ label, value, sub, accent }) {
  return (
    <div className="panel" style={{ padding: "14px 16px" }}>
      <div className="eyebrow">{label}</div>
      <div className="metric-val" style={{ fontSize: 26, marginTop: 6, color: accent || "var(--text)" }}>{value}</div>
      {sub && <div style={{ fontSize: 11, color: "var(--muted)", marginTop: 2 }}>{sub}</div>}
    </div>
  );
}

const actionColor = (a) => a === "COMPRAR" ? "var(--buy)" : a === "VENDER" ? "var(--sell)" : "var(--hold)";
const actionLabel = (a) => a === "COMPRAR" ? "BUY" : a === "VENDER" ? "SELL" : "HOLD";

function ChartTooltip({ active, payload, label }) {
  if (!active || !payload || !payload.length) return null;
  const p = payload[0].payload;
  return (
    <div style={{ background: "var(--panel2)", border: "1px solid var(--line)", borderRadius: 8, padding: "8px 11px", fontSize: 12 }}>
      <div style={{ color: "var(--muted)", marginBottom: 4 }}>{label}</div>
      <div style={{ color: "var(--gold)" }}>Strategy &nbsp;{num(p.strat, 4)}×</div>
      <div style={{ color: "var(--steel)" }}>Buy &amp; hold &nbsp;{num(p.hodl, 4)}×</div>
      {Number.isFinite(p.cash) && <div style={{ color: "var(--muted)" }}>Cash &nbsp;{num(p.cash, 4)}×</div>}
      <div style={{ color: "var(--muted)", marginTop: 4 }}>{p.inMarket ? `in market · ${pct(p.weightReal, 0)}` : "in cash"} · {money(p.btc)}</div>
    </div>
  );
}

/* ------------------------------------------------------------------ *
 *  App
 * ------------------------------------------------------------------ */
export default function App() {
  const [url, setUrl] = useState(ENV_URL);
  /* Arranca VACÍO, no con demo. Un dashboard que decide posiciones no puede
     mostrar datos sintéticos como si fueran el registro: si el CSV falla, la
     pantalla lo dice en vez de rellenar. El demo sigue disponible a mano. */
  const [rows, setRows] = useState([]);
  const [source, setSource] = useState("empty");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [logScale, setLogScale] = useState(true);

  const data = useMemo(() => parseRows(rows), [rows]);
  const metrics = useMemo(() => computeMetrics(data), [data]);
  const spans = useMemo(() => marketSpans(data), [data]);
  const last = data[data.length - 1];
  const stale = useMemo(() => (source === "live" && last ? daysStale(last.date) : null), [source, last]);

  async function loadUrl(target) {
    const u = (target || "").trim();
    if (!u) { setError("Pega el link CSV publicado de tu Google Sheet."); return; }
    setLoading(true); setError("");
    try {
      const res = await fetch(u);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const text = await res.text();
      const parsed = Papa.parse(text, { header: true, skipEmptyLines: true });
      const clean = parseRows(parsed.data);
      if (!clean.length) throw new Error("No encontré filas válidas. ¿Es el CSV de la pestaña track_record_v21?");
      setRows(parsed.data); setSource("live");
    } catch (e) {
      /* No se conserva lo anterior ni se cae a demo: se vacía y se explica. */
      setRows([]); setSource("empty");
      setError(`No pude cargar el CSV (${e.message}). Revisa que la pestaña esté publicada.`);
    } finally { setLoading(false); }
  }

  // Auto-carga si VITE_CSV_URL está definida
  useEffect(() => { if (ENV_URL) loadUrl(ENV_URL); /* eslint-disable-next-line */ }, []);

  const dateTicks = useMemo(() => {
    if (data.length <= 6) return data.map((d) => d.date);
    const step = Math.ceil(data.length / 6);
    return data.filter((_, i) => i % step === 0).map((d) => d.date);
  }, [data]);

  const hasCash = data.some((d) => Number.isFinite(d.cash));

  return (
    <div className="btcd">
      <style>{STYLES}</style>

      <div style={{ display: "flex", flexWrap: "wrap", justifyContent: "space-between", alignItems: "flex-end", gap: 12, marginBottom: 18 }}>
        <div>
          <div className="eyebrow">trend-following · volatility-targeting · paper</div>
          <h1 className="display" style={{ fontSize: 30, fontWeight: 700, margin: "4px 0 0", letterSpacing: "-.01em" }}>
            BTC Paper Trading
          </h1>
        </div>
        <div style={{ textAlign: "right" }}>
          {last && <StatusBadge inMarket={last.inMarket} />}
          <StaleBadge stale={stale} />
          <div style={{ fontSize: 11, color: "var(--muted)", marginTop: 6 }}>
            {source === "live" ? "live" : source === "demo" ? "demo data" : "no data"}
            {last ? ` · last ${last.date}` : ""}
            {last && last.source ? ` · ${last.source}` : ""}
          </div>
        </div>
      </div>

      <div className="panel" style={{ padding: 12, marginBottom: 14, display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" }}>
        <input
          value={url} onChange={(e) => setUrl(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && loadUrl(url)}
          placeholder="https://docs.google.com/…/pub?output=csv"
          style={{ flex: "1 1 320px", background: "var(--ink)", border: "1px solid var(--line)", borderRadius: 7,
            color: "var(--text)", padding: "9px 12px", fontSize: 13, outline: "none" }}
        />
        <button onClick={() => loadUrl(url)} disabled={loading}
          style={{ background: "var(--gold)", color: "#1a1407", border: "none", borderRadius: 7,
            padding: "9px 18px", fontWeight: 600, cursor: "pointer", fontSize: 13 }}>
          {loading ? "Loading…" : "Load"}
        </button>
      </div>
      {error && <div style={{ color: "var(--sell)", fontSize: 12, marginBottom: 14 }}>{error}</div>}

      {!last && !loading && (
        <div className="panel" style={{ padding: "36px 20px", textAlign: "center", marginBottom: 14 }}>
          <div className="display" style={{ fontSize: 17, fontWeight: 500 }}>No hay datos cargados</div>
          <div style={{ fontSize: 12, color: "var(--muted)", marginTop: 8, lineHeight: 1.7 }}>
            Pega arriba el CSV publicado de la pestaña <code>track_record_v21</code>.<br />
            Si el registro aún no tiene filas, aparecerán al cerrar la primera vela.
          </div>
        </div>
      )}

      {last && (
        <div className="grid" style={{ gridTemplateColumns: "repeat(auto-fit,minmax(150px,1fr))", marginBottom: 14 }}>
          <div className="panel" style={{ padding: "14px 16px" }}>
            <div className="eyebrow">BTC price</div>
            <div className="metric-val" style={{ fontSize: 24, marginTop: 6 }}>{money(last.btc)}</div>
            <div style={{ fontSize: 11, color: last.dailyRet >= 0 ? "var(--buy)" : "var(--sell)", marginTop: 2 }}>
              {last.dailyRet >= 0 ? "▲" : "▼"} {pct(Math.abs(last.dailyRet), 2)} today
            </div>
          </div>
          <div className="panel" style={{ padding: "14px 16px" }}>
            <div className="eyebrow">Today's call</div>
            <div className="metric-val" style={{ fontSize: 24, marginTop: 6, color: actionColor(last.action) }}>
              {actionLabel(last.action)}
            </div>
            <div style={{ fontSize: 11, color: "var(--muted)", marginTop: 2 }}>target {pct(last.target, 0)}</div>
          </div>
          <div className="panel" style={{ padding: "14px 16px", display: "flex", flexDirection: "column", justifyContent: "center" }}>
            <WeightGauge weight={last.weightReal} />
          </div>
          <div className="panel" style={{ padding: "14px 16px" }}>
            <div className="eyebrow">Signal</div>
            <div style={{ fontSize: 13, marginTop: 8, lineHeight: 1.7 }}>
              <div>trend <span style={{ color: "var(--gold)" }}>{num(last.trend, 2)}</span></div>
              <div>vol scalar <span style={{ color: "var(--steel)" }}>{num(last.volScalar, 2)}</span></div>
            </div>
          </div>
        </div>
      )}

      {last && (
      <div className="panel" style={{ padding: 16, marginBottom: 14 }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 6, flexWrap: "wrap", gap: 8 }}>
          <div>
            <div className="eyebrow">Equity — strategy vs buy &amp; hold</div>
            <div style={{ fontSize: 12, marginTop: 4 }}>
              <span style={{ color: "var(--gold)" }}>● strategy {metrics ? pct(metrics.totalStrat) : ""}</span>
              <span style={{ color: "var(--steel)", marginLeft: 14 }}>● buy &amp; hold {metrics ? pct(metrics.totalHodl) : ""}</span>
              {hasCash && <span style={{ color: "var(--muted)", marginLeft: 14 }}>● cash {metrics ? pct(metrics.cashTotal) : ""}</span>}
            </div>
          </div>
          <div style={{ display: "flex", gap: 4 }}>
            {["log", "linear"].map((s) => (
              <button key={s} onClick={() => setLogScale(s === "log")}
                style={{ fontSize: 11, padding: "5px 11px", borderRadius: 6, cursor: "pointer",
                  border: "1px solid var(--line)",
                  background: (logScale === (s === "log")) ? "var(--panel2)" : "transparent",
                  color: (logScale === (s === "log")) ? "var(--text)" : "var(--muted)" }}>{s}</button>
            ))}
          </div>
        </div>
        <ResponsiveContainer width="100%" height={300}>
          <LineChart data={data} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
            <CartesianGrid stroke="var(--line)" strokeDasharray="2 4" vertical={false} />
            {spans.map(([x1, x2], i) => (
              <ReferenceArea key={i} x1={x1} x2={x2} fill="var(--gold)" fillOpacity={0.07} stroke="none" />
            ))}
            <XAxis dataKey="date" ticks={dateTicks} tick={{ className: "tick" }} stroke="var(--line)" />
            <YAxis scale={logScale ? "log" : "linear"} domain={["auto", "auto"]}
              tickFormatter={(v) => `${v.toFixed(2)}×`} tick={{ className: "tick" }} stroke="var(--line)" width={48} />
            <Tooltip content={<ChartTooltip />} />
            <Line type="monotone" dataKey="hodl" stroke="var(--steel)" strokeWidth={1.5} dot={false} isAnimationActive={false} />
            {hasCash && <Line type="monotone" dataKey="cash" stroke="var(--muted)" strokeWidth={1} strokeDasharray="3 3" dot={false} isAnimationActive={false} />}
            <Line type="monotone" dataKey="strat" stroke="var(--gold)" strokeWidth={2} dot={false} isAnimationActive={false} />
          </LineChart>
        </ResponsiveContainer>
        <div style={{ fontSize: 11, color: "var(--muted)", marginTop: 6 }}>
          Gold bands = strategy in market. Unshaded = defensive in cash.
        </div>
      </div>
      )}

      {last && (
      <div className="panel" style={{ padding: 16, marginBottom: 14 }}>
        <div className="eyebrow" style={{ marginBottom: 6 }}>Drawdown — strategy</div>
        <ResponsiveContainer width="100%" height={140}>
          <AreaChart data={data} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
            <defs>
              <linearGradient id="ddg" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="var(--sell)" stopOpacity={0.05} />
                <stop offset="100%" stopColor="var(--sell)" stopOpacity={0.4} />
              </linearGradient>
            </defs>
            <CartesianGrid stroke="var(--line)" strokeDasharray="2 4" vertical={false} />
            <XAxis dataKey="date" ticks={dateTicks} tick={{ className: "tick" }} stroke="var(--line)" />
            <YAxis tickFormatter={(v) => pct(v, 0)} tick={{ className: "tick" }} stroke="var(--line)" width={48} />
            <Tooltip content={<ChartTooltip />} />
            <Area type="monotone" dataKey="dd" stroke="var(--sell)" strokeWidth={1.5} fill="url(#ddg)" isAnimationActive={false} />
          </AreaChart>
        </ResponsiveContainer>
      </div>
      )}

      {metrics && (
        <>
          <div className="grid" style={{ gridTemplateColumns: "repeat(auto-fit,minmax(140px,1fr))", marginBottom: 8 }}>
            <Metric label="Total return" value={pct(metrics.totalStrat, 2)} sub={`HODL ${pct(metrics.totalHodl, 2)}`} accent="var(--gold)" />
            <Metric label="vs cash" value={pct(metrics.excessOverCash, 2)}
              sub={`cash ${pct(metrics.cashTotal, 2)} · ${STABLE_APY * 100}% APY assumed`}
              accent={metrics.excessOverCash >= 0 ? "var(--buy)" : "var(--sell)"} />
            <Metric label="Max drawdown" value={pct(metrics.maxDD, 2)} sub={`HODL ${pct(metrics.hodlMaxDD, 2)}`} accent="var(--sell)" />
            <Metric label="Time in market" value={pct(metrics.inMarketShare, 0)} sub={`${metrics.n} days`} />
            <Metric label="Sharpe" value={metrics.sharpe == null ? "—" : num(metrics.sharpe, 2)}
              sub={metrics.enoughSample ? "excess over cash, annualized" : `needs ${MIN_DAYS_ANNUALIZED}d · have ${metrics.days}d`} />
            <Metric label="Calmar" value={metrics.calmar == null ? "—" : num(metrics.calmar, 2)}
              sub={metrics.enoughSample ? "CAGR / maxDD" : `needs ${MIN_DAYS_ANNUALIZED}d · have ${metrics.days}d`} />
          </div>
          <div style={{ fontSize: 11, color: "var(--muted)", marginBottom: 14, lineHeight: 1.6 }}>
            Assumed, not observed: cash at {STABLE_APY * 100}% APY and {COST_BPS} bps per unit of turnover
            (high-volume tier; retail taker runs 25–60 bps). Annualized ratios are hidden until {MIN_DAYS_ANNUALIZED} days
            of record — below that they are noise.
          </div>
        </>
      )}

      {last && (
      <div className="panel" style={{ padding: 16 }}>
        <div className="eyebrow" style={{ marginBottom: 10 }}>Recent decisions</div>
        <div style={{ overflowX: "auto" }}>
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
            <thead>
              <tr style={{ color: "var(--muted)" }}>
                {["Date", "BTC", "Trend", "Target", "Signal", "Actual", "Call", "Equity"].map((h, i) => (
                  <th key={h} style={{ padding: "6px 8px", textAlign: i === 0 || i === 6 ? "left" : "right", fontWeight: 500, borderBottom: "1px solid var(--line)" }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {[...data].slice(-12).reverse().map((d) => (
                <tr key={d.date} style={{ borderBottom: "1px solid var(--panel2)" }}>
                  <td style={{ padding: "7px 8px" }}>{d.date}</td>
                  <td style={{ padding: "7px 8px", textAlign: "right" }}>{money(d.btc)}</td>
                  <td style={{ padding: "7px 8px", textAlign: "right", color: "var(--gold)" }}>{num(d.trend, 2)}</td>
                  <td style={{ padding: "7px 8px", textAlign: "right" }}>{pct(d.target, 0)}</td>
                  <td style={{ padding: "7px 8px", textAlign: "right" }}>{pct(d.weight, 0)}</td>
                  {/* Peso REAL: deriva con el precio entre rebalanceos */}
                  <td style={{ padding: "7px 8px", textAlign: "right", color: "var(--muted)" }}>{pct(d.weightReal, 1)}</td>
                  <td style={{ padding: "7px 8px", color: actionColor(d.action) }}>{actionLabel(d.action)}</td>
                  <td style={{ padding: "7px 8px", textAlign: "right" }}>{num(d.strat, 4)}×</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
      )}

      <div style={{ fontSize: 11, color: "var(--muted)", textAlign: "center", marginTop: 18 }}>
        Paper trading · not financial advice
      </div>
    </div>
  );
}

import React, { useState, useMemo, useEffect } from "react";
import Papa from "papaparse";
import {
  ResponsiveContainer, LineChart, Line, AreaChart, Area,
  XAxis, YAxis, CartesianGrid, Tooltip, ReferenceArea,
} from "recharts";

/* CSV publicado del Google Sheet. En Vercel se define como variable de entorno
   VITE_CSV_URL; en local puedes usar un archivo .env (ver .env.example). */
const ENV_URL = import.meta.env.VITE_CSV_URL || "";

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

function parseRows(rows) {
  return rows
    .filter((r) => r.date)
    .map((r) => ({
      date: String(r.date).trim(),
      btc: toNum(r.btc_price),
      trend: toNum(r.trend_score),
      volScalar: toNum(r.vol_scalar),
      target: toNum(r.target_weight),
      weight: toNum(r.new_weight),
      action: String(r.action || "").trim().toUpperCase(),
      tradePct: toNum(r.trade_pct),
      dailyRet: toNum(r.daily_return),
      strat: toNum(r.strat_equity),
      hodl: toNum(r.hodl_equity),
      dd: toNum(r.drawdown),
    }))
    .filter((r) => Number.isFinite(r.strat))
    .map((r) => ({ ...r, inMarket: r.weight > 1e-9 }));
}

function computeMetrics(data) {
  if (data.length < 2) return null;
  const first = data[0], last = data[data.length - 1];
  const days = Math.max(1, (new Date(last.date) - new Date(first.date)) / 86400000);

  const stratRets = [];
  for (let i = 1; i < data.length; i++) stratRets.push(data[i].strat / data[i - 1].strat - 1);
  const mean = stratRets.reduce((a, b) => a + b, 0) / stratRets.length;
  const variance = stratRets.reduce((a, b) => a + (b - mean) ** 2, 0) / Math.max(1, stratRets.length - 1);
  const std = Math.sqrt(variance);

  const cagr = Math.pow(last.strat / first.strat, 365 / days) - 1;
  const hodlCagr = Math.pow(last.hodl / first.hodl, 365 / days) - 1;
  const maxDD = Math.min(0, ...data.map((d) => d.dd));
  const hodlMaxDD = Math.min(...data.map((d, i) => {
    const peak = Math.max(...data.slice(0, i + 1).map((x) => x.hodl));
    return d.hodl / peak - 1;
  }));
  const inMarketShare = data.filter((d) => d.inMarket).length / data.length;

  const sharpe = std > 1e-9 ? (mean / std) * Math.sqrt(365) : null;
  const calmar = maxDD < -1e-6 ? cagr / Math.abs(maxDD) : null;

  return {
    cagr, hodlCagr, maxDD, hodlMaxDD, inMarketShare, sharpe, calmar,
    totalStrat: last.strat / first.strat - 1,
    totalHodl: last.hodl / first.hodl - 1,
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

function demoData() {
  const out = [];
  let price = 42000, strat = 1, hodl = 1, peak = 1;
  const cashD = Math.pow(1.04, 1 / 365) - 1;
  let rng = 7;
  const rand = () => { rng = (rng * 1103515245 + 12345) & 0x7fffffff; return rng / 0x7fffffff - 0.5; };
  const start = new Date("2025-09-20");
  for (let i = 0; i < 240; i++) {
    const date = new Date(start.getTime() + i * 86400000).toISOString().slice(0, 10);
    let drift = i < 90 ? 0.004 : i < 150 ? -0.006 : 0.0035;
    const ret = drift + rand() * 0.045;
    price *= 1 + ret;
    hodl *= 1 + ret;
    const weight = i < 80 ? 0.9 : i < 100 ? 0.4 : i < 165 ? 0 : 0.85;
    const sret = weight * ret + (1 - weight) * cashD;
    strat *= 1 + sret;
    peak = Math.max(peak, strat);
    out.push({
      date, btc_price: price, trend_score: weight > 0 ? (weight > 0.6 ? 1 : 0.5) : 0,
      vol_scalar: 1, target_weight: weight, new_weight: weight,
      action: "MANTENER", trade_pct: 0, daily_return: ret,
      strat_equity: strat, hodl_equity: hodl, drawdown: strat / peak - 1,
    });
  }
  return out;
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
      <div style={{ color: "var(--muted)", marginTop: 4 }}>{p.inMarket ? `in market · ${pct(p.weight, 0)}` : "in cash"} · {money(p.btc)}</div>
    </div>
  );
}

/* ------------------------------------------------------------------ *
 *  App
 * ------------------------------------------------------------------ */
export default function App() {
  const [url, setUrl] = useState(ENV_URL);
  const [rows, setRows] = useState(demoData());
  const [source, setSource] = useState("demo");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [logScale, setLogScale] = useState(true);

  const data = useMemo(() => parseRows(rows), [rows]);
  const metrics = useMemo(() => computeMetrics(data), [data]);
  const spans = useMemo(() => marketSpans(data), [data]);
  const last = data[data.length - 1];

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
      if (!clean.length) throw new Error("No encontré filas válidas. ¿Es el CSV de la pestaña track_record?");
      setRows(parsed.data); setSource("live");
    } catch (e) {
      setError(`No pude cargar el CSV (${e.message}).`);
    } finally { setLoading(false); }
  }

  // Auto-carga si VITE_CSV_URL está definida
  useEffect(() => { if (ENV_URL) loadUrl(ENV_URL); /* eslint-disable-next-line */ }, []);

  const dateTicks = useMemo(() => {
    if (data.length <= 6) return data.map((d) => d.date);
    const step = Math.ceil(data.length / 6);
    return data.filter((_, i) => i % step === 0).map((d) => d.date);
  }, [data]);

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
          <div style={{ fontSize: 11, color: "var(--muted)", marginTop: 6 }}>
            {source === "demo" ? "demo data" : "live"} · last {last ? last.date : "—"}
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
        <button onClick={() => { setRows(demoData()); setSource("demo"); setError(""); }}
          style={{ background: "transparent", color: "var(--muted)", border: "1px solid var(--line)",
            borderRadius: 7, padding: "9px 14px", cursor: "pointer", fontSize: 13 }}>
          Demo
        </button>
      </div>
      {error && <div style={{ color: "var(--sell)", fontSize: 12, marginBottom: 14 }}>{error}</div>}

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
            <WeightGauge weight={last.weight} />
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

      <div className="panel" style={{ padding: 16, marginBottom: 14 }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 6, flexWrap: "wrap", gap: 8 }}>
          <div>
            <div className="eyebrow">Equity — strategy vs buy &amp; hold</div>
            <div style={{ fontSize: 12, marginTop: 4 }}>
              <span style={{ color: "var(--gold)" }}>● strategy {metrics ? pct(metrics.totalStrat) : ""}</span>
              <span style={{ color: "var(--steel)", marginLeft: 14 }}>● buy &amp; hold {metrics ? pct(metrics.totalHodl) : ""}</span>
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
            <Line type="monotone" dataKey="strat" stroke="var(--gold)" strokeWidth={2} dot={false} isAnimationActive={false} />
          </LineChart>
        </ResponsiveContainer>
        <div style={{ fontSize: 11, color: "var(--muted)", marginTop: 6 }}>
          Gold bands = strategy in market. Unshaded = defensive in cash.
        </div>
      </div>

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

      {metrics && (
        <div className="grid" style={{ gridTemplateColumns: "repeat(auto-fit,minmax(140px,1fr))", marginBottom: 14 }}>
          <Metric label="CAGR (to date)" value={pct(metrics.cagr)} sub={`HODL ${pct(metrics.hodlCagr)}`} accent="var(--gold)" />
          <Metric label="Sharpe" value={metrics.sharpe == null ? "—" : num(metrics.sharpe, 2)} sub={metrics.sharpe == null ? "needs more data" : "annualized"} />
          <Metric label="Calmar" value={metrics.calmar == null ? "—" : num(metrics.calmar, 2)} sub={metrics.calmar == null ? "no drawdown yet" : "CAGR / maxDD"} />
          <Metric label="Max drawdown" value={pct(metrics.maxDD)} sub={`HODL ${pct(metrics.hodlMaxDD)}`} accent="var(--sell)" />
          <Metric label="Time in market" value={pct(metrics.inMarketShare, 0)} sub={`${metrics.n} days`} />
        </div>
      )}

      <div className="panel" style={{ padding: 16 }}>
        <div className="eyebrow" style={{ marginBottom: 10 }}>Recent decisions</div>
        <div style={{ overflowX: "auto" }}>
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
            <thead>
              <tr style={{ color: "var(--muted)" }}>
                {["Date", "BTC", "Trend", "Target", "Position", "Call", "Strategy"].map((h, i) => (
                  <th key={h} style={{ padding: "6px 8px", textAlign: i === 0 || i === 5 ? "left" : "right", fontWeight: 500, borderBottom: "1px solid var(--line)" }}>{h}</th>
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
                  <td style={{ padding: "7px 8px", color: actionColor(d.action) }}>{actionLabel(d.action)}</td>
                  <td style={{ padding: "7px 8px", textAlign: "right" }}>{num(d.strat, 4)}×</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <div style={{ fontSize: 11, color: "var(--muted)", textAlign: "center", marginTop: 18 }}>
        Paper trading · not financial advice
      </div>
    </div>
  );
}

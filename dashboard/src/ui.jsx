/* ui.jsx — piezas visuales del dashboard. Sin estado propio salvo toggles locales. */
import React, { useMemo, useState } from "react";
import {
  ResponsiveContainer, ComposedChart, LineChart, Line, Area, XAxis, YAxis, CartesianGrid,
  Tooltip, ReferenceArea, ReferenceLine, ScatterChart, Scatter, ZAxis,
} from "recharts";
import { coneAt, daysBetween, withDrawdowns } from "./lib.js";

/* ------------------------------------------------------------------ formato */
export const pct = (x, d = 1) => (x == null || Number.isNaN(x) ? "—" : `${(x * 100).toFixed(d)}%`);
export const num = (x, d = 2) => (x == null || Number.isNaN(x) ? "—" : x.toLocaleString("es-CL", { minimumFractionDigits: d, maximumFractionDigits: d }));
export const usd = (x) => (x == null || Number.isNaN(x) ? "—" : "US$" + Math.round(x).toLocaleString("es-CL"));
export const bps = (x) => (x == null || Number.isNaN(x) ? "—" : `${Math.round(x)} pb`);

export const VERSION_COLOR = { v21: "var(--gold)", v3: "var(--teal)", v20: "var(--violet)", hodl: "var(--steel)", cash: "var(--muted)" };
export const VERSION_NAME = { v21: "v2.1", v3: "V3", v20: "v2.0", hodl: "HODL", cash: "Cash" };

export const actionColor = (a) => (a === "COMPRAR" ? "var(--buy)" : a === "VENDER" ? "var(--sell)" : "var(--hold)");
export const actionLabel = (a) => (a === "COMPRAR" ? "COMPRAR" : a === "VENDER" ? "VENDER" : "MANTENER");

/* ------------------------------------------------------------------ estilos */
export const STYLES = `
@import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;700&family=IBM+Plex+Mono:wght@400;500;600&display=swap');
.btcd { --ink:#0E1320; --panel:#151B2B; --panel2:#1B2336; --line:#28324d;
  --text:#E7EBF3; --muted:#8B95AB; --gold:#E8B33B; --steel:#6FB3D6; --teal:#3CC3A6; --violet:#A48BE0;
  --buy:#54B98A; --sell:#D98B6A; --hold:#8B95AB; --warn:#E0B44A;
  background:var(--ink); color:var(--text); min-height:100vh;
  font-family:'IBM Plex Mono',ui-monospace,monospace; padding:20px; max-width:1100px; margin:0 auto; }
.btcd * { box-sizing:border-box; }
.btcd .display { font-family:'Space Grotesk',system-ui,sans-serif; }
.btcd .eyebrow { font-size:11px; letter-spacing:.18em; text-transform:uppercase; color:var(--muted); }
.btcd .panel { background:var(--panel); border:1px solid var(--line); border-radius:10px; padding:16px; min-width:0; }
.btcd .grid { display:grid; gap:14px; }
.btcd .metric-val { font-family:'Space Grotesk',system-ui,sans-serif; font-weight:700; }
.btcd .tick { font-size:11px; fill:var(--muted); }
.btcd .sub { font-size:11px; color:var(--muted); margin-top:2px; line-height:1.5; }
.btcd .row { display:flex; flex-wrap:wrap; gap:8px; align-items:center; }
.btcd .seg { display:inline-flex; flex-wrap:wrap; border:1px solid var(--line); border-radius:8px; overflow:hidden; }
.btcd .seg button { font:500 12px 'IBM Plex Mono',monospace; background:transparent; color:var(--muted); border:0; border-right:1px solid var(--line); padding:7px 12px; cursor:pointer; }
.btcd .seg button:last-child { border-right:0; }
.btcd .seg button[aria-pressed="true"] { background:var(--panel2); color:var(--text); }
.btcd .seg button:disabled { opacity:.35; cursor:not-allowed; }
.btcd button:focus-visible, .btcd input:focus-visible, .btcd summary:focus-visible { outline:2px solid var(--gold); outline-offset:1px; }
.btcd table { width:100%; border-collapse:collapse; font-size:12px; }
.btcd th { padding:6px 8px; color:var(--muted); font-weight:500; border-bottom:1px solid var(--line); text-align:right; }
.btcd td { padding:7px 8px; text-align:right; border-bottom:1px solid var(--panel2); font-variant-numeric:tabular-nums; white-space:nowrap; }
.btcd th:first-child, .btcd td:first-child { text-align:left; }
.btcd .scroll { overflow-x:auto; }
.btcd .pill { display:inline-block; font-size:11px; font-weight:600; letter-spacing:.06em; padding:3px 9px; border-radius:999px; border:1px solid var(--line); }
.btcd .two { display:grid; gap:14px; grid-template-columns:repeat(auto-fit,minmax(320px,1fr)); }
.btcd details summary { cursor:pointer; list-style:none; }
.btcd details summary::-webkit-details-marker { display:none; }
.btcd input[type=url] { width:100%; background:var(--ink); border:1px solid var(--line); border-radius:7px; color:var(--text); padding:8px 10px; font:12px 'IBM Plex Mono',monospace; }
.btcd .btn { background:var(--gold); color:#1a1407; border:none; border-radius:7px; padding:8px 16px; font-weight:600; cursor:pointer; font-family:inherit; font-size:12px; }
.btcd .btn.ghost { background:transparent; color:var(--muted); border:1px solid var(--line); }
.btcd .strip { display:flex; gap:3px; flex-wrap:wrap; }
.btcd .strip i { width:10px; height:18px; border-radius:2px; display:inline-block; }
.btcd .now td { background:rgba(232,179,59,.08); }
@media (max-width:720px){ .btcd { padding:12px; } }
@media (prefers-reduced-motion:reduce){ .btcd * { transition:none !important; animation:none !important; } }
`;

/* ------------------------------------------------------------------ piezas */
export function Pill({ color, children, title }) {
  return <span className="pill" title={title} style={{ color, borderColor: color, background: "transparent" }}>{children}</span>;
}

export function Metric({ label, value, sub, accent }) {
  return (
    <div className="panel" style={{ padding: "14px 16px" }}>
      <div className="eyebrow">{label}</div>
      <div className="metric-val" style={{ fontSize: 24, marginTop: 6, color: accent || "var(--text)" }}>{value}</div>
      {sub && <div className="sub">{sub}</div>}
    </div>
  );
}

export function WeightGauge({ real, signal }) {
  const w = Math.min(100, Math.max(0, (real || 0) * 100));
  const s = Math.min(100, Math.max(0, (signal || 0) * 100));
  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", fontSize: 11, color: "var(--muted)" }}>
        <span>POSICIÓN REAL</span><span>{pct(real, 1)} en BTC</span>
      </div>
      <div style={{ position: "relative", height: 8, background: "var(--panel2)", borderRadius: 6, marginTop: 6 }}>
        <div style={{ width: `${w}%`, height: "100%", background: "linear-gradient(90deg,#E8B33B,#f0c463)", borderRadius: 6 }} />
        {Number.isFinite(signal) && <div title={`Señal ${pct(signal, 0)}`} style={{ position: "absolute", left: `calc(${s}% - 1px)`, top: -3, width: 2, height: 14, background: "var(--text)" }} />}
      </div>
      <div className="sub">marca blanca = señal {pct(signal, 0)}</div>
    </div>
  );
}

const axisProps = { tick: { className: "tick" }, stroke: "var(--line)" };
const tipBox = { background: "var(--panel2)", border: "1px solid var(--line)", borderRadius: 8, padding: "8px 11px", fontSize: 12 };

function dateTicks(rows, n = 6) {
  if (rows.length <= n) return rows.map((d) => d.date);
  const step = Math.ceil(rows.length / n);
  return rows.filter((_, i) => i % step === 0).map((d) => d.date);
}

/* ------------------------------------------------------------------ giro */
export function FlipPanel({ sc, version, note }) {
  if (!sc) {
    return (
      <div className="panel">
        <div className="eyebrow">Precios de giro para el próximo cierre</div>
        <div className="sub" style={{ marginTop: 8 }}>
          Falta la pestaña <code>next_levels</code>. La escribe <code>daily_levels.py</code> en cada corrida; publícala como CSV y pega el link en Fuentes de datos.
        </div>
      </div>
    );
  }
  const now = sc.rows.find((r) => (r.lo == null || sc.price > r.lo) && (r.hi == null || sc.price <= r.hi));
  const label = (r) => r.lo == null ? `bajo ${usd(r.hi)}` : r.hi == null ? `sobre ${usd(r.lo)}` : `${usd(r.lo)} – ${usd(r.hi)}`;
  const dist = (r) => {
    const edge = r.lo == null ? r.hi : r.hi == null ? r.lo : null;
    if (edge == null) return `${pct(r.lo / sc.price - 1)} a ${pct(r.hi / sc.price - 1)}`;
    return pct(edge / sc.price - 1);
  };
  const nearest = sc.rows.flatMap((r) => [r.lo, r.hi]).filter((x) => x != null)
    .map((x) => ({ x, d: x / sc.price - 1 })).sort((a, b) => Math.abs(a.d) - Math.abs(b.d))[0];
  return (
    <div className="panel">
      <div className="row" style={{ justifyContent: "space-between" }}>
        <div>
          <div className="eyebrow">Precios de giro · {VERSION_NAME[version]} · cierre siguiente al {sc.date}</div>
          <div className="display" style={{ fontSize: 17, fontWeight: 600, marginTop: 4 }}>
            {now ? <>Si cierra igual que hoy ({usd(sc.price)}): <span style={{ color: actionColor(now.action) }}>{actionLabel(now.action)}</span> → {pct(now.weight, 0)}</> : "—"}
          </div>
          {nearest && <div className="sub">Umbral más cercano: {usd(nearest.x)} ({pct(nearest.d)} desde hoy).</div>}
        </div>
      </div>
      <div className="scroll" style={{ marginTop: 10 }}>
        <table>
          <thead><tr><th>Cierre de mañana</th><th>Distancia</th><th>{version === "v3" ? "Plazos al alza" : "Tendencia"}</th><th>Peso resultante</th><th>Decisión</th></tr></thead>
          <tbody>
            {[...sc.rows].reverse().map((r, i) => (
              <tr key={i} className={r === now ? "now" : ""}>
                <td>{label(r)}{r === now ? "  ← hoy" : ""}</td>
                <td>{dist(r)}</td>
                <td>{version === "v3"
                  ? (Math.round(r.votes * 4) === Math.round(r.votesHi * 4) ? `${Math.round(r.votes * 4)} de 4` : `${Math.round(r.votes * 4)}–${Math.round(r.votesHi * 4)} de 4`)
                  : (Math.abs(r.votes - r.votesHi) < 1e-9 ? num(r.votes, 2) : `${num(r.votes, 2)}–${num(r.votesHi, 2)}`)}</td>
                <td>{pct(r.weight, 0)}</td>
                <td style={{ color: actionColor(r.action), fontWeight: 600 }}>{actionLabel(r.action)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="sub" style={{ marginTop: 8 }}>
        {version === "v3"
          ? `Cada plazo vota arriba si el cierre de mañana supera el de hace L días (los mismos que v2.1). V3 queda 100% en BTC con ${sc.need} o más plazos al alza y 0% con menos.`
          : `Cada plazo vota arriba si el cierre de mañana supera el de hace L días. Opera si la señal se mueve más de 10 pp. Supone volatilidad sin cambio (vol scalar ${num(sc.vs, 2)}).`}
        {note ? ` ${note}` : ""}
      </div>
      <div className="row" style={{ marginTop: 8 }}>
        {sc.detail.map((d) => (
          <Pill key={d.n} color={d.state ? "var(--buy)" : "var(--muted)"} title={`umbral ${usd(d.level)}`}>
            {d.n}d {d.state ? "arriba" : "abajo"} · {usd(d.level)}
          </Pill>
        ))}
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ salud */
const STATUS = {
  ok: { label: "AL DÍA", color: "var(--buy)" },
  late: { label: "ATRASADO", color: "var(--warn)" },
  fork: { label: "FORK · BLOQUEADO", color: "var(--sell)" },
};

export function HealthBadge({ h }) {
  if (!h) return null;
  const s = STATUS[h.status];
  return <Pill color={s.color}>● {s.label}</Pill>;
}

export function HealthPanel({ title, h }) {
  if (!h) {
    return (
      <div className="panel">
        <div className="eyebrow">{title}</div>
        <div className="sub" style={{ marginTop: 8 }}>Sin datos de corridas. Publica la pestaña de corridas y pega el link en Fuentes de datos.</div>
      </div>
    );
  }
  const s = STATUS[h.status];
  return (
    <div className="panel">
      <div className="row" style={{ justifyContent: "space-between" }}>
        <div className="eyebrow">{title}</div>
        <Pill color={s.color}>● {s.label}</Pill>
      </div>
      <div className="grid" style={{ gridTemplateColumns: "repeat(3,minmax(0,1fr))", marginTop: 10, fontSize: 12 }}>
        <div><div className="sub">Última corrida</div><div>{h.last.run.slice(5, 16)} UTC</div><div className="sub">hace {num(h.hoursSince, 0)} h</div></div>
        <div><div className="sub">Atraso del cron</div><div>{num(h.medDelay, 1)} h</div><div className="sub">mediana 30 corridas</div></div>
        <div><div className="sub">Corridas OK seguidas</div><div>{h.streak}</div><div className="sub">{h.forks30} FORK en 30</div></div>
      </div>
      <div className="sub" style={{ marginTop: 10 }}>Últimas {h.recent.length} corridas (verde OK, rojo abortada)</div>
      <div className="strip" style={{ marginTop: 4 }} aria-label="historial de corridas">
        {h.recent.map((m, i) => (
          <i key={i} title={`${m.run} · ${m.consistency}${m.rowsAdded ? ` · +${m.rowsAdded}` : ""}`} style={{ background: m.ok ? "var(--buy)" : "var(--sell)", opacity: m.ok ? 0.85 : 1 }} />
        ))}
      </div>
      {h.status === "fork" && <div className="sub" style={{ color: "var(--sell)", marginTop: 8 }}>La última corrida no escribió: {h.last.consistency}. Revisa el log de Actions.</div>}
      {h.status === "late" && <div className="sub" style={{ color: "var(--warn)", marginTop: 8 }}>{h.staleDays > 1 ? `Faltan ${h.staleDays} días en el registro.` : "Sin corrida en más de 36 h."}</div>}
    </div>
  );
}

/* ------------------------------------------------------------------ gráficos */
export function EquityChart({ data, cone, coneKey, hasCash, color, liveStart, allReconstructed, rebase = "account" }) {
  const [logScale, setLogScale] = useState(true);
  const [showCone, setShowCone] = useState(true);
  const rows = useMemo(() => {
    if (!data.length) return [];
    // "account": la cuenta nace en 1,0 (el costo de la primera compra se ve);
    // "first": tramo rebasado en su primera fila (p. ej. solo en vivo)
    const d0 = data[0].date;
    const base = rebase === "first" ? data[0].strat : 1;
    const hb = rebase === "first" ? data[0].hodl : 1;
    const cb = rebase === "first" ? data[0].cash : 1;
    return data.map((d) => {
      const c = cone ? coneAt(cone, coneKey, daysBetween(d0, d.date)) : null;
      return {
        ...d,
        stratN: d.strat / base,
        hodlN: d.hodl / hb,
        cashN: d.cash / cb,
        cone90: c ? [c[5], c[95]] : null,
        cone50: c ? [c[25], c[75]] : null,
        coneMed: c ? c[50] : null,
      };
    });
  }, [data, cone, coneKey, rebase]);
  const spans = useMemo(() => {
    const out = []; let st = null;
    rows.forEach((d, i) => {
      if (d.inMarket && st === null) st = d.date;
      if ((!d.inMarket || i === rows.length - 1) && st !== null) { out.push([st, d.inMarket ? d.date : rows[i - 1].date]); st = null; }
    });
    return out;
  }, [rows]);
  const last = rows.at(-1);
  const outside = last && last.cone90 && (last.stratN < last.cone90[0] || last.stratN > last.cone90[1]);
  return (
    <div className="panel">
      <div className="row" style={{ justifyContent: "space-between" }}>
        <div>
          <div className="eyebrow">Capital — estrategia vs comprar y mantener</div>
          <div style={{ fontSize: 12, marginTop: 4 }} className="row">
            <span style={{ color }}>● estrategia {last ? pct(last.stratN - 1) : ""}</span>
            <span style={{ color: "var(--steel)" }}>● HODL {last ? pct(last.hodlN - 1) : ""}</span>
            {hasCash && <span style={{ color: "var(--muted)" }}>● cash</span>}
            {cone && <span style={{ color: "var(--muted)" }}>▒ rango esperado</span>}
          </div>
        </div>
        <div className="row">
          {cone && <div className="seg"><button aria-pressed={showCone} onClick={() => setShowCone(!showCone)}>rango</button></div>}
          <div className="seg">
            {["log", "lineal"].map((s) => <button key={s} aria-pressed={logScale === (s === "log")} onClick={() => setLogScale(s === "log")}>{s}</button>)}
          </div>
        </div>
      </div>
      <ResponsiveContainer width="100%" height={300}>
        <ComposedChart data={rows} margin={{ top: 8, right: 8, left: 4, bottom: 0 }}>
          <CartesianGrid stroke="var(--line)" strokeDasharray="2 4" vertical={false} />
          {spans.map(([a, b], i) => <ReferenceArea key={i} x1={a} x2={b} fill="var(--gold)" fillOpacity={0.05} stroke="none" />)}
          {liveStart && <ReferenceLine x={liveStart} stroke="var(--text)" strokeDasharray="4 3" label={{ value: "en vivo →", position: "insideTopLeft", fill: "var(--muted)", fontSize: 11 }} />}
          <XAxis dataKey="date" ticks={dateTicks(rows)} {...axisProps} />
          <YAxis scale={logScale ? "log" : "linear"} domain={["auto", "auto"]} allowDataOverflow
            tickFormatter={(v) => `${v.toFixed(2)}×`} width={56} {...axisProps} />
          <Tooltip content={({ active, payload, label }) => {
            if (!active || !payload?.length) return null; const p = payload[0].payload;
            return (
              <div style={tipBox}>
                <div style={{ color: "var(--muted)" }}>{label}</div>
                <div style={{ color }}>Estrategia {num(p.stratN, 4)}×</div>
                <div style={{ color: "var(--steel)" }}>HODL {num(p.hodlN, 4)}×</div>
                {p.cone90 && <div style={{ color: "var(--muted)" }}>Rango 90%: {num(p.cone90[0], 3)}–{num(p.cone90[1], 3)}×</div>}
                <div style={{ color: "var(--muted)" }}>{p.inMarket ? `en mercado · ${pct(p.weightReal, 0)}` : "en cash"} · {usd(p.btc)}</div>
              </div>
            );
          }} />
          {cone && showCone && <Area dataKey="cone90" stroke="none" fill="var(--muted)" fillOpacity={0.12} isAnimationActive={false} />}
          {cone && showCone && <Area dataKey="cone50" stroke="none" fill="var(--muted)" fillOpacity={0.18} isAnimationActive={false} />}
          {cone && showCone && <Line dataKey="coneMed" stroke="var(--muted)" strokeDasharray="2 3" strokeWidth={1} dot={false} isAnimationActive={false} />}
          <Line dataKey="hodlN" name="hodl" stroke="var(--steel)" strokeWidth={1.5} dot={false} isAnimationActive={false} />
          {hasCash && <Line dataKey="cashN" name="cash" stroke="var(--muted)" strokeWidth={1} strokeDasharray="3 3" dot={false} isAnimationActive={false} />}
          <Line dataKey="stratN" stroke={color} strokeWidth={2} dot={false} isAnimationActive={false} />
        </ComposedChart>
      </ResponsiveContainer>
      <div className="sub" style={{ marginTop: 6 }}>
        Bandas doradas = en mercado. {liveStart ? `Antes del ${liveStart} el registro es reconstruido (calculado después, con las mismas reglas); la evidencia en vivo empieza en la línea punteada. ` : allReconstructed ? "Todo el registro mostrado es reconstruido: aún no hay días en vivo. " : ""}{cone ? `El rango gris es una distribución histórica simulada (50% y 90% central de 4.000 trayectorias armadas con los retornos diarios 2022–2026 del backtest), no una predicción${outside ? "; hoy la estrategia está FUERA de ese rango" : "; hoy la estrategia está dentro"}.` : ""}
      </div>
    </div>
  );
}

export function CompareChart({ cmp, liveStart }) {
  const [hidden, setHidden] = useState({});
  if (!cmp.rows.length || cmp.keys.length < 2) return null;
  const last = cmp.rows.at(-1);
  const toggle = (k) => setHidden({ ...hidden, [k]: !hidden[k] });
  return (
    <div className="panel">
      <div className="eyebrow">Comparación de versiones · base común {cmp.start}</div>
      <div className="row" style={{ fontSize: 12, marginTop: 4 }}>
        {[...cmp.keys, "hodl"].map((k) => (
          <button key={k} type="button" onClick={() => toggle(k)} aria-pressed={!hidden[k]} title="Mostrar u ocultar"
            style={{ background: "transparent", border: "1px solid var(--line)", borderRadius: 999, padding: "3px 10px", cursor: "pointer",
              font: "inherit", fontSize: 12, color: VERSION_COLOR[k], opacity: hidden[k] ? 0.4 : 1, textDecoration: hidden[k] ? "line-through" : "none" }}>
            ● {VERSION_NAME[k]} {last[k] != null ? pct(last[k] - 1) : "—"}
          </button>
        ))}
      </div>
      <ResponsiveContainer width="100%" height={240}>
        <LineChart data={cmp.rows} margin={{ top: 8, right: 8, left: 4, bottom: 0 }}>
          <CartesianGrid stroke="var(--line)" strokeDasharray="2 4" vertical={false} />
          <XAxis dataKey="date" ticks={dateTicks(cmp.rows)} {...axisProps} />
          <YAxis domain={["auto", "auto"]} tickFormatter={(v) => `${v.toFixed(2)}×`} width={56} {...axisProps} />
          <ReferenceLine y={1} stroke="var(--line)" />
          <Tooltip contentStyle={tipBox} labelStyle={{ color: "var(--muted)" }} formatter={(v, k) => [`${num(v, 4)}×`, VERSION_NAME[k] || k]} />
          {liveStart && <ReferenceLine x={liveStart} stroke="var(--teal)" strokeDasharray="4 3" label={{ value: "V3 en vivo →", position: "insideTopLeft", fill: "var(--muted)", fontSize: 11 }} />}
          {!hidden.hodl && <Line dataKey="hodl" stroke="var(--steel)" strokeWidth={1.2} dot={false} isAnimationActive={false} connectNulls />}
          {cmp.keys.filter((k) => !hidden[k]).map((k) => <Line key={k} dataKey={k} stroke={VERSION_COLOR[k]} strokeWidth={2} dot={false} isAnimationActive={false} connectNulls />)}
        </LineChart>
      </ResponsiveContainer>
      <div className="sub">Todas rebasadas a 1 en la fecha en que empezó la versión más reciente con datos. Mismos precios, distintas reglas. Toca una etiqueta para mostrarla u ocultarla.{liveStart ? ` V3 está reconstruida antes del ${liveStart}.` : ""}</div>
    </div>
  );
}

export function DrawdownChart({ data, color }) {
  const rows = useMemo(() => withDrawdowns(data), [data]);
  return (
    <div className="panel">
      <div className="eyebrow">Caída desde el máximo — estrategia vs HODL</div>
      <ResponsiveContainer width="100%" height={150}>
        <ComposedChart data={rows} margin={{ top: 6, right: 8, left: 4, bottom: 0 }}>
          <CartesianGrid stroke="var(--line)" strokeDasharray="2 4" vertical={false} />
          <XAxis dataKey="date" ticks={dateTicks(rows)} {...axisProps} />
          <YAxis tickFormatter={(v) => pct(v, 0)} width={56} {...axisProps} />
          <Tooltip contentStyle={tipBox} labelStyle={{ color: "var(--muted)" }} formatter={(v, k) => [pct(v, 2), k === "ddStrat" ? "Estrategia" : "HODL"]} />
          <Line dataKey="ddHodl" stroke="var(--steel)" strokeWidth={1.2} dot={false} isAnimationActive={false} />
          <Area dataKey="ddStrat" stroke={color} fill={color} fillOpacity={0.18} strokeWidth={1.5} isAnimationActive={false} />
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}

export function ExposureChart({ data, color }) {
  return (
    <div className="panel">
      <div className="eyebrow">Exposición — peso real vs señal</div>
      <ResponsiveContainer width="100%" height={150}>
        <LineChart data={data} margin={{ top: 6, right: 8, left: 4, bottom: 0 }}>
          <CartesianGrid stroke="var(--line)" strokeDasharray="2 4" vertical={false} />
          <XAxis dataKey="date" ticks={dateTicks(data)} {...axisProps} />
          <YAxis domain={[0, 1]} tickFormatter={(v) => pct(v, 0)} width={56} {...axisProps} />
          <Tooltip contentStyle={tipBox} labelStyle={{ color: "var(--muted)" }} formatter={(v, k) => [pct(v, 1), k === "weightReal" ? "Peso real" : "Señal"]} />
          <Line type="stepAfter" dataKey="signal" stroke="var(--muted)" strokeDasharray="4 3" strokeWidth={1} dot={false} isAnimationActive={false} />
          <Line type="stepAfter" dataKey="weightReal" stroke={color} strokeWidth={2} dot={false} isAnimationActive={false} />
        </LineChart>
      </ResponsiveContainer>
      <div className="sub">La línea punteada es la señal; la sólida, el peso que realmente tiene la cuenta. Entre operaciones el peso deriva con el precio.</div>
    </div>
  );
}

export function ExecutionPanel({ sf }) {
  if (!sf) return null;
  const all = sf.pts.filter((p) => p.trade == null).map((p) => ({ ...p, gapPct: p.gap * 100 }));
  const buys = sf.trades.filter((p) => p.side > 0).map((p) => ({ ...p, gapPct: p.gap * 100 }));
  const sells = sf.trades.filter((p) => p.side < 0).map((p) => ({ ...p, gapPct: p.gap * 100 }));
  return (
    <div className="panel">
      <div className="eyebrow">Ejecución — precio al correr vs cierre de la señal · v2.1</div>
      <div className="grid" style={{ gridTemplateColumns: "repeat(auto-fit,minmax(150px,1fr))", marginTop: 10, fontSize: 12 }}>
        <div><div className="sub">Costo medio por operación</div><div className="metric-val" style={{ fontSize: 20, color: sf.tradeMeanCost > 0 ? "var(--sell)" : "var(--buy)" }}>{sf.nTrades ? pct(sf.tradeMeanCost, 2) : "—"}</div><div className="sub">{sf.nTrades} operaciones · + = pagó más / vendió más barato</div></div>
        <div><div className="sub">Impacto acumulado</div><div className="metric-val" style={{ fontSize: 20 }}>{sf.nTrades ? `${num(sf.tradeImpactBps, 1)} pb` : "—"}</div><div className="sub">brecha × tamaño de cada operación</div></div>
        <div><div className="sub">Movimiento típico del mercado</div><div className="metric-val" style={{ fontSize: 20 }}>{pct(sf.medAbs, 2)}</div><div className="sub">todas las corridas · p90 {pct(sf.p90Abs, 2)}</div></div>
        <div><div className="sub">Atraso del cron</div><div className="metric-val" style={{ fontSize: 20 }}>{num(sf.medDelay, 1)} h</div><div className="sub">mediana · máx {num(sf.maxDelay, 1)} h</div></div>
      </div>
      <ResponsiveContainer width="100%" height={210}>
        <ScatterChart margin={{ top: 12, right: 8, left: 4, bottom: 4 }}>
          <CartesianGrid stroke="var(--line)" strokeDasharray="2 4" />
          <XAxis type="number" dataKey="delayH" name="atraso" unit=" h" {...axisProps} />
          <YAxis type="number" dataKey="gapPct" name="brecha" unit="%" width={56} {...axisProps} />
          <ZAxis range={[28, 28]} />
          <ReferenceLine y={0} stroke="var(--line)" />
          <Tooltip contentStyle={tipBox} formatter={(v, k) => [k === "atraso" ? `${num(v, 1)} h` : `${num(v, 2)}%`, k]} />
          <Scatter name="sin operación" data={all} fill="var(--muted)" fillOpacity={0.45} isAnimationActive={false} />
          <Scatter name="compra" data={buys} fill="var(--buy)" isAnimationActive={false} />
          <Scatter name="venta" data={sells} fill="var(--sell)" isAnimationActive={false} />
        </ScatterChart>
      </ResponsiveContainer>
      <div className="row sub"><span style={{ color: "var(--buy)" }}>● compra</span><span style={{ color: "var(--sell)" }}>● venta</span><span>● corrida sin operación</span></div>
      <div className="sub">El registro opera al cierre (teórico y recomputable). Aquí se mide cuánto habría cambiado el precio al ejecutar cuando corre el cron: en una compra, un spot sobre el cierre es costo; en una venta, uno bajo el cierre. Solo cuentan los días con operación. En el backtest 2014–2026, ejecutar 5 h después reduce el capital final de V3 de 483× a 363× y deja a v2.1 bajo HODL.</div>
    </div>
  );
}

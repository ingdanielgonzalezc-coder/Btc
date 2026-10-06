import React, { useEffect, useMemo, useState } from "react";
import cone from "./cone.json";
import {
  parseTrack, parseMeta, parseLevels, assumptionsFrom, computeMetrics, compareSeries,
  shortfall, health, scenariosV21, scenariosV3, firstLiveDate, liveSlice, daysStale, STALE_AFTER_DAYS, MIN_DAYS_ANNUALIZED, RETAIL_BPS,
} from "./lib.js";
import { SOURCE_DEFS, loadUrls, saveUrls, clearSavedUrls, loadAll } from "./sources.js";
import {
  STYLES, pct, num, usd, bps, Pill, Metric, WeightGauge, FlipPanel, HealthPanel, HealthBadge,
  EquityChart, CompareChart, DrawdownChart, ExposureChart, ExecutionPanel,
  VERSION_COLOR, VERSION_NAME, actionColor, actionLabel,
} from "./ui.jsx";

const VERSIONS = [
  { key: "v21", label: "v2.1 · oficial" },
  { key: "v3", label: "V3 · todo/nada" },
  { key: "v20", label: "v2.0 · legado" },
];

export default function App() {
  const [urls, setUrls] = useState(loadUrls);
  const [draft, setDraft] = useState(urls);
  const [raw, setRaw] = useState({});
  const [status, setStatus] = useState({});
  const [warnings, setWarnings] = useState([]);
  const [loading, setLoading] = useState(false);
  const [version, setVersion] = useState("v21");
  const [showSources, setShowSources] = useState(false);
  const [span, setSpan] = useState("all");   // "all" | "live"

  async function reload(u = urls) {
    setLoading(true);
    try {
      const r = await loadAll(u);
      setRaw(r.data); setStatus(r.status); setWarnings(r.warnings);
    } finally { setLoading(false); }
  }
  useEffect(() => { reload(); /* eslint-disable-next-line */ }, []);

  const levels = useMemo(() => (raw.levels ? parseLevels(raw.levels) : null), [raw.levels]);
  const A = assumptionsFrom(levels);
  const tracks = useMemo(() => ({
    v21: raw.v21 ? parseTrack(raw.v21, A.costBps) : null,
    v3: raw.v3 ? parseTrack(raw.v3, A.costBps) : null,
    v20: raw.v20 ? parseTrack(raw.v20, A.costBps) : null,
  }), [raw.v21, raw.v3, raw.v20, A.costBps]);
  const meta = useMemo(() => (raw.meta ? parseMeta(raw.meta) : null), [raw.meta]);
  const metaV3 = useMemo(() => (raw.meta_v3 ? parseMeta(raw.meta_v3) : null), [raw.meta_v3]);

  // si la versión elegida no tiene datos, cae a la primera que sí
  const available = VERSIONS.filter((v) => tracks[v.key]?.length);
  const active = tracks[version]?.length ? version : (available[0]?.key || version);
  const fullData = tracks[active] || [];
  const liveData = useMemo(() => liveSlice(fullData), [fullData]);
  const hasLiveSplit = !!liveData && fullData.some((d) => d.live === false);
  const useLive = hasLiveSplit && span === "live";
  const data = useLive ? liveData : fullData;
  const last = fullData.at(-1);   // estado de hoy: siempre del registro completo
  const color = VERSION_COLOR[active];
  const metrics = useMemo(() => computeMetrics(data, A.stableApy, A.costBps, useLive ? "first" : "account"), [data, A.stableApy, A.costBps, useLive]);
  const cmp = useMemo(() => compareSeries(Object.fromEntries(Object.entries(tracks).filter(([, v]) => v?.length))), [tracks]);

  const closes = useMemo(() => {
    const m = new Map();
    for (const k of ["v20", "v21", "v3"]) for (const d of tracks[k] || []) if (!m.has(d.date)) m.set(d.date, d.btc);
    return m;
  }, [tracks]);
  const trades21 = useMemo(() => new Map((tracks.v21 || []).map((d) => [d.date, d.tradePct])), [tracks.v21]);
  const sf = useMemo(() => (meta ? shortfall(meta, closes, trades21) : null), [meta, closes, trades21]);
  const h21 = useMemo(() => health(meta, tracks.v21), [meta, tracks.v21]);
  const h3 = useMemo(() => health(metaV3, tracks.v3), [metaV3, tracks.v3]);
  const hActive = active === "v3" ? h3 : h21;

  const sc = useMemo(() => {
    if (active === "v3") return scenariosV3(levels);
    return scenariosV21(levels, last?.weightReal, A.band);
  }, [active, levels, last, A.band]);
  const levelsStale = levels && last && levels.meta.date !== last.date;

  const stale = last ? daysStale(last.date) : null;
  const coneKey = active === "v3" ? "v3" : "v21";
  const v3Live = useMemo(() => firstLiveDate(tracks.v3), [tracks.v3]);
  const v3AllRec = !!tracks.v3?.length && tracks.v3.every((d) => d.live === false);
  const hasCash = data.some((d) => Number.isFinite(d.cash));

  function applySources() {
    const clean = Object.fromEntries(Object.entries(draft).map(([k, v]) => [k, (v || "").trim()]));
    setUrls(clean); saveUrls(clean); reload(clean);
  }

  return (
    <div className="btcd">
      <style>{STYLES}</style>

      {/* ------------------------------------------------ cabecera */}
      <div className="row" style={{ justifyContent: "space-between", alignItems: "flex-end", marginBottom: 14 }}>
        <div>
          <div className="eyebrow">seguimiento de tendencia · control de volatilidad · paper trading</div>
          <h1 className="display" style={{ fontSize: 30, fontWeight: 700, margin: "4px 0 0" }}>BTC Paper Trading</h1>
        </div>
        <div style={{ textAlign: "right", display: "grid", gap: 6, justifyItems: "end" }}>
          <div className="row" style={{ justifyContent: "flex-end" }}>
            {last && <Pill color={last.inMarket ? "var(--gold)" : "var(--muted)"}>● {last.inMarket ? "EN MERCADO" : "EN CASH"}</Pill>}
            <HealthBadge h={hActive} />
            {stale != null && stale > STALE_AFTER_DAYS && <Pill color="var(--sell)">● DATO VIEJO · {stale} d</Pill>}
          </div>
          <div className="sub">{loading ? "cargando…" : last ? `última vela ${last.date}${last.source ? ` · ${last.source}` : ""}` : "sin datos"}</div>
        </div>
      </div>

      <div className="row" style={{ justifyContent: "space-between", marginBottom: 14 }}>
        <div className="seg" role="group" aria-label="Versión">
          {VERSIONS.map((v) => (
            <button key={v.key} id={`ver-${v.key}`} aria-pressed={active === v.key} disabled={!tracks[v.key]?.length}
              onClick={() => setVersion(v.key)} title={tracks[v.key]?.length ? "" : "Sin datos: falta publicar la pestaña o aún no tiene filas"}>
              <span style={{ color: VERSION_COLOR[v.key] }}>●</span> {v.label}
            </button>
          ))}
        </div>
        <div className="row">
          <button className="btn ghost" onClick={() => reload()} disabled={loading}>{loading ? "Cargando…" : "Recargar"}</button>
          <button className="btn ghost" onClick={() => setShowSources(!showSources)} aria-expanded={showSources}>Fuentes de datos</button>
        </div>
      </div>

      {warnings.map((w, i) => (
        <div key={i} className="panel" style={{ borderColor: "var(--warn)", color: "var(--warn)", fontSize: 12, marginBottom: 10 }}>{w}</div>
      ))}

      {/* ------------------------------------------------ fuentes */}
      {showSources && (
        <div className="panel" style={{ marginBottom: 14 }}>
          <div className="eyebrow">Fuentes de datos</div>
          <div className="sub" style={{ marginBottom: 10 }}>
            En la planilla: Archivo → Compartir → Publicar en la web → elige cada pestaña → CSV → Publicar, y pega cada link aquí.
            Se guardan solo en este navegador; para que valgan en todos tus dispositivos, ponlos como variables en Vercel (ver README).
          </div>
          <div className="grid" style={{ gap: 10 }}>
            {SOURCE_DEFS.map((s) => {
              const st = status[s.key];
              const tag = !st ? "" : st.state === "ok" ? `✓ ${st.n} filas${st.as !== s.key ? ` (se usó como ${VERSION_NAME[st.as] || st.as})` : ""}` : st.state === "missing" ? "sin link" : `✗ ${st.msg}`;
              return (
                <label key={s.key} htmlFor={`src-${s.key}`} style={{ display: "grid", gap: 4, fontSize: 12 }}>
                  <span className="row" style={{ justifyContent: "space-between" }}>
                    <span>{s.label} · <code style={{ color: "var(--muted)" }}>{s.tab}</code></span>
                    <span style={{ color: st?.state === "ok" ? "var(--buy)" : st?.state === "error" ? "var(--sell)" : "var(--muted)" }}>{tag}</span>
                  </span>
                  <input type="url" id={`src-${s.key}`} value={draft[s.key] || ""} placeholder="https://docs.google.com/spreadsheets/d/e/…/pub?gid=…&single=true&output=csv"
                    onChange={(e) => setDraft({ ...draft, [s.key]: e.target.value })} />
                </label>
              );
            })}
          </div>
          <div className="row" style={{ marginTop: 12 }}>
            <button className="btn" onClick={applySources}>Guardar y cargar</button>
            <button className="btn ghost" onClick={() => { clearSavedUrls(); const u = loadUrls(); setDraft(u); setUrls(u); reload(u); }}>Volver a los links del build</button>
          </div>
        </div>
      )}

      {!last && !loading && (
        <div className="panel" style={{ padding: "32px 20px", textAlign: "center", marginBottom: 14 }}>
          <div className="display" style={{ fontSize: 17 }}>No hay datos cargados</div>
          <div className="sub" style={{ marginTop: 8 }}>Abre «Fuentes de datos» y pega al menos el CSV publicado de <code>track_record_v21</code>.</div>
        </div>
      )}

      {last && (
        <div className="grid">
          {/* ------------------------------------------------ hoy */}
          <div className="grid" style={{ gridTemplateColumns: "repeat(auto-fit,minmax(160px,1fr))" }}>
            <div className="panel">
              <div className="eyebrow">Precio BTC</div>
              <div className="metric-val" style={{ fontSize: 24, marginTop: 6 }}>{usd(last.btc)}</div>
              <div className="sub" style={{ color: last.dailyRet >= 0 ? "var(--buy)" : "var(--sell)" }}>{last.dailyRet >= 0 ? "▲" : "▼"} {pct(Math.abs(last.dailyRet), 2)} en la vela</div>
            </div>
            <div className="panel">
              <div className="eyebrow">Decisión del último cierre</div>
              <div className="metric-val" style={{ fontSize: 24, marginTop: 6, color: actionColor(last.action) }}>{actionLabel(last.action)}</div>
              <div className="sub">objetivo {pct(last.target, 0)}{Math.abs(last.tradePct) > 1e-9 ? ` · operó ${pct(last.tradePct, 1)}` : ""}</div>
            </div>
            <div className="panel" style={{ display: "flex", flexDirection: "column", justifyContent: "center" }}>
              <WeightGauge real={last.weightReal} signal={last.signal} />
            </div>
            <div className="panel">
              <div className="eyebrow">Señal</div>
              <div style={{ fontSize: 13, marginTop: 8, lineHeight: 1.7 }}>
                {active === "v3"
                  ? <div>plazos al alza <span style={{ color: "var(--gold)" }}>{Math.round(last.trend * 4)} de 4</span><div className="sub">100% con 3 o más</div></div>
                  : <>
                      <div>tendencia <span style={{ color: "var(--gold)" }}>{num(last.trend, 2)}</span></div>
                      <div>vol scalar <span style={{ color: "var(--steel)" }}>{num(last.volScalar, 2)}</span></div>
                    </>}
              </div>
            </div>
          </div>

          <FlipPanel sc={sc} version={active === "v3" ? "v3" : "v21"}
            note={[active === "v20" ? "v2.0 usa la misma señal que v2.1." : "", levelsStale ? `Ojo: los niveles son del ${levels.meta.date} y el registro llega al ${last.date}.` : ""].filter(Boolean).join(" ")} />

          <div className="two">
            <HealthPanel title="Salud de las corridas · v2.1" h={h21} />
            <HealthPanel title="Salud de las corridas · V3" h={h3} />
          </div>

          {hasLiveSplit && (
            <div className="row">
              <div className="seg" role="group" aria-label="Tramo del registro">
                <button id="span-all" aria-pressed={!useLive} onClick={() => setSpan("all")}>Todo el registro</button>
                <button id="span-live" aria-pressed={useLive} onClick={() => setSpan("live")}>Solo en vivo</button>
              </div>
              <span className="sub">{useLive ? (liveData.length > 1 ? `Desde ${liveData[1].date}: métricas y gráficos rebasados al cierre anterior.` : "Aún no hay días en vivo.") : "Incluye filas reconstruidas (antes de que la versión existiera)."}</span>
            </div>
          )}
          {useLive && liveData.length < 2 ? (
            <div className="panel sub">Todavía no cierra la primera vela en vivo de esta versión. Mientras tanto, mira «Todo el registro».</div>
          ) : <>
          <EquityChart data={data} rebase={useLive ? "first" : "account"} cone={active === "v20" ? null : cone} coneKey={coneKey} hasCash={hasCash} color={color}
            liveStart={active === "v3" ? v3Live : null} allReconstructed={active === "v3" && v3AllRec} />
          <CompareChart cmp={cmp} liveStart={v3Live} />
          <div className="two">
            <DrawdownChart data={data} color={color} />
            <ExposureChart data={data} color={color} />
          </div>

          {/* ------------------------------------------------ métricas */}
          {metrics && (
            <div>
              <div className="grid" style={{ gridTemplateColumns: "repeat(auto-fit,minmax(140px,1fr))" }}>
                <Metric label="Ventaja vs HODL" value={pct(metrics.vsHodl, 2)} sub={`capital relativo: ${num(1 + metrics.totalStrat, 3)}× vs ${num(1 + metrics.totalHodl, 3)}×`} accent={metrics.vsHodl >= 0 ? "var(--buy)" : "var(--sell)"} />
                <Metric label="Retorno total" value={pct(metrics.totalStrat, 2)} sub={`HODL ${pct(metrics.totalHodl, 2)} · incluye el costo de entrada`} accent={color} />
                <Metric label="Contra cash" value={pct(metrics.excessOverCash, 2)} sub={`cash ${pct(metrics.cashTotal, 2)} · ${num(A.stableApy * 100, 1)}% anual supuesto`} accent={metrics.excessOverCash >= 0 ? "var(--buy)" : "var(--sell)"} />
                <Metric label="Máxima caída" value={pct(metrics.maxDD, 2)} sub={`HODL ${pct(metrics.hodlMaxDD, 2)}`} accent="var(--sell)" />
                <Metric label="Exposición media" value={pct(metrics.avgExposure, 0)} sub={`en BTC · con algo de BTC el ${pct(metrics.inMarketShare, 0)} de ${metrics.days} días`} />
                <Metric label="Operaciones" value={metrics.trades} sub={`${num(metrics.trades / metrics.days * 365, 0)} al año · turnover ${num(metrics.turnover, 2)}×`} />
                <Metric label="Costo acumulado" value={bps(metrics.costBps)} sub={`del capital inicial · a ${RETAIL_BPS} pb (retail) serían ${bps(metrics.retailCostBps)}`} />
                <Metric label="Sharpe" value={metrics.sharpe == null ? "—" : num(metrics.sharpe, 2)} sub={metrics.enough ? "exceso sobre cash, anualizado" : `requiere ${MIN_DAYS_ANNUALIZED} d · hay ${metrics.days}`} />
                <Metric label="Calmar" value={metrics.calmar == null ? "—" : num(metrics.calmar, 2)} sub={metrics.enough ? "CAGR / máxima caída" : `requiere ${MIN_DAYS_ANNUALIZED} d · hay ${metrics.days}`} />
              </div>
              <div className="sub" style={{ marginTop: 8 }}>
                Supuestos, no observaciones: cash al {num(A.stableApy * 100, 1)}% anual y {num(A.costBps, 0)} pb por unidad de turnover
                {A.fromSheet ? " (leídos de la planilla)" : " (valores por defecto: falta next_levels)"}. Un exchange retail cobra 25–60 pb. Los ratios anualizados se ocultan bajo {MIN_DAYS_ANNUALIZED} días porque son ruido.
              </div>
            </div>
          )}
          </>}

          <ExecutionPanel sf={sf} />

          {/* ------------------------------------------------ decisiones */}
          <div className="panel">
            <div className="eyebrow" style={{ marginBottom: 10 }}>Decisiones recientes · {VERSION_NAME[active]}</div>
            <div className="scroll">
              <table>
                <thead><tr>{["Fecha", "BTC", "Tendencia", "Objetivo", "Señal", "Real", "Decisión", "Costo", "Capital"].map((h) => <th key={h}>{h}</th>)}</tr></thead>
                <tbody>
                  {[...data].slice(-14).reverse().map((d) => (
                    <tr key={d.date}>
                      <td>{d.date}{d.live === false ? <span className="sub" title="fila reconstruida"> · rec.</span> : ""}</td>
                      <td>{usd(d.btc)}</td>
                      <td style={{ color: "var(--gold)" }}>{num(d.trend, 2)}</td>
                      <td>{pct(d.target, 0)}</td>
                      <td>{pct(d.signal, 0)}</td>
                      <td style={{ color: "var(--muted)" }}>{pct(d.weightReal, 1)}</td>
                      <td style={{ textAlign: "left", color: actionColor(d.action) }}>{actionLabel(d.action)}</td>
                      <td style={{ color: "var(--muted)" }}>{d.tradeCost > 0 ? `${num(d.tradeCost * 1e4, 1)} pb` : "—"}</td>
                      <td>{num(d.strat, 4)}×</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}

      <div className="sub" style={{ textAlign: "center", marginTop: 18 }}>Paper trading · no es recomendación de inversión</div>
    </div>
  );
}

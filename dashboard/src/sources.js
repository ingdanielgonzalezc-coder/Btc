/* sources.js — qué pestañas publicadas lee el dashboard y de dónde sale cada link.
   Prioridad: lo que el usuario guardó en este navegador > variables VITE_* del build. */
import Papa from "papaparse";
import { detectKind } from "./lib.js";

const env = import.meta.env || {};

export const SOURCE_DEFS = [
  { key: "v21", kind: "v21", label: "Registro v2.1 (oficial)", tab: "track_record_v21", env: env.VITE_CSV_V21 || env.VITE_CSV_URL || "" },
  { key: "v3", kind: "v3", label: "Registro V3 (challenger)", tab: "track_record_v3", env: env.VITE_CSV_V3 || "" },
  { key: "v20", kind: "v20", label: "Registro v2.0 (legado)", tab: "track_record", env: env.VITE_CSV_V20 || "" },
  { key: "meta", kind: "meta", label: "Corridas de v2.1", tab: "meta_runs", env: env.VITE_CSV_META || "" },
  { key: "meta_v3", kind: "meta", label: "Corridas de V3", tab: "meta_runs_v3", env: env.VITE_CSV_META_V3 || "" },
  { key: "levels", kind: "levels", label: "Precios de giro", tab: "next_levels", env: env.VITE_CSV_LEVELS || "" },
];

const LS_KEY = "btc-dashboard-sources";

export function loadUrls() {
  let saved = {};
  try { saved = JSON.parse(localStorage.getItem(LS_KEY) || "{}") || {}; } catch { saved = {}; }
  const out = {};
  for (const s of SOURCE_DEFS) out[s.key] = (saved[s.key] ?? s.env ?? "").trim();
  return out;
}

export function saveUrls(urls) {
  try { localStorage.setItem(LS_KEY, JSON.stringify(urls)); return true; } catch { return false; }
}

export function clearSavedUrls() {
  try { localStorage.removeItem(LS_KEY); } catch { /* sin almacenamiento */ }
}

async function fetchCsv(url) {
  const res = await fetch(url, { cache: "no-store" });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  const parsed = Papa.parse(await res.text(), { header: true, skipEmptyLines: true });
  return { rows: parsed.data, kind: detectKind(parsed.meta.fields) };
}

/* Carga todas las fuentes en paralelo. Un link que resulta ser otra pestaña de
   registro (p. ej. el de v2.1 apunta a la pestaña v2.0) se reasigna a la pestaña
   que realmente es, con un aviso: así un VITE_CSV_URL viejo no rompe nada. */
export async function loadAll(urls) {
  const results = await Promise.allSettled(
    SOURCE_DEFS.map((s) => (urls[s.key] ? fetchCsv(urls[s.key]) : Promise.resolve(null))),
  );
  const data = {}, status = {}, warnings = [];
  SOURCE_DEFS.forEach((s, i) => {
    const r = results[i];
    if (!urls[s.key]) { status[s.key] = { state: "missing" }; return; }
    if (r.status === "rejected") { status[s.key] = { state: "error", msg: r.reason?.message || "error" }; return; }
    const { rows, kind } = r.value;
    if (kind === "unknown") { status[s.key] = { state: "error", msg: "no reconozco las columnas de esta pestaña" }; return; }
    let slot = s.key;
    if (kind !== s.kind) {
      const isTrack = ["v21", "v3", "v20"].includes(kind);
      if (isTrack && !data[kind]) {
        slot = kind;
        const real = SOURCE_DEFS.find((d) => d.key === kind);
        warnings.push(`El link de «${s.label}» es la pestaña ${real.tab}; lo muestro como ${real.label}. Publica ${s.tab} y pega ese link en Fuentes de datos.`);
      } else {
        status[s.key] = { state: "error", msg: `esta pestaña no es ${s.tab}` }; return;
      }
    }
    data[slot] = rows;
    status[s.key] = { state: "ok", n: rows.length, as: slot };
  });
  return { data, status, warnings };
}

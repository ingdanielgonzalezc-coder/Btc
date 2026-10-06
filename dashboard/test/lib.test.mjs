// Tests de la lógica del dashboard. Correr: cd dashboard && npm test  (node --test, sin dependencias)
import test from "node:test";
import assert from "node:assert/strict";
import * as L from "../src/lib.js";

const near = (a, b, eps = 1e-9) => assert.ok(Math.abs(a - b) < eps, `${a} != ${b}`);

test("escenario v2.1: el sentido se decide contra el peso real (50% señal, 80% real, 67,5% objetivo)", () => {
  const lv = { meta: { price: 100, date: "2026-10-05" }, v21: { signal: 0.5, vol_scalar: 0.9,
    L20_ref: 50, L60_ref: 60, L120_ref: 70, L250_ref: 200, L20_state: 1, L60_state: 1, L120_state: 1, L250_state: 0 } };
  const sc = L.scenariosV21(lv, 0.8);
  const now = sc.rows.find((r) => (r.lo == null || 100 > r.lo) && (r.hi == null || 100 <= r.hi));
  near(now.target, 0.675);
  assert.equal(now.action, "VENDER");
});

const flat = [
  { date: "2026-10-06", btc: 100, tradePct: 0.5, tradeCost: 0.00035, strat: 0.99965, hodl: 0.9993, cash: 1, weightReal: 0.5, inMarket: true },
  { date: "2026-10-07", btc: 100, tradePct: 0, tradeCost: 0, strat: 0.99965, hodl: 0.9993, cash: 1, weightReal: 0.5, inMarket: true },
];

test("retorno total incluye el costo de entrada (precio plano)", () => {
  near(L.computeMetrics(flat, 0, 7).totalStrat, -0.00035, 1e-12);
});

test("caída máxima: tarjeta y gráfico coinciden", () => {
  const card = L.computeMetrics(flat, 0, 7).maxDD;
  const chart = Math.min(...L.withDrawdowns(flat).map((d) => d.ddStrat));
  near(card, chart, 1e-12);
  near(card, -0.00035, 1e-12);
});

test("costo retail en la misma base que el costo actual", () => {
  const m = L.computeMetrics(flat, 0, 7);
  near(m.costBps, 3.5, 1e-9);
  near(m.retailCostBps, 3.5 * 40 / 7, 1e-9);
});

test("ejecución: una operación, una corrida repetida y una fallida cuentan como UNA operación", () => {
  const meta = L.parseMeta([
    { run_at_utc: "2026-10-07 05:00:00", last_candle: "2026-10-06", consistency: "OK (0/1)", rows_added: "1", spot_price: "101" },
    { run_at_utc: "2026-10-07 06:00:00", last_candle: "2026-10-06", consistency: "OK (1/1)", rows_added: "0", spot_price: "102" },
    { run_at_utc: "2026-10-07 07:00:00", last_candle: "2026-10-06", consistency: "FORK (3 celdas)", rows_added: "0", spot_price: "103" },
  ]);
  const sf = L.shortfall(meta, flat);
  assert.equal(sf.nTrades, 1);
  near(sf.tradeMeanCost, 0.01, 1e-12);       // compra con spot 1% sobre el cierre
  assert.equal(sf.n, 1);                      // una vela de mercado, no tres corridas
});

test("ejecución: fila escrita por gap-fill no se atribuye a una corrida ajena", () => {
  const meta = L.parseMeta([{ run_at_utc: "2026-10-08 05:00:00", last_candle: "2026-10-07", consistency: "OK (0/2)", rows_added: "2", spot_price: "99" }]);
  const sf = L.shortfall(meta, flat);
  assert.equal(sf.nTrades, 0);
  assert.equal(sf.unmatched, 1);
});

test("comparación en vivo: recorta todas las series desde la base del tramo", () => {
  const t = (vals) => vals.map(([date, strat]) => ({ date, strat, btc: 1 }));
  const cmp = L.compareSeries({ v21: t([["2026-10-01", 1], ["2026-10-05", 1.1], ["2026-10-06", 1.2]]),
                               v3: t([["2026-10-01", 1], ["2026-10-05", 1.0], ["2026-10-06", 1.05]]) }, "2026-10-05");
  assert.equal(cmp.start, "2026-10-05");
  assert.equal(cmp.rows[0].date, "2026-10-05");
  near(cmp.rows.at(-1).v21, 1.2 / 1.1);
});

test("fechas d/m/aaaa de la pestaña v2.0 quedan en orden", () => {
  assert.deepEqual(L.normalizeDates(["30/9/2026", "1/10/2026"]), ["2026-09-30", "2026-10-01"]);
});

test("registro de ejecución: separa versiones y mide la brecha contra el teórico", () => {
  const rows = [
    { date: "2026-10-05", version: "v21", btc_close: "100", exec_price: "101", equity_close: "1.10", hodl_close: "1.2", weight_close: "0.5", target_weight: "0.5", trade_pct: "0", trade_cost: "0", live: "0" },
    { date: "2026-10-05", version: "v3", btc_close: "100", exec_price: "101", equity_close: "0.98", hodl_close: "1.2", weight_close: "1", target_weight: "1", trade_pct: "0", trade_cost: "0", live: "0" },
  ];
  const x = L.parseExec(rows);
  assert.equal(x.v21x.length, 1); assert.equal(x.v3x.length, 1);
  const g = L.execGap([{ date: "2026-10-05", strat: 1.0 }, { date: "2026-10-06", strat: 1.2 }], x.v3x);
  assert.equal(g.date, "2026-10-05"); near(g.gap, -0.02);
});

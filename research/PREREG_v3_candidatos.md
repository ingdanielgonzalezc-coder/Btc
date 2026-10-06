# Pre-registro de candidatos V3 (escrito antes de mirar OOS) — 2026-10-06
Datos: Bitstamp BTC/USD, cierre 00:00 UTC. IS = 2014-01-01..2021-12-31. OOS = 2022-01-01..2026-10-05.
Costo base 15 bps por unidad de turnover (maker global 10 bps + 5 bps slippage). Cash 0% (histórico).
Long-only spot, cap 1.0, sin apalancamiento. Ejecución al cierre de la señal (convención v2.1).
C0 v2.1 congelada (voto binario 4 plazos × vol-target 50%, banda 0.10 sobre `held`, rebalanceo al cambiar señal)
C1 Señal continua: media de Φ(z_L), z_L = log(P_t/P_{t-L})/(σ_d·√L), L∈{20,60,120,250} × vol-target 50%; rebalanceo cuando |objetivo − peso real| > 0.10, al objetivo
C2 = C1 pero operando solo hasta el borde de la banda (región de no-trade, Gârleanu–Pedersen)
C3 = C0 con rebalanceo semanal (solo lunes)
C4 Ensemble Donchian (entrada: cierre > máximo N previo; salida: cierre < mínimo N/2 previo), N∈{20,60,120,250} × vol-target 50%, banda 0.10 sobre peso real
C5 = C0 sin el plazo de 20 días (60,120,250)
Regla de selección: mayor Sharpe IS neto de costos entre C1..C5, con turnover ≤ C0 y MaxDD IS no peor que C0 − 5 pp.
Luego: OOS una sola vez, bootstrap pareado vs C0, Sharpe deflactado con N=6.

# Especificación V3 — BTC Paper Trading (challenger)

**Estado:** propuesta, pendiente de congelar
**Relación con v2.1:** corre en paralelo; v2.1 sigue siendo el registro oficial.
**Nombre:** en la convención de `ESPECIFICACION_v2.1.md` esta versión es la familia
"tendencia + histéresis" reservada como v4.0. Se llama V3 por decisión del dueño;
el linaje ML (v3.0 en la spec anterior) queda sin número asignado.

---

## 1. Por qué existe

Selección pre-registrada (`research/PREREG_v3_candidatos.md`) entre 5 rediseños de v2.1,
elegida con datos 2014–2021 y evaluada una sola vez en 2022–2026 (Bitstamp, 15 pb, cash 0%).

| Métrica 2022–2026 | v2.1 | V3 |
|---|---|---|
| Sharpe | 0,86 | 0,78 |
| CAGR | 22,0% | 16,7% |
| MaxDD | −26,9% | −20,9% |
| Operaciones/año | 67 | 27 |
| Turnover/año | 15,8× | 6,0× |
| Exposición media | 0,51 | 0,38 |

Diferencia de Sharpe −0,07, IC 95% bootstrap pareado [−0,36, +0,21]: **no es mejor en
retorno ajustado por riesgo**. Lo que ofrece: 62% menos turnover, 6 pp menos de drawdown,
y supera a v2.1 cuando el costo real es ≥ 50 pb por unidad de turnover.

## 2. Señal (congelada al lanzar)

```python
for N in (20, 60, 120, 250):
    entra si close_t > max(close_{t-N..t-1})
    sale  si close_t < min(close_{t-M..t-1}),  M = max(N/2, 5)
donchian_score = promedio de los 4 estados
vol_scalar     = min(1, 0.50 / (ret.ewm(span=30).std() * sqrt(365)))   # = v2.1
target         = clip(donchian_score * vol_scalar, 0, 1)
```

Estados path-dependent, recomputados desde `PAPER_START_V3 − 420 días` en cada corrida.

## 3. Contabilidad

Idéntica a v2.1 §4 (units + cash, arranque desde cash, sin rebase, sin apalancamiento,
ejecución al cierre, mismo `FEE + SLIP = 7 pb` y `STABLE_APY = 4%` para comparar like-for-like),
**salvo el rebalanceo**: se opera cuando `|target − peso real| > 0.10`, al target completo.

Conocido y aceptado: una posición residual < 10% puede quedar abierta con target 0, y un
target < 10% desde cero no se compra (46 de 4.661 días en 2014–2026).

## 4. Columnas (`track_record_v3`)

Las de v2.1, más `d20 d60 d120 d250` (estado de cada canal), `donchian_score`,
`next_buy_above` y `next_sell_below`: los cierres de mañana que encienden o apagan al
menos un canal. Se conocen hoy y son la base del panel "precios de giro" del dashboard.

## 5. Comparación pre-registrada contra v2.1

- Métrica primaria: diferencia de Sharpe diaria, bootstrap estacionario pareado (bloque 20 d).
- Se revisa una vez al año desde `PAPER_START_V3`. Ningún cambio antes de 3 años.
- V3 reemplaza a v2.1 solo si el IC 95% de la diferencia excluye 0 a favor de V3, **o**
  si el costo real medido (fills reales) supera 40 pb por unidad de turnover.
- Con tracking error ~10% anual, detectar 5 pp/año de diferencia toma ~15 años:
  lo esperable es que el criterio estadístico no se cumpla, y la decisión la tome el costo.

## 6. Secuencia de lanzamiento

1. Tests en verde (`pytest -q`, 67 tests).
2. Commit + push de esta spec, `engine_v3.py`, `daily_run_v3.py`, `research/`.
3. Verificar que `PAPER_START_V3` sea **posterior** al push (por defecto 2026-10-12).
4. Primera corrida. Sin backfill.

# Especificación V3 — BTC Paper Trading: todo o nada

**Estado:** congelada al primer push
**Relación con v2.1:** corre en paralelo; v2.1 sigue siendo el registro oficial.
**Reemplaza:** a la V3 Donchian (2026-10-06), que nunca escribió una fila.

---

## 1. Objetivo

Maximizar el capital final. Se aceptan caídas mayores que v2.1 a cambio de estar
completo en BTC cuando la tendencia es clara.

## 2. Regla (congelada)

```python
votos_t = Σ_{L in (20, 60, 120, 250)} [P_t > P_{t-L}]     # el trend_score de v2.1 × 4
objetivo_t = 1 si votos_t >= 3, si no 0
```

Se opera solo cuando el objetivo cambia (0 ↔ 1), al cierre de la señal.
Sin vol-targeting, sin banda, sin apalancamiento.

## 3. Contabilidad

La de v2.1 §4: units + cash, arranque desde cash, sin rebase, ejecución al cierre,
`FEE + SLIP = 7 pb` y cash a 4% anual, para comparar like-for-like.

## 4. Evidencia (Bitstamp, 15 pb, cash 0%)

| Desde 2014 | V3 todo/nada | v2.1 | HODL |
|---|---|---|---|
| Capital final | 486× | 118× | 114× |
| Peor caída | −60% | −41% | −83% |
| Ventanas de 4 años en que gana a HODL | 97% | — | — |
| Operaciones al año | 17 | 65 | 0 |

- Robusto a 1 día de atraso (368×) y a 50 pb de costo (227×); pierde contra HODL a 100 pb.
- Sensible a los plazos: con combinaciones vecinas da entre 92× y 813× (mediana ~280×).
  Los plazos 20/60/120/250 vienen de v2.0, no de la búsqueda.
- Elegir cada año la "mejor" de 147 reglas rinde menos (147× desde 2017) que esta regla fija (224×).

## 5. Registro reconstruido

`PAPER_START_V3 = 2026-08-17` (igual que v2.1) para compararlas en el mismo gráfico.
Las filas con fecha anterior a `LIVE_FROM_V3 = 2026-10-06` se calcularon después de los
hechos y llevan `live = 0`. Son deterministas (los mismos precios dan las mismas filas),
pero **no son evidencia forward**: la comparación honesta empieza en `LIVE_FROM_V3`.
Si el push ocurre después del 7 de octubre de 2026 (UTC), mover `LIVE_FROM_V3` a la
primera vela posterior al push en el mismo commit.

En el tramo reconstruido (17-ago a 5-oct) V3 hizo +3,2%, contra +14,4% de v2.1 y +32,9% de
HODL: entró tarde al rally y operó 7 veces en un mercado lateral. 50 días no dicen nada
sobre la regla; se deja escrito para que nadie lo descubra después y quiera ajustar.

## 6. Comparación contra v2.1

Revisión anual desde `LIVE_FROM_V3`. Métrica primaria: capital final relativo, y peor caída
como restricción (no peor que −70%). Ningún cambio de regla antes de 4 años (un ciclo).

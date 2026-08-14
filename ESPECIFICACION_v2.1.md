# Especificación v2.1 — BTC Paper Trading

**Estado:** propuesta, pendiente de congelar
**Predecesor:** v2.0 (commit `a427e09`, registro 2026-06-06 → 2026-07-15, archivado)
**Invariante central:** la señal es **bit-idéntica** a v2.0. Solo cambia la contabilidad y la infraestructura.

---

## 1. Propósito

v2.1 es el **baseline de referencia** del experimento: la vara honesta contra la cual se medirá v3.0 (ML) en un test forward pre-registrado. Su objetivo no es rendir bien, es ser simple, congelado y auditable.

v2.1 existe porque el registro de v2.0 quedó contaminado: procedencia del tramo inicial no demostrable, cambio de fuente de precio a mitad del periodo (2026-06-21), dependencias sin congelar, sin procedencia por fila. Los defectos eran de integridad del registro, no de la estrategia — por eso la señal no cambia.

---

## 2. Convención de versionado

**El entero cambia solo si cambia la señal. El decimal nunca la toca.**

| Versión | Señal | Contabilidad | Held-out requerido |
|---|---|---|---|
| v2.0 | tendencia + vol-targeting | original (con defectos) | ya validada (2022–2026) |
| v2.1 | **idéntica a v2.0** | corregida | no — la señal no cambió |
| v3.0 | ML (linaje separado) | propia | sí, tras corregir sus 6 bugs |
| v4.0 | tendencia + histéresis | la de v2.1 | sí, obligatorio |

---

## 3. Capa 1 — Señal (CONGELADA, sin un solo cambio)

Se computa sobre la serie **completa** descargada (warmup incluido), exactamente como en v2.0:

```python
ret        = precios.pct_change()
trend      = mean_{L in (20,60,120,250)} (precios > precios.shift(L)).astype(float)
vol        = ret.ewm(span=30).std() * sqrt(365)          # adjust=True (default)
vol_scalar = (0.50 / vol).clip(upper=1.0)
target     = (trend * vol_scalar).clip(0.0, 1.0).fillna(0.0)

held, w = 0.0, []                                        # banda de no-trade
for tw in target.values:
    if abs(tw - held) > 0.10:                            # > estricto, NO >=
        held = tw
    w.append(held)
signal_weight = pd.Series(w, index=precios.index)
```

Después: `df = df.iloc[max(LOOKBACKS):]` (descarte de warmup por posición).

**Detalles que deben preservarse literalmente**, porque alterarlos cambia la señal:

- `held` inicializa en `0.0` y el loop arranca en el inicio de la serie **descargada**, no en `PAPER_START`.
- `ewm(span=30)` con `adjust=True` (default de pandas) — la ponderación depende de dónde empieza la serie.
- Comparación `>` estricta en la banda: un salto de exactamente 0.10 **no** dispara.
- `precios > precios.shift(L)` devuelve `False`, no `NaN`, en el warmup — de ahí el descarte por posición.

**Consecuencia operativa:** `PAPER_START_V21` y `WARMUP_DAYS = 420` quedan congelados en el momento del lanzamiento. Moverlos altera la trayectoria de `held` y de la EWMA, y por tanto la señal pasada.

---

## 4. Capa 2 — Contabilidad (NUEVA)

Corrige tres defectos estructurales de v2.0: posición heredada gratis del warmup, rebase que borra el día 1, y peso teórico que nunca deriva con el precio.

### 4.1 Estado

Tres variables, recomputadas desde cero en cada corrida:

- `units` — unidades de BTC
- `cash` — saldo en efectivo
- `equity = units × price + cash`

La contabilidad corre **solo sobre el tramo `>= PAPER_START_V21`**, no sobre el warmup. Este es el cambio que elimina la posición heredada: la cuenta nace en cash el día 0, sin importar qué decía la señal antes.

### 4.2 Día 0 (`PAPER_START_V21`)

La cuenta se funda con equity = 1.0, 100% cash, y ejecuta la señal del cierre del día 0.

```python
units, cash = 0.0, 1.0
eq_pre, w_pre = 1.0, 0.0

dv    = signal_weight[0] * eq_pre                  # valor a comprar
cost  = abs(dv) * (FEE + SLIP)
units = dv / price[0]
cash  = cash - dv - cost
equity[0] = units*price[0] + cash                  # = 1 - cost
```

`equity[0] ≤ 1.0`, no exactamente 1.0. **No hay rebase.** Si la señal del día 0 es 0, no hay costo y `equity[0] = 1.0`. El retorno de BTC del día 0 **no** se gana: se compró al cierre.

### 4.3 Día t ≥ 1

```python
cash   = cash * (1 + cash_d)                       # devengo del día
eq_pre = units*price[t] + cash                     # mark-to-market al cierre de hoy
w_pre  = units*price[t] / eq_pre                   # peso REAL, ya derivado

if abs(signal_weight[t] - signal_weight[t-1]) > 1e-12:      # la señal cambió
    dv    = signal_weight[t]*eq_pre - units*price[t]
    cost  = abs(dv) * (FEE + SLIP)
    units = units + dv/price[t]
    cash  = cash - dv - cost
else:
    dv, cost = 0.0, 0.0                            # dejar derivar, sin tocar

equity[t]     = units*price[t] + cash
weight_post[t]= units*price[t] / equity[t]
trade_pct[t]  = dv / eq_pre
```

**No-lookahead:** las `units` de ayer valoradas al precio de hoy capturan el retorno de hoy. El trade de hoy se ejecuta al cierre de hoy y solo afecta de mañana en adelante. El costo se carga hoy.

### 4.4 Política de rebalanceo — decisión de diseño

Se rebalancea **únicamente cuando la señal congelada cambia**, nunca para corregir deriva.

La alternativa (rebalancear a `signal_weight` todos los días) generaría micro-trades diarios y costos que v2.0 nunca tuvo, y ningún operador real lo haría. Con esta política el número de trades de v2.1 es idéntico al de v2.0; lo único que difiere es el **tamaño**, que ahora incluye la deriva acumulada.

La deriva típica a `w = 0.25` con la volatilidad actual de BTC es ~0.34 pp/día, y crece con la exposición.

**La deriva jamás realimenta la banda.** El loop de la banda opera sobre `held` teórico, exactamente como v2.0. `signal_weight` es el objetivo; `weight_pre` es la realidad. Confundirlos cambiaría la señal.

---

## 5. Determinismo — requisito no negociable

v2.1 debe ser **recomputable bit-a-bit** desde `(serie de precios, código)`. Dos corridas distintas sobre los mismos precios producen filas idénticas.

La contabilidad es *stateful dentro del cómputo* pero **el estado nunca se persiste**: se reconstruye desde el día 0 en cada corrida. Esto es lo que distingue este diseño de un "modelo incremental" que guarda estado entre corridas — ese cambia un modo de falla detectable por uno irrecuperable.

**Corolario:** queda prohibido cualquier input que dependa del momento de ejecución. En particular, **la ejecución sigue siendo close-to-close**. Ejecutar al precio spot del momento de la corrida haría el registro no reproducible. El gap real de ejecución se mide aparte (§9).

---

## 6. Benchmarks

Tres curvas, todas arrancando en el día 0:

| Curva | Definición |
|---|---|
| `equity` | la estrategia |
| `hodl_equity` | compra BTC al cierre del día 0 pagando `FEE+SLIP` una vez, luego compone con `ret` |
| `cash_equity` | `(1 + cash_d)^t` |

HODL paga el costo de entrada deliberadamente: ambas estrategias nacen en cash, la comparación debe ser like-for-like. Son 7 bps una sola vez.

`cash_equity` es el benchmark que v2.0 no tenía y que resultó ser el más informativo: sobre el registro archivado, el trading activo aportó **−17.6 bps** contra cash puro.

---

## 7. Esquema de columnas (pestaña `track_record_v21`)

Nuevo esquema, congelado desde el lanzamiento. Las 13 columnas de v2.0 no aplican.

| # | Columna | Nota |
|---|---|---|
| 1 | `date` | ISO, una fila por día |
| 2 | `btc_price` | cierre 00:00 UTC de vela cerrada |
| 3 | `price_source` | `coinbase` \| `yfinance` — procedencia por fila |
| 4 | `trend_score` | señal |
| 5 | `vol_scalar` | señal |
| 6 | `target_weight` | señal, pre-banda |
| 7 | `signal_weight` | señal, post-banda — equivale a `new_weight` de v2.0 |
| 8 | `weight_pre` | peso real derivado, antes de ejecutar |
| 9 | `weight_post` | peso real tras ejecutar |
| 10 | `action` | COMPRAR / VENDER / MANTENER |
| 11 | `trade_pct` | `dv / eq_pre` |
| 12 | `trade_cost` | costo del día, fracción de equity |
| 13 | `units` | BTC tras ejecutar |
| 14 | `cash` | efectivo tras ejecutar |
| 15 | `equity` | `units × price + cash` |
| 16 | `daily_return` | retorno de BTC |
| 17 | `hodl_equity` | benchmark |
| 18 | `cash_equity` | benchmark |
| 19 | `drawdown` | sobre `equity` |
| 20 | `code_sha` | `GITHUB_SHA` de la corrida que escribió la fila |
| 21 | `generated_at_utc` | timestamp de escritura |

Columnas 3, 20 y 21 son las que resuelven el problema de procedencia que hundió a v2.0.

Escritura con `value_input_option="RAW"`.

---

## 8. Parámetros

**Congelados** (idénticos a v2.0, no re-optimizar):
`LOOKBACKS=(20,60,120,250)` · `TARGET_VOL=0.50` · `EWMA_SPAN=30` · `CAP=1.0` · `BAND=0.10` · `FEE=0.0004` · `SLIP=0.0003` · `STABLE_APY=0.04` · `ANN=365`

**Congelados al lanzar** (afectan la señal si se mueven):
`PAPER_START_V21` · `WARMUP_DAYS=420`

**Supuestos declarados, no observaciones:** el cash a 4% APY y los 7 bps por unidad de turnover (tier de alto volumen; el taker retail real está en 25–60 bps). Deben aparecer visibles en el dashboard.

---

## 9. Qué NO entra en v2.1

Rechazado explícitamente, para que no vuelva a discutirse:

- **Histéresis anti-whipsaw.** El paso mínimo de `trend_score` (0.25) supera la banda (0.10), así que la banda es ciega a los flips de tendencia. Confirmado en 58 días: 5 trades, 2 round trips completos, ambos perdedores (−0.05% y −3.33%), alpha vs cash −96 bps. Pero el held-out 2022–2026 que dio Calmar 1.03 **ya incluía este comportamiento**: el forward no reveló un defecto oculto, mostró el costo esperado en una muestra de 58 días en rango. Además la corrección apunta justo en la dirección que estos episodios sugieren, lo que la hace fitting sobre el forward disfrazado de mejora de diseño. Va a **v4.0**, validada en held-out antes de congelarse.
- **Cualquier cambio de parámetro** de la lista congelada.
- **Ejecución a precio distinto del cierre** — rompe el determinismo (§5).
- **Cambio de `STABLE_APY`** o de los supuestos de costo.

**Defectos conocidos que se documentan y no se corrigen:** la banda ciega a flips; el modelo no captura el gap real entre el cierre de señal (00:00 UTC) y la ejecución efectiva (cron 00:30+ UTC). Este último se **mide** en `meta_runs` registrando el precio spot al momento de correr, para tener la distribución empírica del implementation shortfall antes de considerar capital real — pero no entra al motor.

---

## 10. Tests obligatorios (bloquean la escritura al sheet)

| # | Test | Aserción |
|---|---|---|
| 1 | **Equivalencia de señal con v2.0** | sobre la serie de precios archivada, `trend_score`, `vol_scalar`, `target_weight`, `signal_weight` idénticos a v2.0 |
| 2 | Arranque desde cash | `units=0` y `cash=1` antes de ejecutar; `equity[0] = 1 − cost[0]` |
| 3 | Sin rebase | `equity[0] ≠ 1.0` cuando `signal_weight[0] > 0` |
| 4 | No-lookahead | el retorno de BTC del día 0 no aparece en `equity[0]` |
| 5 | Deriva sin trade | señal constante + movimiento de precio → `weight_pre ≠ signal_weight`, `trade_pct = 0` |
| 6 | Identidad de equity | `equity == units*price + cash` a 1e-12 en toda fila |
| 7 | Determinismo | dos corridas sobre los mismos precios → salida idéntica |
| 8 | Salida completa | señal → 0 implica `units == 0` |
| 9 | Banda exacta | salto de 0.10 no dispara; 0.1001 sí |
| 10 | `new_rows` idempotente | segunda corrida sin velas nuevas → 0 filas |
| 11 | `verify_consistency` | casos match / mismatch / fecha faltante |
| 12 | Serie desordenada | entrada desordenada → salida ordenada o error explícito |

El test 1 es el que **prueba** que la señal no cambió. Es la razón por la que el held-out de v2.0 (Calmar 1.03, Sharpe 0.92, MaxDD −24%) sigue siendo válido para v2.1 sin re-correrlo.

---

## 11. Impacto medido sobre el registro archivado

Simulando la contabilidad v2.1 sobre los precios de v2.0 (58 días, 6-jun → 2-ago):

| | v2.0 | v2.1 |
|---|---|---|
| Equity final | −0.3500% | −0.3695% |
| Costo total | 8.750 bps | 8.710 bps |
| MaxDD | −1.332% | −1.347% |
| Deriva máx. sin trade | n/a | 0.00428 |

Las diferencias siguen siendo pequeñas (−1.94 bps de equity), pero **crecieron con la exposición**: con 7.5% de tiempo en mercado (primeros 40 días) el delta era ~0 y la deriva 0.00076; con 32.8% (58 días) el delta es −1.94 bps y la deriva 0.00428. Esa es exactamente la relación esperada.

Las correcciones son por **corrección estructural**, no para cambiar resultados. Su efecto escala con la exposición sostenida, que es el régimen donde se acumulará el track record. Esto calibra expectativas; no es un argumento contra los cambios.

### Fixture de precios — requisito para el test 1

El CSV archivado contiene **solo los precios forward** (58 filas desde `PAPER_START`). El test de equivalencia de señal necesita la serie **completa con warmup** (~420 días previos), porque `trend_score` en el día 0 depende de precios de abril 2025 y la trayectoria de `held` arranca en el inicio de la descarga.

Antes de tocar nada, ejecutar una corrida que vuelque la serie cruda a `data/prices_snapshot_YYYYMMDD.csv` y commitearla. Ese archivo es el fixture real del test 1 y además congela los datos contra futuras revisiones de velas por parte de Coinbase.

---

## 12. Secuencia de lanzamiento

El orden importa: es lo que hace demostrable la procedencia.

1. Implementar motor v2.1 + infraestructura (deps pineadas, `RAW`, guarda de consistencia, `meta_runs`, dashboard ordenado).
2. Suite de tests en verde.
3. Commitear `SISTEMA_v2.1.md`, esta spec y `PREREGISTRO_comparacion_v3.md`.
4. `git tag -s motor-v2.1-frozen`.
5. **Recién ahí**, fijar `PAPER_START_V21` en una fecha **posterior** al push y commitear.
6. Primera corrida.

El commit precede al inicio del registro, con el timestamp de GitHub como testigo. **Sin backfill de un solo día.**

**v2.0 sigue corriendo en paralelo** en su pestaña, con su motor intacto. Mismo fetch, dos motores, dos pestañas. Esto da un A/B controlado del impacto real de las correcciones de contabilidad y elimina para siempre la tentación de reiniciar.

Archivar el CSV actual como `data/track_record_v20_archive.csv` — es el fixture de regresión del test 1.

---

## 13. Compromiso anti-reinicio

**Este es el último reinicio.**

A partir de `PAPER_START_V21`, todo defecto que se descubra se documenta como defecto conocido y se corrige en una versión nueva que corre **en paralelo**, nunca reiniciando el registro vigente.

El modo de falla que esta regla previene no es técnico sino psicológico: siempre aparecerá otro defecto, y si la regla implícita es "reinicio cuando encuentro algo", nunca se acumula evidencia — que es el único propósito de todo este sistema.

La disciplina no es "el código es perfecto". Es "el código está versionado, congelado y sus defectos están escritos".

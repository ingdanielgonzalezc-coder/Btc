# Registro de ejecución atrasada (`track_record_exec`)

**Qué es:** las mismas señales congeladas de v2.1 y V3, ejecutadas al precio de apertura de
la vela horaria de Coinbase de las **05:00 UTC del día siguiente** (mediana real del cron),
en vez de al cierre de las 00:00 UTC. No reemplaza a ningún registro oficial.

**Por qué:** el cierre no estaba disponible cuando se conoció la señal. En el backtest
2014–2026, ejecutar a las 05:00 baja V3 de 483× a 363× y deja a v2.1 (102×) bajo HODL (112×).

**Orden por fila D:** (1) marca al cierre D con las tenencias previas → `equity_close`;
(2) a las 05:00 UTC de D+1, si la señal cambió, opera a `exec_price` → `trade_*`, `units`,
`cash`, `equity_post`. Una fila existe solo cuando su vela horaria ya abrió (va ~1 día atrás).

**Reproducible:** las velas horarias se re-descargan; el registro se recomputa desde
2026-08-17 en cada corrida y pasa la misma guarda de consistencia (clave fecha + versión).
Un hueco en las velas horarias aborta sin escribir. Filas antes de 2026-10-06: `live = 0`.

**HODL comparable:** compra en la ejecución del día 0 pagando el mismo costo.
**Costos y cash:** 7 pb y 4% anual, como los registros oficiales.

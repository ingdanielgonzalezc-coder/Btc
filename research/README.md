# research/ — evidencia de la selección de V3

Reproduce el backtest 2014–2026 y la selección pre-registrada de V3.

```bash
cd research
git clone --depth 1 https://github.com/ff137/bitstamp-btcusd-minute-data
mkdir -p data
python build_daily.py bitstamp-btcusd-minute-data        # -> data/btc_daily_bitstamp.csv
python build_exec_prices.py bitstamp-btcusd-minute-data  # -> data/exec_prices.csv (opcional)
pip install scipy
python run_is.py      # in-sample 2014–2021 (selección)
python run_oos.py     # fuera de muestra 2022–2026, bootstrap, Sharpe deflactado
python run_wf.py      # walk-forward de parámetros
python run_exec.py    # sensibilidad al atraso de ejecución
python build_cone.py  # rango esperado del dashboard (dashboard/src/cone.json)
```

`PREREG_v3_candidatos.md` fija candidatos y regla de selección antes de mirar OOS.
`lib.simulate` reproduce la contabilidad de `engine_v21` (diferencia 0.0 en equity),
y `test_engine_v3.py::test_matches_reference_backtest` ata el motor de producción a esta referencia.
Los datos (Bitstamp, ~90 MB) no se versionan.

## V3 todo/nada (reemplaza a la V3 Donchian antes de su primera fila)

Selección hecha con criterio de **capital final**, no de Sharpe:

```bash
python todo_nada_binary.py        # todo/nada vs escalonado, por umbral
python todo_nada_frontier.py      # mezclas y topes de volatilidad
python todo_nada_maxcap.py        # 147 reglas en 9 familias (capital final, años de inicio)
python todo_nada_maxcap_wf.py     # walk-forward: elegir la mejor cada año vs regla fija
python todo_nada_hyst_check.py    # ventanas móviles 1–4 años, vecindad de la histéresis
python todo_nada_verify_binary.py # cálculo independiente, atraso de 1 día, costos, tramos
```

Resultado: 20/60/120/250 ≥3 de 4 (plazos heredados de v2.0, no elegidos por la búsqueda)
da 486× desde 2014 contra 114× HODL. Las reglas que la superan en el backtest no resisten
la vecindad de parámetros ni el walk-forward (147× vs 224× desde 2017).

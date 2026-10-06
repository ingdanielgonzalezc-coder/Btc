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
```

`PREREG_v3_candidatos.md` fija candidatos y regla de selección antes de mirar OOS.
`lib.simulate` reproduce la contabilidad de `engine_v21` (diferencia 0.0 en equity),
y `test_engine_v3.py::test_matches_reference_backtest` ata el motor de producción a esta referencia.
Los datos (Bitstamp, ~90 MB) no se versionan.

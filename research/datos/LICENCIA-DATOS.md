# Datos derivados de Bitstamp BTC/USD

`btc_daily_bitstamp.csv` (cierre diario 00:00 UTC, volumen) y `exec_prices.csv`
(precio a las 00:05, 01:00, 05:00 y 12:00 UTC del día siguiente) se derivan de
[ff137/bitstamp-btcusd-minute-data](https://github.com/ff137/bitstamp-btcusd-minute-data)
(minutos 2012-01-01 → 2026-10-06), con `build_daily.py` y `build_exec_prices.py`.

Atribución requerida:
- **"Zielak (mczielinski), Bitcoin Historical Data, Kaggle"** (filas hasta 2025-01-07, CC BY-SA 4.0)
- **"Bitstamp BTC/USD minute data, github.com/ff137/bitstamp-btcusd-minute-data"** (desde 2025-01-07, CC BY 4.0)

Por unir ambas partes, estos archivos se distribuyen bajo
[CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/).
Cambios: agregación de minutos a precios diarios y a horas fijas. Sin afiliación con Bitstamp Ltd.

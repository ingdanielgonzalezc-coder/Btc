# BTC Paper Trading — Dashboard

PWA (React + Vite) que lee las pestañas publicadas del Google Sheet y muestra el
registro en vivo de v2.1 (oficial), V3 (challenger) y v2.0 (legado).

## Qué muestra

- **Precios de giro**: qué cierre de mañana dispara una compra o venta, por versión (pestaña `next_levels`).
- **Salud de las corridas**: última corrida, OK o FORK, atraso del cron, historial de 30 corridas (`meta_runs`, `meta_runs_v3`).
- **Capital con rango esperado**: la curva real contra el 50% y 90% central de 4.000 trayectorias
  simuladas con los retornos diarios 2022–2026 del backtest (`src/cone.json`, lo genera `research/build_cone.py`).
- **Comparación de versiones** rebasadas a una fecha común.
- **Caída desde el máximo** contra HODL y **exposición** (peso real escalonado vs señal).
- **Operaciones y costo acumulado**, con lo que costaría a 40 pb (retail).
- **Ejecución**: brecha entre el spot al correr y el cierre de la señal, contra el atraso del cron.

## Configurar las fuentes

Publica cada pestaña como CSV (Archivo → Compartir → Publicar en la web → pestaña → CSV)
y define estas variables en Vercel (**Settings → Environment Variables**), luego **Redeploy**:

| Variable | Pestaña |
|---|---|
| `VITE_CSV_V21` | `track_record_v21` |
| `VITE_CSV_V3` | `track_record_v3` |
| `VITE_CSV_V20` | `track_record` |
| `VITE_CSV_META` | `meta_runs` |
| `VITE_CSV_META_V3` | `meta_runs_v3` |
| `VITE_CSV_LEVELS` | `next_levels` |
| `VITE_CSV_EXEC` | `track_record_exec` |

También puedes pegarlas en la app con **Fuentes de datos**; quedan guardadas solo en ese
navegador. La app reconoce cada pestaña por sus columnas: si un link apunta a otra pestaña
de registro, la reasigna y lo avisa.

> Las variables `VITE_*` quedan dentro del bundle. Los links CSV publicados ya son públicos.

## Tests

```bash
npm test        # lógica de métricas, escenarios, ejecución y comparación (node --test)
```

## Local

```bash
npm install
cp .env.example .env.local   # pega los links
npm run dev                  # http://localhost:5173
```

## Después de un deploy

La PWA se actualiza sola, pero el service worker puede servir la versión anterior en la
primera carga. Si ves la versión vieja, recarga dos veces o cierra y abre la app.

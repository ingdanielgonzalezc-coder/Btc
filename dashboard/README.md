# BTC Paper Trading — Dashboard

PWA (React + Vite) que lee el track record publicado del Google Sheet y grafica la
estrategia (trend-following + volatility-targeting) contra buy & hold. Instalable y
con caché offline del último dato.

## Local

```bash
npm install
cp .env.example .env      # y pega tu link CSV en VITE_CSV_URL
npm run dev               # http://localhost:5173
```

Sin `VITE_CSV_URL`, la app arranca con datos demo. También puedes pegar el link a
mano en el campo de arriba y darle **Load**.

## Conseguir el link CSV

En el Google Sheet: **Archivo → Compartir → Publicar en la web → pestaña
`track_record` → CSV → Publicar**. Copia el link (`https://docs.google.com/…/pub?output=csv`).

## Desplegar en Vercel

1. Sube esta carpeta a un repo (propio o subcarpeta del repo `Btc`).
2. En Vercel: **New Project → Import** ese repo.
   - Si está en una subcarpeta, pon esa carpeta en **Root Directory**.
   - Framework: **Vite** (se autodetecta). Build: `npm run build`. Output: `dist`.
3. En **Settings → Environment Variables** agrega:
   - `VITE_CSV_URL` = tu link CSV publicado.
4. **Deploy**. La app carga el track record sola al abrir.

> Las variables `VITE_*` se incrustan en el bundle del cliente en build. El link CSV
> ya es público, así que no es un secreto — pero por eso mismo no pongas nada sensible
> con prefijo `VITE_`.

## Instalar como app

Abre la URL de Vercel en el navegador → menú → **Instalar app** (o "Añadir a pantalla
de inicio" en móvil). Funciona offline mostrando el último dato cacheado.

## Build

```bash
npm run build      # genera dist/ + service worker (PWA)
npm run preview    # sirve dist/ localmente para probar la PWA
```

import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { VitePWA } from "vite-plugin-pwa";

export default defineConfig({
  plugins: [
    react(),
    VitePWA({
      registerType: "autoUpdate",
      includeAssets: ["favicon.svg", "icon-192.png", "icon-512.png"],
      manifest: {
        name: "BTC Paper Trading",
        short_name: "BTC Paper",
        description: "Live forward track record — trend-following + volatility-targeting",
        theme_color: "#0E1320",
        background_color: "#0E1320",
        display: "standalone",
        start_url: "/",
        icons: [
          { src: "icon-192.png", sizes: "192x192", type: "image/png" },
          { src: "icon-512.png", sizes: "512x512", type: "image/png" },
          { src: "icon-512-maskable.png", sizes: "512x512", type: "image/png", purpose: "maskable" },
        ],
      },
      workbox: {
        // Cachea el CSV publicado para que la app funcione offline con el último dato
        runtimeCaching: [
          {
            urlPattern: ({ url }) => url.hostname.includes("docs.google.com"),
            handler: "NetworkFirst",
            options: {
              cacheName: "track-record-csv",
              expiration: { maxEntries: 4, maxAgeSeconds: 60 * 60 * 24 },
              cacheableResponse: { statuses: [0, 200] },
            },
          },
        ],
      },
    }),
  ],
});

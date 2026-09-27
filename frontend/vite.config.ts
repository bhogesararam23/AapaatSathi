import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { fileURLToPath, URL } from "node:url";

const API_TARGET = process.env.VITE_PROXY_TARGET || "http://127.0.0.1:8000";

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": fileURLToPath(new URL("./src", import.meta.url)),
    },
  },
  server: {
    port: 5173,
    host: true,
    // Proxying keeps the browser on one origin in development, so the demo
    // needs no CORS tuning and the WebSocket upgrade just works.
    proxy: {
      "/api": {
        target: API_TARGET,
        changeOrigin: true,
        ws: true,
      },
    },
  },
  build: {
    outDir: "dist",
    sourcemap: false,
    chunkSizeWarningLimit: 1200,
    rollupOptions: {
      output: {
        manualChunks: {
          map: ["maplibre-gl"],
          charts: ["recharts"],
        },
      },
    },
  },
});

/// <reference types="vitest/config" />
import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import path from "node:path";
import { defineConfig } from "vite";

const backend = process.env.DARTSENSE_BACKEND ?? "http://127.0.0.1:8000";
// Operator panel API: the central fleet server (python -m backend --central).
const central = process.env.DARTSENSE_CENTRAL ?? "http://127.0.0.1:8100";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: { alias: { "@": path.resolve(__dirname, "src") } },
  server: {
    host: true,
    port: 5173,
    proxy: {
      // first match wins: fleet calls go to the central server, everything else to the board
      "/api/fleet": { target: central, changeOrigin: true },
      "/api": { target: backend, changeOrigin: true },
      "/ws": { target: backend.replace(/^http/, "ws"), ws: true },
    },
  },
  build: { outDir: "dist", sourcemap: true, chunkSizeWarningLimit: 900 },
  test: { environment: "jsdom", include: ["src/**/*.test.{ts,tsx}"] },
});

/// <reference types="vitest/config" />
import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import path from "node:path";
import { defineConfig } from "vite";

const backend = process.env.DARTSENSE_BACKEND ?? "http://127.0.0.1:8000";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: { alias: { "@": path.resolve(__dirname, "src") } },
  server: {
    host: true,
    port: 5173,
    proxy: {
      "/api": { target: backend, changeOrigin: true },
      "/ws": { target: backend.replace(/^http/, "ws"), ws: true },
    },
  },
  build: { outDir: "dist", sourcemap: true, chunkSizeWarningLimit: 900 },
  test: { environment: "jsdom", include: ["src/**/*.test.{ts,tsx}"] },
});

/// <reference types="vitest" />
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Proxy de desenvolvimento: o frontend (5173) conversa com a API local (8765).
export default defineConfig({
  plugins: [react()],
  server: { host: "127.0.0.1", port: 5173, proxy: { "/api": `http://127.0.0.1:${process.env.DMI_API_PORT ?? "8765"}` } },
  build: { outDir: "dist", sourcemap: false, chunkSizeWarningLimit: 900 },
  test: { environment: "jsdom", setupFiles: ["./src/test/setup.ts"], css: false },
});

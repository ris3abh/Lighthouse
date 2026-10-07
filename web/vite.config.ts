import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import { defineConfig } from "vite";

// The build lands inside the Python package so `pipx install` ships the dashboard.
export default defineConfig({
  plugins: [react(), tailwindcss()],
  base: "./",
  build: { outDir: "../areao1/server/static", emptyOutDir: true },
  server: { proxy: { "/api": "http://127.0.0.1:7777" } },
});

import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// Tauri sert le front depuis `dist/` ; en dev, il attend Vite sur 1420.
export default defineConfig({
  plugins: [react()],
  clearScreen: false,
  server: { port: 1420, strictPort: true },
  envPrefix: ["VITE_", "TAURI_ENV_"],
  build: { target: "es2022", minify: true, sourcemap: false },
});

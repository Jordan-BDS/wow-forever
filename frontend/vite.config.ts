import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { fileURLToPath, URL } from "node:url";
import { defineConfig } from "vitest/config";

const backend = process.env.VITE_BACKEND_URL ?? "http://localhost:8000";

// changeOrigin: false conserve l'en-tête Host du navigateur (localhost:3001), sinon Django
// rejette les POST car l'Origin ne correspond plus à l'hôte (contrôle CSRF).
const proxy = { target: backend, changeOrigin: false };

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: { "@": fileURLToPath(new URL("./src", import.meta.url)) },
  },
  build: {
    rolldownOptions: {
      output: {
        // Les bibliothèques dans un fichier à part : il reste en cache quand seul le code du site change.
        codeSplitting: { groups: [{ name: "vendor", test: /node_modules[\\/](?!@fontsource)/ }] },
      },
    },
  },
  server: {
    port: 5173,
    proxy: {
      "/api": proxy,
      "/admin": proxy,
      "/static": proxy,
    },
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test/setup.ts"],
  },
});

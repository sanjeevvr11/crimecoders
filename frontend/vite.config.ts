import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";

// In development the UI calls relative /api/* URLs and Vite proxies them to the
// FastAPI backend, so no backend URL is hard-coded in the UI. Override the
// target with VITE_PROXY_TARGET, or call another host directly by setting
// VITE_API_BASE_URL (see src/api/client.ts).
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, ".", "");
  return {
    plugins: [react()],
    build: {
      rollupOptions: {
        output: { manualChunks: { react: ["react", "react-dom", "react-router-dom"], charts: ["recharts"], graph: ["cytoscape"] } },
      },
    },
    server: {
      port: 5173,
      proxy: { "/api": { target: env.VITE_PROXY_TARGET || "http://localhost:8000", changeOrigin: true } },
    },
  };
});

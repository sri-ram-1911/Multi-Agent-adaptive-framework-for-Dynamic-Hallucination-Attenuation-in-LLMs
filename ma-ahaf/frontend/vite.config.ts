import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react()],
  server: {
    host: true,
    port: 5173,
    proxy: {
      "/v1": { target: process.env.VITE_API_BASE || "http://localhost:8000", changeOrigin: true },
      "/health": { target: process.env.VITE_API_BASE || "http://localhost:8000", changeOrigin: true },
    },
  },
});

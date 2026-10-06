import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    // Geliştirmede /api istekleri FastAPI'ye yönlendirilir; böylece
    // istemci kodunda sunucu adresi hiç geçmez.
    proxy: { "/api": "http://127.0.0.1:8000" },
  },
});

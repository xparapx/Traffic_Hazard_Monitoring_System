import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

// 공개 API :8600 · 관리 API :8601 (edge/trafficsvc/settings.py)
export default defineConfig({
  base: "./", // 정적 서빙(기기·아티팩트)에서 상대 경로로 동작
  plugins: [react(), tailwindcss()],
  server: {
    proxy: {
      "/api/public": { target: "http://127.0.0.1:8600", changeOrigin: true },
      "/api/admin": { target: "http://127.0.0.1:8601", changeOrigin: true },
    },
  },
});

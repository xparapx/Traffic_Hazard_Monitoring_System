import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

// 공개 API :8600 · 관리 API :8601 (edge/trafficsvc/settings.py)
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    proxy: {
      "/api/public": {
        target: "http://127.0.0.1:8600",
        changeOrigin: true,
        rewrite: (p) => p.replace(/^\/api\/public/, ""),
      },
      "/api/admin": {
        target: "http://127.0.0.1:8601",
        changeOrigin: true,
        rewrite: (p) => p.replace(/^\/api\/admin/, ""),
      },
    },
  },
});

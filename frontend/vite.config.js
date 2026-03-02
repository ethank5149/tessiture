import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  const apiTarget = env.VITE_API_PROXY_TARGET || "http://127.0.0.1:8000";

  return {
    plugins: [react()],
    server: {
      host: "0.0.0.0",
      port: 5173,
      proxy: {
        "/analyze": apiTarget,
        "/analyze/example": apiTarget,
        "/status": apiTarget,
        "/results": apiTarget,
        "/examples": apiTarget,
      },
    },
    preview: {
      host: "0.0.0.0",
      port: 4173,
    },
    build: {
      outDir: "dist",
      sourcemap: false,
    },
    test: {
      environment: "jsdom",
      globals: true,
      css: true,
      include: ["src/**/*.test.{js,jsx}"],
    },
  };
});

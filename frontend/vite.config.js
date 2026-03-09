import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";
import { fileURLToPath } from "node:url";

const resolveFromRoot = (relativePath) =>
  fileURLToPath(new URL(relativePath, import.meta.url));

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  const apiTarget = env.VITE_API_PROXY_TARGET || "http://127.0.0.1:8000";
  const devServerHost = env.VITE_DEV_SERVER_HOST || "0.0.0.0";
  const devServerPort = Number.parseInt(env.VITE_DEV_SERVER_PORT || "5173", 10) || 5173;
  const devAllowedHosts = env.VITE_DEV_ALLOWED_HOSTS
    ? env.VITE_DEV_ALLOWED_HOSTS.split(",")
        .map((host) => host.trim())
        .filter(Boolean)
    : ["localhost", "127.0.0.1", "::1", ".local"];

  return {
    plugins: [react()],
    resolve: {
      alias: {
        "@": resolveFromRoot("./src"),
        "@components": resolveFromRoot("./src/components"),
        "@hooks": resolveFromRoot("./src/hooks"),
        "@lib": resolveFromRoot("./src/lib"),
      },
    },
    server: {
      host: devServerHost,
      port: devServerPort,
      allowedHosts: devAllowedHosts,
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
      coverage: {
        provider: "v8",
        reporter: ["text", "json", "html"],
        include: ["src/**/*.{js,jsx}"],
        exclude: [
          "src/main.jsx",
          "src/**/*.test.{js,jsx}",
          "src/**/__tests__/**",
        ],
      },
    },
  };
});

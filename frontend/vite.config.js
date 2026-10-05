import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  const apiTarget =
    env.VITE_API_PROXY_TARGET?.trim() || "http://127.0.0.1:8000";

  return {
    plugins: [react(), tailwindcss()],
    server: {
      port: 5173,
      proxy: {
        // En desarrollo, /api → backend (mismo prefijo que `API_PREFIX` del backend, por defecto /api).
        // Si el API corre en otra máquina/puerto: VITE_API_PROXY_TARGET=http://192.168.1.10:8000
        "/api": { target: apiTarget, changeOrigin: true, ws: true },
        // Pulsaciones ESP32 (firmware usa /zaguan/pulsacion/pN sin prefijo /api)
        "/zaguan": { target: apiTarget, changeOrigin: true },
        "/docs": { target: apiTarget, changeOrigin: true },
        "/redoc": { target: apiTarget, changeOrigin: true },
      },
    },
  };
});

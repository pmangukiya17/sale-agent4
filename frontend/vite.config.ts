import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    host: true,
    proxy: {
      "/api": {
        // Docker Compose sets VITE_API_PROXY_TARGET=http://backend:8000
        // explicitly (see docker-compose.yml) - "backend" is only
        // resolvable inside the Compose network, so that value always
        // wins there and this fallback is never reached in Docker.
        // Running `npm run dev` directly on the host has no such env var
        // set, so it falls through here - localhost:8000 is correct in
        // that case because Compose already publishes the backend's port
        // to the host ("8000:8000"), whether the backend itself is
        // running natively or via `docker compose up backend db`.
        target: process.env.VITE_API_PROXY_TARGET || "http://localhost:8000",
        changeOrigin: true,
      },
    },
  },
});

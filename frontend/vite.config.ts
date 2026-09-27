import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    host: "0.0.0.0",
    port: 5173,
    // Required so file changes are picked up inside the Docker container.
    watch: {
      usePolling: true,
    },
    proxy: {
      // Rich-text fields store relative "/media/…" URLs (issue #5); proxy them
      // to the backend in dev. Prod serves /media on the same origin via Caddy.
      "/media": {
        target: "http://backend:8000",
        changeOrigin: true,
      },
    },
  },
});

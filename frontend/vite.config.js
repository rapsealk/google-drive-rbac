import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import stylex from "vite-plugin-stylex";

export default defineConfig({
  plugins: [react(), stylex()],
  server: {
    proxy: {
      "/api": "http://localhost:8000",
    },
  },
});

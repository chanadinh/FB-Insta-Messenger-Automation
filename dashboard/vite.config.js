import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  base: "/mailbox/",
  server: { proxy: { "/api": "http://127.0.0.1:8000", "/gallery": "http://127.0.0.1:8000" } },
});

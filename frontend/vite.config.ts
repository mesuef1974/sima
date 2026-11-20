import { defineConfig } from "vitest/config";
import vue from "@vitejs/plugin-vue";
import { fileURLToPath, URL } from "node:url";

// يبني إلى src/sima/web/frontend_dist حيث يقرأ django-vite بيانه .vite/manifest.json ويخدمه Django تحت /static/.
export default defineConfig({
  plugins: [vue()],
  base: "/static/",
  server: { host: "127.0.0.1", port: 5173, strictPort: true, origin: "http://127.0.0.1:5173" },
  resolve: { alias: { "@": fileURLToPath(new URL("./src", import.meta.url)) } },
  build: {
    manifest: true,
    outDir: "../src/sima/web/frontend_dist",
    emptyOutDir: true,
    rollupOptions: { input: ["src/main.ts"] },
  },
  test: { environment: "jsdom", globals: true },
});

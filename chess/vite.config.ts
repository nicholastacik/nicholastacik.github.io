import { defineConfig } from "vite";

export default defineConfig({
  base: "./",
  build: { outDir: "../posts/chess/app", emptyOutDir: true },
  test: { environment: "jsdom", globals: true },
});

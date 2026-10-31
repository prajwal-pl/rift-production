import { defineConfig } from "vite";
import { viteSingleFile } from "vite-plugin-singlefile";

// Everything (JS + CSS) is inlined into dist/index.html: one file = one R2 upload = no CORS
// problems inside a sandboxed iframe. DO NOT change this file.
export default defineConfig({
  base: "./",
  plugins: [viteSingleFile()],
  build: {
    assetsInlineLimit: 100_000_000,
    chunkSizeWarningLimit: 4_000,
    cssCodeSplit: false,
    reportCompressedSize: false,
  },
});

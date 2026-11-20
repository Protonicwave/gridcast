import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

/** The API as `uv run uvicorn --factory gridcast.api:app_from_environment` serves it. */
const LOCAL_API_URL = "http://127.0.0.1:8000";

export default defineConfig({
  // Relative asset URLs, so the built site works under a GitHub Pages project path.
  base: "./",
  plugins: [react()],
  // scripts/check_bundle.py reads the manifest to size each chunk.
  build: { manifest: true },
  // The dev and preview servers forward API calls, so the page and the API share an origin locally.
  server: { host: "127.0.0.1", proxy: { "/regions": LOCAL_API_URL } },
  preview: { host: "127.0.0.1" },
  test: {
    exclude: ["e2e/**", "node_modules/**"],
    environment: "jsdom",
    setupFiles: ["./src/testSetup.ts"],
    restoreMocks: true,
    unstubGlobals: true,
  },
});

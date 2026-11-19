import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "e2e",
  // The API may answer slowly, so a run gets more time than the page's own ten second fetch limit.
  timeout: 60_000,
  retries: 0,
  reporter: "list",
  use: { baseURL: process.env["SITE_URL"] },
});

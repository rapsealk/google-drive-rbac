import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  timeout: 60_000,
  retries: 1,
  use: {
    baseURL: "http://localhost:8080",
    headless: true,
  },
  // Prereq: `docker compose up --build -d` from the repo root.
  // The e2e self-seeds by driving the UI (no fixtures, no seed command).
});

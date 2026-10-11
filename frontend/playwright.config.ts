import { defineConfig } from '@playwright/test'

// Runs against the production build using the installed Microsoft Edge, so no browser download is needed.
// Set PW_CHANNEL=chrome to use Chrome instead.
export default defineConfig({
  testDir: './e2e',
  timeout: 60_000,
  use: {
    baseURL: 'http://localhost:4173',
    channel: process.env.PW_CHANNEL ?? 'msedge',
  },
  webServer: {
    command: 'npm run preview -- --port 4173 --strictPort',
    url: 'http://localhost:4173',
    reuseExistingServer: true,
  },
})

import { defineConfig } from '@playwright/test'

export default defineConfig({
  testDir: '../tests/e2e',
  timeout: 30_000,
  fullyParallel: false,
  workers: 1,
  use: {
    baseURL: 'http://127.0.0.1:9902',
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },
  webServer: {
    command: 'node ../tests/e2e/start-server.mjs',
    url: 'http://127.0.0.1:9902/health',
    reuseExistingServer: false,
    timeout: 30_000,
  },
  projects: [{
    name: 'chromium',
    use: process.env.CI ? { browserName: 'chromium' } : { browserName: 'chromium', channel: 'chrome' },
  }],
})

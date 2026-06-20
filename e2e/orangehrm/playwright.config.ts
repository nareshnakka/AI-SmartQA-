import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: './src/tests',
  timeout: 300_000,
  retries: 1,
  outputDir: 'test-results',
  reporter: [
    ['html', { outputFolder: 'playwright-report', open: 'never' }],
    ['json', { outputFile: 'test-results/results.json' }],
    ['line'],
  ],
  use: {
    baseURL: process.env.BASE_URL || process.env.PLAYWRIGHT_BASE_URL || '',
    headless: true,
    video: 'on',
    trace: 'on',
    screenshot: 'on',
    actionTimeout: 10_000,
    navigationTimeout: 30_000,
  },
});

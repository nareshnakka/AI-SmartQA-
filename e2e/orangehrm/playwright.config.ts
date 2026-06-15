import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: './src/tests',
  timeout: 120_000,
  retries: 1,
  outputDir: 'test-results',
  reporter: [
    ['html', { outputFolder: 'playwright-report', open: 'never' }],
    ['json', { outputFile: 'test-results/results.json' }],
    ['line'],
  ],
  use: {
    baseURL: 'https://opensource-demo.orangehrmlive.com',
    headless: true,
    video: 'on',
    trace: 'on',
    screenshot: 'on',
    actionTimeout: 10_000,
    navigationTimeout: 30_000,
  },
});

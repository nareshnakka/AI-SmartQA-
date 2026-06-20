import { Page, expect } from '@playwright/test';

/** Stream current page to Studio live browser panel (QEOS_LIVE_FRAME env). */
export async function publishLiveFrame(page: Page) {
  const framePath = process.env.QEOS_LIVE_FRAME;
  if (!framePath) return;
  try {
    await page.screenshot({
      path: framePath,
      type: 'jpeg',
      quality: 72,
      timeout: 8_000,
      animations: 'disabled',
    });
  } catch {
    /* page may be mid-navigation */
  }
}

export async function waitForPageLoad(page: Page) {
  await page.waitForLoadState('domcontentloaded');
  await page.waitForLoadState('networkidle', { timeout: 15_000 }).catch(() => {});
  await publishLiveFrame(page);
}

export async function assertNoJsErrors(page: Page, errors: string[]) {
  expect(errors.filter((e) => !e.includes('favicon'))).toHaveLength(0);
}

export async function retryAction<T>(fn: () => Promise<T>, label: string, timeoutMs = 10_000): Promise<T> {
  const start = Date.now();
  let lastError: unknown;
  while (Date.now() - start < timeoutMs) {
    try {
      return await fn();
    } catch (e) {
      lastError = e;
      await new Promise((r) => setTimeout(r, 500));
    }
  }
  throw new Error(`${label} failed after ${timeoutMs}ms: ${lastError}`);
}

export async function timed<T>(fn: () => Promise<T>): Promise<{ result: T; durationMs: number }> {
  const start = Date.now();
  const result = await fn();
  return { result, durationMs: Date.now() - start };
}

export async function expectHeaderContains(page: Page, text: string) {
  const header = page.locator('.oxd-topbar-header-breadcrumb-module, .oxd-topbar-header-title, h6').first();
  await expect(header).toBeVisible({ timeout: 15_000 });
  await expect(header).toContainText(text, { timeout: 15_000 });
}

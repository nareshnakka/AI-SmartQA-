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

/** Default pause between automation steps (ms). Override with QEOS_STEP_PAUSE_MS. */
export function stepPauseMs(): number {
  const n = parseInt(process.env.QEOS_STEP_PAUSE_MS || '3000', 10);
  return Number.isFinite(n) && n >= 0 ? n : 3000;
}

/**
 * Wait until the page has fully loaded (document load + network mostly idle).
 * Used after every automation step so the next action sees a settled UI.
 */
export async function waitForPageLoad(page: Page) {
  try {
    await page.waitForLoadState('domcontentloaded', { timeout: 30_000 });
  } catch {
    /* already past or navigation in flight */
  }
  try {
    await page.waitForLoadState('load', { timeout: 30_000 });
  } catch {
    /* SPA may not fire a classic load event */
  }
  await page.waitForLoadState('networkidle', { timeout: 20_000 }).catch(() => {});
  // Brief settle for SPA/client rendering after network quiet
  await page.waitForTimeout(300);
  await publishLiveFrame(page);
}

/** Pause between steps (default 3s) and refresh live frame. */
export async function pauseBetweenSteps(page: Page, label?: string) {
  const ms = stepPauseMs();
  if (ms <= 0) return;
  console.log(label ? `⏳ Pause ${ms}ms ${label}` : `⏳ Pause ${ms}ms between steps`);
  await page.waitForTimeout(ms);
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

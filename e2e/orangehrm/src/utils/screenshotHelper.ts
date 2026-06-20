import { Page } from '@playwright/test';
import path from 'path';
import { publishLiveFrame } from './helpers';

const SCREENSHOT_DIR = path.join(process.cwd(), 'screenshots');

export async function captureScreenshot(page: Page, name: string): Promise<string> {
  const filePath = path.join(SCREENSHOT_DIR, `${name}.png`);
  await page.screenshot({ path: filePath, fullPage: true });
  await publishLiveFrame(page);
  return filePath;
}

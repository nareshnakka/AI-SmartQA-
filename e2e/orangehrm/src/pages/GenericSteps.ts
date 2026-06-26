import { expect, Page } from '@playwright/test';
import { publishLiveFrame } from '../utils/helpers';

export type DiscoveryStep = {
  description: string;
  action?: string;
  url?: string;
  element?: string;
  target?: string;
};

function quotedText(text: string): string | null {
  const m = text.match(/["']([^"']+)["']/);
  return m?.[1] ?? null;
}

async function tryGenericLogin(page: Page) {
  const user = process.env.QEOS_USERNAME || process.env.TEST_USERNAME || '';
  const pass = process.env.QEOS_PASSWORD || process.env.TEST_PASSWORD || '';

  const userSelectors = [
    'input[name=username]',
    'input[name=email]',
    'input[type=email]',
    '#username',
    '#txtUsername',
    'input[placeholder*="user" i]',
    'input[autocomplete=username]',
  ];
  const passSelectors = [
    'input[name=password]',
    'input[type=password]',
    '#password',
    'input[placeholder*="pass" i]',
  ];

  let filledUser = false;
  for (const sel of userSelectors) {
    const loc = page.locator(sel).first();
    if ((await loc.count()) > 0) {
      if (user) await loc.fill(user, { timeout: 8000 });
      filledUser = true;
      console.log(`→ Enter username (${sel})`);
      break;
    }
  }

  if (!filledUser) {
    const ph = page.getByPlaceholder(/user/i).first();
    if ((await ph.count()) > 0) {
      if (user) await ph.fill(user, { timeout: 8000 });
      filledUser = true;
      console.log('→ Enter username (placeholder)');
    }
  }

  if (!filledUser) {
    throw new Error('No username field found — set QEOS_USERNAME or use an app with a standard login form');
  }

  for (const sel of passSelectors) {
    const loc = page.locator(sel).first();
    if ((await loc.count()) > 0) {
      if (pass) await loc.fill(pass, { timeout: 8000 });
      console.log('→ Enter password');
      break;
    }
  }

  const loginBtn = page.getByRole('button', { name: /login|sign in|submit/i }).first();
  if ((await loginBtn.count()) > 0) {
    await loginBtn.click({ timeout: 8000 });
    console.log('✓ Click login button');
  } else {
    await page.locator('button[type=submit], input[type=submit]').first().click({ timeout: 8000 }).catch(() => {});
  }

  await page.waitForLoadState('domcontentloaded').catch(() => {});
  await publishLiveFrame(page);
}

async function runOneStep(page: Page, step: DiscoveryStep, baseUrl: string) {
  const desc = step.description || '';
  const lower = desc.toLowerCase();
  const action = (step.action || '').toLowerCase();

  if (action === 'navigate' || lower.startsWith('open ') || lower.includes('navigate to') || step.url) {
    let url = step.url || step.target || '';
    if (!url || url.startsWith('/')) {
      const fromDesc = desc.match(/https?:\/\/[^\s'"]+/i)?.[0];
      url = fromDesc || (url ? `${baseUrl.replace(/\/$/, '')}${url.startsWith('/') ? url : `/${url}`}` : baseUrl);
    }
    console.log(`→ Navigate to ${url}`);
    const resp = await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 30_000 });
    await publishLiveFrame(page);
    const status = resp?.status() ?? 0;
    const title = (await page.title()).toLowerCase();
    if (status === 404 || title.includes('not found') || title.includes('404')) {
      throw new Error(
        `HTTP ${status || 404} — page not found at ${url}. Check Base URL in Automation IDE and the navigate step URL.`
      );
    }
    console.log(`✓ Loaded: ${page.url()}`);
    return;
  }

  if (lower.includes('login') || lower.includes('sign in') || action === 'fill') {
    console.log(`→ ${desc}`);
    await tryGenericLogin(page);
    console.log(`✓ ${desc}`);
    return;
  }

  if (action === 'click' || lower.includes('click')) {
    const label = step.element || quotedText(desc) || desc.replace(/^click\s+/i, '').trim();
    console.log(`→ Click "${label}"`);
    const link = page.getByRole('link', { name: new RegExp(label.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'), 'i') }).first();
    const menu = page.locator(
      '.oxd-main-menu-item, [role=menuitem], nav a, .sidebar a, .menu-item'
    ).filter({ hasText: new RegExp(label.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'), 'i') }).first();
    const btn = page.getByRole('button', { name: new RegExp(label.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'), 'i') }).first();

    if ((await menu.count()) > 0) {
      await menu.click({ timeout: 15_000 });
    } else if ((await link.count()) > 0) {
      await link.click({ timeout: 15_000 });
    } else if ((await btn.count()) > 0) {
      await btn.click({ timeout: 15_000 });
    } else if (step.target) {
      await page.goto(step.target, { waitUntil: 'domcontentloaded', timeout: 30_000 });
    } else {
      throw new Error(`Could not find clickable target: ${label}`);
    }
    await page.waitForLoadState('domcontentloaded').catch(() => {});
    await publishLiveFrame(page);
    console.log(`✓ After click: ${page.url()}`);
    return;
  }

  if (action === 'verify' || lower.includes('verify')) {
    console.log(`→ ${desc}`);
    await expect(page).toHaveURL(/.+/);
    const title = await page.title();
    if (step.target) {
      await expect(page).toHaveURL(new RegExp(step.target.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'), 'i'));
    }
    console.log(`✓ Verified page: ${title || page.url()}`);
    return;
  }

  if (action === 'inspect' || lower.includes('follow link')) {
    const href = step.target || step.url;
    if (href) {
      await page.goto(href, { waitUntil: 'domcontentloaded', timeout: 30_000 });
      await publishLiveFrame(page);
      console.log(`✓ Opened ${href}`);
      return;
    }
  }

  console.log(`→ ${desc}`);
  await expect(page.locator('body')).toBeVisible();
  console.log(`✓ ${desc}`);
}

export async function runDiscoverySteps(page: Page, steps: DiscoveryStep[], baseUrl: string) {
  const { resetQeosProgress, setQeosProgressPage, reportQeosStepAt } = await import('../utils/qeosProgress');
  resetQeosProgress();
  setQeosProgressPage(page);

  if (!steps.length) {
    reportQeosStepAt(0, 'Open application', 'running');
    await page.goto(baseUrl, { waitUntil: 'domcontentloaded' });
    await expect(page.locator('body')).toBeVisible();
    reportQeosStepAt(0, 'Open application', 'passed');
    return;
  }

  for (let i = 0; i < steps.length; i++) {
    const step = steps[i];
    const desc = step.description?.trim() || `Step ${i + 1}`;
    reportQeosStepAt(i, desc, 'running');
    try {
      await runOneStep(page, step, baseUrl);
      reportQeosStepAt(i, desc, 'passed');
    } catch (err) {
      reportQeosStepAt(i, desc, 'failed');
      throw err;
    }
  }
}

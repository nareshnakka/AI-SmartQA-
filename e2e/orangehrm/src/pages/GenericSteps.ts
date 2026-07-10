import { expect, Page } from '@playwright/test';
import { publishLiveFrame } from '../utils/helpers';

export type DiscoveryStep = {
  description: string;
  action?: string;
  url?: string;
  element?: string;
  target?: string;
  field?: string;
  interaction?: string;
};

function quotedText(text: string): string | null {
  const m = text.match(/["']([^"']+)["']/);
  return m?.[1] ?? null;
}

function escapeRegExp(text: string): string {
  return text.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

function parseFillStep(step: DiscoveryStep): { label: string; value: string } {
  const desc = step.description || '';
  const fromDesc = desc.match(/^Enter\s+(.+?):\s*(.+)$/i);
  if (fromDesc) {
    return { label: (step.field || fromDesc[1]).trim(), value: fromDesc[2].trim() };
  }
  return { label: (step.field || desc).trim(), value: '' };
}

const FIELD_ALIASES: Record<string, string[]> = {
  'your name': ['name'],
  name: ['name'],
  'e-mail': ['email'],
  email: ['email'],
  'mobile number': ['mobile'],
  mobile: ['mobile'],
  phone: ['mobile', 'phone'],
  'organization name': ['organization'],
  organization: ['organization'],
  message: ['comments', 'message'],
};

async function fillFormField(page: Page, step: DiscoveryStep) {
  const { label, value } = parseFillStep(step);
  if (!value) {
    throw new Error(`Fill step missing value: ${step.description}`);
  }
  const key = label.toLowerCase().replace(/\*+$/, '').trim();
  const names = FIELD_ALIASES[key] || [key.replace(/\s+/g, ''), ...key.split(/\s+/).filter((t) => t.length >= 3)];

  for (const name of names) {
    const loc = page.locator(
      `input[name='${name}'], textarea[name='${name}'], #${name}, input[name*='${name}'], textarea[name*='${name}']`
    ).first();
    if ((await loc.count()) > 0) {
      await loc.fill(value, { timeout: 8000 });
      console.log(`✓ Filled ${label} → ${value.slice(0, 40)}`);
      await publishLiveFrame(page);
      return;
    }
  }

  // Paragraph-style labels (Vivilex: <p class="label">Your Name</p><input name="name">)
  const labelPattern = new RegExp(escapeRegExp(label.replace(/\*+$/, '').trim()), 'i');
  for (const sel of ['p.label', '.label', 'label']) {
    const labelEl = page.locator(sel).filter({ hasText: labelPattern }).first();
    if ((await labelEl.count()) > 0) {
      const field = labelEl.locator('xpath=following::input[1] | following::textarea[1]').first();
      if ((await field.count()) > 0) {
        await field.fill(value, { timeout: 8000 });
        console.log(`✓ Filled ${label} → ${value.slice(0, 40)}`);
        await publishLiveFrame(page);
        return;
      }
    }
  }

  if (key.includes('email') || key.includes('mail')) {
    const email = page.locator('input[type=email], input#email, input[name=email]').first();
    if ((await email.count()) > 0) {
      await email.fill(value, { timeout: 8000 });
      return;
    }
  }
  if (key.includes('message') || key.includes('comment')) {
    const ta = page.locator('textarea, textarea#comments, textarea[name=comments]').first();
    if ((await ta.count()) > 0) {
      await ta.fill(value, { timeout: 8000 });
      return;
    }
  }

  throw new Error(`Could not find form field for: ${label}`);
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

function siteBrand(baseUrl: string): string {
  try {
    const host = new URL(baseUrl).hostname.replace(/^www\./, '');
    const name = host.split('.')[0] || 'home';
    return name.charAt(0).toUpperCase() + name.slice(1);
  } catch {
    return 'Home';
  }
}

async function dismissPopups(page: Page): Promise<number> {
  const closePatterns = [
    /^close$/i, /^skip$/i, /not now/i, /maybe later/i, /no thanks/i, /got it/i,
    /continue without/i, /^later$/i, /^dismiss$/i, /accept all/i, /^agree$/i, /^ok$/i, /^×$/, /^✕$/,
  ];
  let total = 0;
  for (let round = 0; round < 4; round++) {
    let roundCount = 0;
    await page.keyboard.press('Escape').catch(() => {});
    await page.waitForTimeout(200);

    const overlays = page.locator(
      "[role=dialog], [aria-modal='true'], .modal, [class*='popup' i], [class*='overlay' i], [class*='modal' i]"
    );
    const overlayN = await overlays.count();
    for (let i = 0; i < Math.min(overlayN, 6); i++) {
      const overlay = overlays.nth(i);
      if (!(await overlay.isVisible().catch(() => false))) continue;
      for (const pat of closePatterns) {
        const btn = overlay.getByRole('button', { name: pat }).first();
        if ((await btn.count()) > 0 && (await btn.isVisible().catch(() => false))) {
          await btn.click({ timeout: 8000 }).catch(() => {});
          roundCount++;
          await page.waitForTimeout(300);
          break;
        }
      }
    }

    for (const pat of closePatterns) {
      const buttons = page.getByRole('button', { name: pat });
      const n = await buttons.count();
      for (let j = 0; j < Math.min(n, 4); j++) {
        const btn = buttons.nth(j);
        if (!(await btn.isVisible().catch(() => false))) continue;
        const box = await btn.boundingBox().catch(() => null);
        if (box && box.y > 900) continue;
        await btn.click({ timeout: 8000 }).catch(() => {});
        roundCount++;
        await page.waitForTimeout(300);
      }
    }

    if (roundCount === 0) break;
    total += roundCount;
  }
  if (total > 0) {
    console.log(`✓ Dismissed ${total} popup(s) / overlay(s)`);
  }
  return total;
}

async function isHomeUrl(current: string, homeUrl: string): Promise<boolean> {
  try {
    const c = new URL(current);
    const h = new URL(homeUrl);
    const cn = c.hostname.replace(/^www\./, '');
    const hn = h.hostname.replace(/^www\./, '');
    if (cn !== hn) return false;
    const path = (c.pathname || '/').replace(/^\/+|\/+$/g, '');
    const homePath = (h.pathname || '/').replace(/^\/+|\/+$/g, '');
    if (!path) return true;
    return !!homePath && path === homePath;
  } catch {
    return false;
  }
}

async function clickHomeLogoJs(page: Page, baseUrl: string): Promise<boolean> {
  const clicked = await page.evaluate((homeUrl) => {
    const norm = (u: string) => {
      try {
        const x = new URL(u, homeUrl);
        const p = (x.pathname || '/').replace(/\/+$/, '') || '/';
        return x.origin + p;
      } catch {
        return '';
      }
    };
    const homeKey = norm(homeUrl);
    const isHomeHref = (href: string) => !!href && norm(href) === homeKey;
    const tryClick = (el: Element | null) => {
      if (!el) return false;
      const r = (el as HTMLElement).getBoundingClientRect();
      if (r.width < 4 || r.height < 4) return false;
      (el as HTMLElement).click();
      return true;
    };
    const header =
      document.querySelector('header') ||
      document.querySelector('[role=banner]') ||
      document.querySelector('[class*="header" i]');
    if (header) {
      for (const a of header.querySelectorAll('a[href]')) {
        const href = a.getAttribute('href') || (a as HTMLAnchorElement).href || '';
        if (isHomeHref(href) && tryClick(a)) return true;
      }
      const imgLink = header.querySelector('a img, a svg, a [class*="logo" i]');
      if (imgLink) {
        const a = imgLink.closest('a') || imgLink;
        if (tryClick(a)) return true;
      }
    }
    for (const a of document.querySelectorAll('a[href]')) {
      const href = a.getAttribute('href') || '';
      if ((href === '/' || isHomeHref(href)) && tryClick(a)) return true;
    }
    return false;
  }, baseUrl);
  if (!clicked) return false;
  await page.waitForLoadState('domcontentloaded').catch(() => {});
  return isHomeUrl(page.url(), baseUrl);
}

async function clickHome(page: Page, baseUrl: string) {
  await page.evaluate(() => window.scrollTo(0, 0)).catch(() => {});
  await page.waitForTimeout(200);
  if (await clickHomeLogoJs(page, baseUrl)) {
    await publishLiveFrame(page);
    console.log('✓ Returned to homepage via site logo');
    return;
  }
  const brand = siteBrand(baseUrl);
  const candidates = [
    page.getByRole('link', { name: new RegExp(`^${escapeRegExp(brand)}$`, 'i') }).first(),
    page.getByRole('link', { name: /^home$/i }).first(),
    page.locator("header a[href='/']").first(),
    page.locator('header a:has(img), header a:has(svg)').first(),
    page.locator(`a:has(img[alt*='logo' i]), a:has(img[alt*='${brand}' i])`).first(),
  ];
  for (const loc of candidates) {
    if ((await loc.count()) > 0) {
      await loc.click({ timeout: 15_000 });
      await page.waitForLoadState('domcontentloaded').catch(() => {});
      if (await isHomeUrl(page.url(), baseUrl)) {
        await publishLiveFrame(page);
        console.log('✓ Returned to homepage via UI click');
        return;
      }
    }
  }
  throw new Error('Could not return to homepage via logo or Home link — use UI navigation, not URLs');
}

async function clickMenuLabel(page: Page, label: string) {
  await page.evaluate(() => window.scrollTo(0, 0)).catch(() => {});
  await page.waitForTimeout(200);
  const escaped = escapeRegExp(label);
  const pattern = new RegExp(escaped, 'i');
  const scopes = [
    page.getByRole('link', { name: pattern }).first(),
    page.locator('.oxd-main-menu-item, [role=menuitem], nav a, .sidebar a, .menu-item, header a, header span')
      .filter({ hasText: pattern }).first(),
    page.getByRole('button', { name: pattern }).first(),
  ];

  for (const loc of scopes) {
    if ((await loc.count()) > 0) {
      try {
        await loc.hover({ timeout: 5000 });
        await page.waitForTimeout(400);
      } catch {
        /* hover optional */
      }
      await loc.click({ timeout: 15_000 });
      await page.waitForLoadState('domcontentloaded').catch(() => {});
      await publishLiveFrame(page);
      console.log(`✓ Clicked menu "${label}" — ${page.url()}`);
      return;
    }
  }

  // Mega-menu: hover category seed then click full label
  const seeds = [label];
  if (label.includes(',')) seeds.push(label.split(',')[0].trim());
  if (label.includes('&')) {
    seeds.push(label.replace(/&/g, 'and').trim());
    label.split(/[,/&]/).forEach((p) => {
      const t = p.trim();
      if (t.length >= 3) seeds.push(t);
    });
  }
  const seen = new Set<string>();
  for (const seed of seeds) {
    const key = seed.toLowerCase();
    if (!key || seen.has(key)) continue;
    seen.add(key);
    const trigger = page.locator('header, nav, [role=navigation]').getByText(new RegExp(escapeRegExp(seed), 'i')).first();
    if ((await trigger.count()) === 0) continue;
    await trigger.hover({ timeout: 5000 });
    await page.waitForTimeout(500);
    const flyout = page.getByRole('link', { name: pattern }).first();
    if ((await flyout.count()) > 0) {
      await flyout.click({ timeout: 15_000 });
      await page.waitForLoadState('domcontentloaded').catch(() => {});
      await publishLiveFrame(page);
      console.log(`✓ Clicked mega-menu "${label}" — ${page.url()}`);
      return;
    }
  }

  throw new Error(`Could not find menu element to click: ${label}`);
}

async function runOneStep(page: Page, step: DiscoveryStep, baseUrl: string) {
  const desc = step.description || '';
  const lower = desc.toLowerCase();
  const action = (step.action || '').toLowerCase();
  const interaction = (step.interaction || '').toLowerCase();

  if (action === 'dismiss' || interaction === 'popup') {
    console.log(`→ ${desc || 'Dismiss blocking popups'}`);
    await dismissPopups(page);
    return;
  }

  if (interaction === 'home' || (action === 'click' && /return to homepage|via site logo/i.test(desc))) {
    console.log(`→ ${desc}`);
    await clickHome(page, baseUrl);
    return;
  }

  if (action === 'navigate') {
    // Only the first application entry may use URL navigation; menu journeys use UI clicks.
    if (interaction === 'menu' || /menu|category/i.test(desc)) {
      const label = step.element || quotedText(desc) || desc;
      console.log(`→ Click menu "${label}" (UI navigation)`);
      await clickMenuLabel(page, label);
      return;
    }
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
    await dismissPopups(page);
    return;
  }

  if (action === 'fill') {
    console.log(`→ ${desc}`);
    await fillFormField(page, step);
    console.log(`✓ ${desc}`);
    return;
  }

  if (lower.includes('login') || lower.includes('sign in')) {
    console.log(`→ ${desc}`);
    await tryGenericLogin(page);
    console.log(`✓ ${desc}`);
    return;
  }

  if (action === 'click' || lower.includes('click') || lower.startsWith('open ')) {
    const label = step.element || quotedText(desc) || desc.replace(/^(click|open)\s+/i, '').trim();
    if (interaction === 'menu' || /main navigation|main menu|mega-menu/i.test(desc)) {
      console.log(`→ Click menu "${label}"`);
      await clickMenuLabel(page, label);
      return;
    }
    console.log(`→ Click "${label}"`);
    const escaped = escapeRegExp(label);
    const link = page.getByRole('link', { name: new RegExp(escaped, 'i') }).first();
    const menu = page.locator(
      '.oxd-main-menu-item, [role=menuitem], nav a, .sidebar a, .menu-item, header a'
    ).filter({ hasText: new RegExp(escaped, 'i') }).first();
    const btn = page.getByRole('button', { name: new RegExp(escaped, 'i') }).first();
    const submitInput = page.locator(`input[type=submit][value="${label}" i], input[type=submit]`).filter({ hasText: new RegExp(escaped, 'i') }).first();

    if ((await menu.count()) > 0) {
      await menu.click({ timeout: 15_000 });
    } else if ((await link.count()) > 0) {
      await link.click({ timeout: 15_000 });
    } else if ((await submitInput.count()) > 0) {
      await submitInput.click({ timeout: 15_000 });
    } else if ((await btn.count()) > 0) {
      await btn.click({ timeout: 15_000 });
    } else {
      throw new Error(`Could not find clickable DOM element: ${label}`);
    }
    await page.waitForLoadState('domcontentloaded').catch(() => {});
    await publishLiveFrame(page);
    console.log(`✓ After click: ${page.url()}`);
    return;
  }

  if (action === 'verify' || lower.includes('verify') || lower.includes('confirm')) {
    console.log(`→ ${desc}`);
    await expect(page.locator('body')).toBeVisible();
    if (step.url) {
      const pathPart = step.url.replace(/^https?:\/\/[^/]+/, '').replace(/^\//, '');
      if (pathPart) {
        expect(page.url()).toContain(pathPart);
      }
    }
    if (step.target) {
      await expect(page).toHaveURL(new RegExp(escapeRegExp(step.target), 'i'));
    }
    const title = await page.title();
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
      await dismissPopups(page);
      await runOneStep(page, step, baseUrl);
      reportQeosStepAt(i, desc, 'passed');
    } catch (err) {
      reportQeosStepAt(i, desc, 'failed');
      throw err;
    }
  }
}

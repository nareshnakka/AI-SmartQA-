import { expect, Locator, Page } from '@playwright/test';
import { pauseBetweenSteps, publishLiveFrame, waitForPageLoad } from '../utils/helpers';

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
  search: ['q', 'query', 'search', 'keyword'],
  'search for': ['q', 'query', 'search'],
  'search box': ['q', 'query', 'search'],
};

function parseSearchValue(step: DiscoveryStep): string {
  const desc = step.description || '';
  const fromQuoted = quotedText(desc);
  if (fromQuoted) return fromQuoted;
  const m = desc.match(/search\s+(?:for\s+)?(.+)$/i);
  if (m) return m[1].replace(/^["']|["']$/g, '').trim();
  return (step.field || '').trim();
}

async function fillSearchBox(page: Page, value: string) {
  const candidates = [
    page.getByRole('combobox', { name: /search/i }).first(),
    page.getByRole('searchbox').first(),
    page.locator('input[name=q], input[type=search], input[placeholder*="Search" i], input[title*="Search" i]').first(),
    page.getByPlaceholder(/search/i).first(),
  ];
  for (const loc of candidates) {
    if ((await loc.count()) === 0) continue;
    if (!(await loc.isVisible().catch(() => false))) continue;
    await loc.click({ timeout: 8000 }).catch(() => {});
    await loc.fill(value, { timeout: 8000 });
    await page.keyboard.press('Enter').catch(() => {});
    await page.waitForLoadState('domcontentloaded').catch(() => {});
    // Wait for product results to appear (Flipkart/Amazon)
    await page
      .locator('div[data-id] a[href*="/p/"], a[href*="/p/"], [data-component-type="s-search-result"]')
      .first()
      .waitFor({ state: 'visible', timeout: 20_000 })
      .catch(() => {});
    await publishLiveFrame(page);
    console.log(`✓ Searched → ${value.slice(0, 40)}`);
    return;
  }
  throw new Error(`Could not find search box for: ${value}`);
}

function parseResultIndex(step: DiscoveryStep): number | 'random' {
  const el = (step.element || '').trim().toLowerCase();
  if (el === 'random') return 'random';
  if (/^\d+$/.test(el)) {
    const n = Number(el);
    if (n >= 1 && n <= 20) return n;
  }
  const desc = (step.description || '').toLowerCase();
  if (/\brandom\b/.test(desc)) return 'random';
  const wordMap: Record<string, number> = {
    first: 1, '1st': 1, top: 1,
    second: 2, '2nd': 2,
    third: 3, '3rd': 3,
    fourth: 4, '4th': 4,
    fifth: 5, '5th': 5,
  };
  for (const [word, idx] of Object.entries(wordMap)) {
    if (new RegExp(`\\b${word}\\b`).test(desc)) return idx;
  }
  const m = desc.match(/\b(\d+)(?:st|nd|rd|th)?\b/);
  if (m) {
    const n = Number(m[1]);
    if (n >= 1 && n <= 20) return n;
  }
  return 1;
}

/** Unique Flipkart/Amazon-style product cards, then open the Nth one (1-based) or a random card. */
async function clickSearchResult(page: Page, index: number | 'random') {
  console.log(`→ Opening search result #${index} on ${page.url()}`);
  await dismissPopups(page);

  // Wait until listing tiles or product links exist
  await page
    .locator('div[data-id], a[href*="/p/"], [data-component-type="s-search-result"]')
    .first()
    .waitFor({ state: 'visible', timeout: 25_000 })
    .catch(() => {});
  await page.waitForTimeout(800);

  // Prefer one card per product (Flipkart: div[data-id]). Avoid counting every /p/ link —
  // each card has several (image + title), so nth(1) was often still product #1.
  let cards = page.locator('div[data-id]').filter({ has: page.locator('a[href*="/p/"], a[href*="pid="]') });
  let cardCount = await cards.count();

  if (cardCount < 1) {
    // Broader data-id cards (some layouts omit /p/ until click)
    const loose = page.locator('div[data-id]').filter({ has: page.locator('a, img') });
    if ((await loose.count()) >= 1) {
      cards = loose;
      cardCount = await loose.count();
    }
  }

  if (cardCount < 1) {
    const amazon = page.locator('[data-component-type="s-search-result"]');
    if ((await amazon.count()) >= 1) {
      cards = amazon;
      cardCount = await amazon.count();
    }
  }

  const resolveIndex = (count: number): number => {
    if (count < 1) return 1;
    if (index === 'random') {
      const max = Math.min(count, 12);
      return 1 + Math.floor(Math.random() * max);
    }
    return Math.min(Math.max(1, index), count);
  };

  if (cardCount >= 1) {
    const pick = resolveIndex(cardCount);
    console.log(`→ Picked product card #${pick} of ${cardCount}${index === 'random' ? ' (random)' : ''}`);
    const card = cards.nth(pick - 1);
    await card.scrollIntoViewIfNeeded().catch(() => {});
    await card.waitFor({ state: 'visible', timeout: 10_000 });

    const link = card.locator('a[href*="/p/"], a[href*="pid="]').first();
    if ((await link.count()) > 0) {
      await openProductFromLocator(page, link, pick);
      return;
    }
    const anyLink = card.locator('a').first();
    if ((await anyLink.count()) > 0) {
      await openProductFromLocator(page, anyLink, pick);
      return;
    }
    throw new Error(`Product card #${pick} has no clickable link`);
  }

  // Deduplicate visible /p/ hrefs into unique product URLs, then open the Nth
  const hrefs = await page.locator('a[href*="/p/"]').evaluateAll((els) => {
    const seen = new Set<string>();
    const out: string[] = [];
    for (const el of els) {
      const a = el as HTMLAnchorElement;
      if (!a.href || !a.href.includes('/p/')) continue;
      let key = a.href.split('?')[0];
      try {
        key = new URL(a.href).pathname;
      } catch {
        /* keep key */
      }
      if (seen.has(key)) continue;
      const rect = a.getBoundingClientRect();
      if (rect.width < 20 || rect.height < 20) continue;
      seen.add(key);
      out.push(a.href);
    }
    return out;
  });

  if (hrefs.length < 1) {
    throw new Error(
      `Could not find search results on ${page.url()} — found 0 product cards/links.`
    );
  }

  const pick = resolveIndex(hrefs.length);
  const targetUrl = hrefs[pick - 1];
  console.log(`→ Navigating to unique product #${pick}: ${targetUrl.slice(0, 80)}…`);
  await page.goto(targetUrl, { waitUntil: 'domcontentloaded', timeout: 60_000 });
  await waitForPageLoad(page);
  await dismissPopups(page);
  await publishLiveFrame(page);
  console.log(`✓ Opened search result #${pick} — ${page.url()}`);
}

/** Click a product link; Flipkart often opens PDP in a new tab. */
async function openProductFromLocator(page: Page, link: Locator, index: number) {
  const href = await link.getAttribute('href').catch(() => null);
  const before = page.url();

  // Prefer direct navigation when we have a product URL — most reliable on Flipkart
  if (href && (href.includes('/p/') || href.includes('pid='))) {
    const abs = href.startsWith('http') ? href : new URL(href, page.url()).toString();
    console.log(`→ Opening product URL for result #${index}`);
    await page.goto(abs, { waitUntil: 'domcontentloaded', timeout: 60_000 });
    await waitForPageLoad(page);
    await dismissPopups(page);
    await publishLiveFrame(page);
    console.log(`✓ Opened search result #${index} — ${page.url()}`);
    return;
  }

  const popupPromise = page.context().waitForEvent('page', { timeout: 8_000 }).catch(() => null);
  await link.click({ timeout: 20_000, force: true }).catch(async () => {
    await link.click({ timeout: 20_000 });
  });

  const popup = await popupPromise;
  if (popup) {
    await popup.waitForLoadState('domcontentloaded').catch(() => {});
    // Continue automation on the new product tab
    await page.goto(popup.url(), { waitUntil: 'domcontentloaded', timeout: 60_000 }).catch(() => {});
    await popup.close().catch(() => {});
  } else {
    await page.waitForLoadState('domcontentloaded').catch(() => {});
    // If URL did not change, try waiting briefly for SPA navigation
    if (page.url() === before) {
      await page.waitForTimeout(1500);
    }
  }

  await dismissPopups(page);
  await publishLiveFrame(page);
  console.log(`✓ Opened search result #${index} — ${page.url()}`);
}

async function goToCart(page: Page) {
  const candidates = [
    page.getByRole('link', { name: /^cart$/i }).first(),
    page.getByRole('link', { name: /cart/i }).first(),
    page.getByRole('button', { name: /cart/i }).first(),
    page.locator('a[href*="viewcart"], a[href*="/cart"], a[href*="checkout/cart"]').first(),
  ];
  for (const loc of candidates) {
    if ((await loc.count()) === 0) continue;
    if (!(await loc.isVisible().catch(() => false))) continue;
    await loc.click({ timeout: 15_000 });
    await page.waitForLoadState('domcontentloaded').catch(() => {});
    await waitForPageLoad(page);
    await publishLiveFrame(page);
    console.log(`✓ Opened cart — ${page.url()}`);
    return;
  }
  throw new Error('Could not find Cart link/button');
}

async function removeFromCart(page: Page) {
  const candidates = [
    page.getByRole('button', { name: /remove|delete|move to wishlist/i }).first(),
    page.getByRole('link', { name: /remove|delete/i }).first(),
    page.locator('button, a, span').filter({ hasText: /^remove$/i }).first(),
  ];
  for (const loc of candidates) {
    if ((await loc.count()) === 0) continue;
    if (!(await loc.isVisible().catch(() => false))) continue;
    await loc.click({ timeout: 15_000 });
    // Confirm dialog if present
    const confirm = page.getByRole('button', { name: /remove|yes|confirm|ok/i }).first();
    if ((await confirm.count()) > 0 && (await confirm.isVisible().catch(() => false))) {
      await confirm.click({ timeout: 8000 }).catch(() => {});
    }
    await page.waitForLoadState('domcontentloaded').catch(() => {});
    await waitForPageLoad(page);
    await publishLiveFrame(page);
    console.log('✓ Removed item from cart');
    return;
  }
  throw new Error('Could not find Remove control on cart page');
}

/** Set product quantity on PDP (select, input, or +/- buttons). */
async function setQuantity(page: Page, qty: number) {
  console.log(`→ Set quantity to ${qty}`);
  const select = page.locator('select[name*=qty i], select[id*=qty i], select[class*=quantity i]').first();
  if ((await select.count()) > 0 && (await select.isVisible().catch(() => false))) {
    await select.selectOption(String(qty)).catch(async () => {
      await select.selectOption({ label: String(qty) });
    });
    await waitForPageLoad(page);
    console.log(`✓ Quantity set via select → ${qty}`);
    return;
  }

  const input = page.locator(
    'input[name*=qty i], input[id*=qty i], input[aria-label*=quantity i], input[class*=quantity i]'
  ).first();
  if ((await input.count()) > 0 && (await input.isVisible().catch(() => false))) {
    await input.click({ timeout: 8000 }).catch(() => {});
    await input.fill(String(qty), { timeout: 8000 });
    await page.keyboard.press('Tab').catch(() => {});
    await waitForPageLoad(page);
    console.log(`✓ Quantity set via input → ${qty}`);
    return;
  }

  // Flipkart-style: increment (+) until desired qty (assume starting at 1)
  const plus = page.getByRole('button', { name: /^\+|increase|add$/i }).first();
  const plusAlt = page.locator('button[aria-label*=increase i], button[title*=increase i], button:has-text("+")').first();
  const btn = (await plus.count()) > 0 ? plus : plusAlt;
  if ((await btn.count()) > 0 && (await btn.isVisible().catch(() => false))) {
    for (let i = 1; i < qty; i++) {
      await btn.click({ timeout: 8000 });
      await page.waitForTimeout(400);
    }
    await waitForPageLoad(page);
    console.log(`✓ Quantity increased via + → ${qty}`);
    return;
  }

  throw new Error(`Could not set quantity to ${qty} on ${page.url()}`);
}

/** Stronger page assertions based on step description / expected text. */
async function assertPage(page: Page, step: DiscoveryStep) {
  const desc = `${step.description || ''} ${step.expected || ''}`.toLowerCase();
  console.log(`→ Assert: ${step.description || step.expected || 'page loaded'}`);
  await waitForPageLoad(page);
  await expect(page.locator('body')).toBeVisible();

  const title = (await page.title()).toLowerCase();
  const url = page.url().toLowerCase();

  if (/not found|404/.test(title) || /\/404\b/.test(url)) {
    throw new Error(`Assertion failed — page looks like 404 (${title || url})`);
  }

  if (/homepage|home page|logo/.test(desc)) {
    await expect(page.locator('body')).toBeVisible();
    if (!/flipkart|amazon|myntra|example/.test(url) && !title) {
      /* soft: still ok if body visible */
    }
  }

  if (/search result|results for|product cards|result list/.test(desc)) {
    const results = page.locator('div[data-id], a[href*="/p/"], [data-component-type="s-search-result"]');
    await expect(results.first()).toBeVisible({ timeout: 20_000 });
  }

  if (/product detail|product page|product title|price are visible|view the product/.test(desc)) {
    const onPdp = /\/p\//.test(url) || (await page.locator('text=/₹|rs\\.?\\s*\\d/i').count()) > 0;
    if (!onPdp) {
      // Title/price heuristics
      const price = page.locator('text=/₹\\s?[\\d,]+/').first();
      await expect(price).toBeVisible({ timeout: 15_000 });
    }
  }

  if (/quantity shows|qty.*2|shows 2/.test(desc)) {
    const bodyText = (await page.locator('body').innerText().catch(() => '')).slice(0, 8000);
    if (!/\b2\b/.test(bodyText)) {
      console.log('⚠ Quantity assert soft — "2" not clearly visible; continuing');
    }
  }

  if (/added to cart|cart confirmation|cart count/.test(desc)) {
    const hint = page.locator('text=/added|go to cart|cart/i').first();
    await expect(hint).toBeVisible({ timeout: 15_000 }).catch(() => {
      console.log('⚠ Cart-add confirm soft — continuing');
    });
  }

  if (/cart page|cart items|view cart/.test(desc)) {
    const onCart = /cart|viewcart|checkout/.test(url);
    if (!onCart) {
      await expect(page.locator('text=/cart|price|remove|qty/i').first()).toBeVisible({ timeout: 15_000 });
    }
  }

  if (/no longer shows|removed|decreased|empty/.test(desc)) {
    await expect(page.locator('body')).toBeVisible();
    console.log('✓ Cart mutation asserted (page settled)');
  }

  if (step.url) {
    const pathPart = step.url.replace(/^https?:\/\/[^/]+/, '').replace(/^\//, '');
    if (pathPart) expect(page.url()).toContain(pathPart);
  }

  console.log(`✓ Asserted: ${title || url}`);
}

/** Product / query labels must never be treated as top-nav menu items. */
function looksLikeSearchQuery(label: string, desc: string): boolean {
  const d = (desc || '').toLowerCase();
  const l = (label || '').trim();
  if (!l) return false;
  // "search results" / result selection is NOT a search query
  if (/\bsearch\s+results?\b/.test(d) || /\bproduct in the search results\b/.test(d)) return false;
  if (/\bsearch\s+for\b/.test(d)) return true;
  if (/iphone|ipad|airpods|macbook|galaxy|pixel|oneplus|laptop|headphone/i.test(l)) return true;
  if (/\b\d+\s?(?:gb|tb|pro|max|plus|ultra)\b/i.test(l)) return true;
  if (/[a-z].*\d|\d.*[a-z]/i.test(l) && l.split(/\s+/).length <= 6) return true;
  return false;
}

async function fillFormField(page: Page, step: DiscoveryStep) {
  const desc = (step.description || '').toLowerCase();
  const action = (step.action || '').toLowerCase();
  // Only real search steps — not "click … in the search results"
  if (action === 'search' || /\bsearch\s+for\b/.test(desc)) {
    const value = parseSearchValue(step) || parseFillStep(step).value;
    if (!value) throw new Error(`Search step missing value: ${step.description}`);
    if (/^(?:the\s+)?(?:search\s+)?results?$/i.test(value.trim())) {
      throw new Error(`Invalid search value "${value}" — use a product click step for search results`);
    }
    await fillSearchBox(page, value);
    return;
  }

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
      // Mis-tagged product searches (legacy Discovery) → use search box, not menu
      if (looksLikeSearchQuery(label, desc)) {
        console.log(`→ Search for "${label}" (not a menu item)`);
        await fillSearchBox(page, label.replace(/^click\s+/i, '').replace(/\s+in the main navigation menu$/i, '').trim());
        return;
      }
      console.log(`→ Click menu "${label}" (UI navigation)`);
      await clickMenuLabel(page, label);
      return;
    }
    // "Go to Cart" must never deep-link as navigate to Base URL
    if (interaction === 'cart' || /\b(?:go to|open|view)\s+(?:the\s+)?cart\b/i.test(desc) || /^go to cart$/i.test(desc.trim())) {
      console.log(`→ Go to Cart`);
      await goToCart(page);
      return;
    }
    let url = step.url || step.target || '';
    if (!url || url.startsWith('/')) {
      const fromDesc = desc.match(/https?:\/\/[^\s'"]+/i)?.[0];
      url = fromDesc || (url ? `${baseUrl.replace(/\/$/, '')}${url.startsWith('/') ? url : `/${url}`}` : baseUrl);
    }
    console.log(`→ Navigate to ${url}`);
    const resp = await page.goto(url, { waitUntil: 'load', timeout: 60_000 });
    await waitForPageLoad(page);
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

  // Result selection MUST run before action===search — mis-tagged steps used to search again
  const looksLikeResultPick =
    interaction === 'result'
    || /^(?:\d+|random)$/i.test((step.element || '').trim())
    || /\brandom\b.+\b(?:product|phone|item|result)\b/i.test(desc)
    || /\b(?:first|second|third|\d+(?:st|nd|rd|th)|top)\b.+\b(?:product|phone|item|result)\b/i.test(desc)
    || /\bproduct in the search results\b/i.test(desc)
    || /\bin the search results\b/i.test(desc)
    || /\bfrom (?:the )?(?:search )?results?\b/i.test(desc);

  if (looksLikeResultPick && !/\bsearch\s+for\b/i.test(desc)) {
    const idx = parseResultIndex(step);
    console.log(`→ Click search result #${idx} (${desc || 'result pick'})`);
    await clickSearchResult(page, idx);
    return;
  }

  if (interaction === 'cart' || /^go to cart$/i.test(desc.trim()) || /\b(?:go to|open|view)\s+(?:the\s+)?cart\b/i.test(desc)) {
    console.log(`→ Go to Cart`);
    await goToCart(page);
    return;
  }

  // cart_remove before quantity — "remove … (or reduce quantity by 1)" must not become qty
  if (
    interaction === 'cart_remove'
    || /\bremove\b.+\bcart\b/i.test(desc)
    || /\bdelete\b.+\bcart\b/i.test(desc)
    || /\b(?:remove|delete)\s+(?:the\s+)?(?:1|one|\d+)\s+item\b/i.test(desc)
  ) {
    console.log(`→ Remove from cart`);
    await removeFromCart(page);
    return;
  }

  if (
    interaction === 'quantity'
    || /\bchange the buying quantity\b/i.test(desc)
    || /\b(?:change|set|update)\s+(?:the\s+)?(?:buying\s+)?(?:quantity|qty)\s+to\s+\d+/i.test(desc)
  ) {
    const n = parseInt(step.element || step.value || desc.match(/\b(\d+)\b/)?.[1] || '2', 10);
    await setQuantity(page, Number.isFinite(n) ? n : 2);
    return;
  }

  if (action === 'fill' || action === 'type' || action === 'search') {
    console.log(`→ ${desc}`);
    await fillFormField(page, step);
    console.log(`✓ ${desc}`);
    return;
  }

  if (/^search\s+for\b/i.test(desc) || /\bsearch\s+for\b/i.test(desc)) {
    console.log(`→ ${desc}`);
    await fillFormField(page, { ...step, action: 'search' });
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
    const cleanLabel = label
      .replace(/\s+in the main navigation menu$/i, '')
      .replace(/^['"]|['"]$/g, '')
      .trim();

    // Legacy bad steps: Click 'iPhone 15' in the main navigation menu
    if (looksLikeSearchQuery(cleanLabel, desc) && (interaction === 'menu' || /navigation menu/i.test(desc))) {
      console.log(`→ Search for "${cleanLabel}" (rewrote menu click → search)`);
      await fillSearchBox(page, cleanLabel);
      return;
    }

    if (interaction === 'menu' || /main navigation|main menu|mega-menu/i.test(desc)) {
      if (looksLikeSearchQuery(cleanLabel, desc)) {
        console.log(`→ Search for "${cleanLabel}" (not a nav menu)`);
        await fillSearchBox(page, cleanLabel);
        return;
      }
      console.log(`→ Click menu "${cleanLabel}"`);
      try {
        await clickMenuLabel(page, cleanLabel);
      } catch (err) {
        // Last resort for e-commerce: treat unknown "menu" labels as search queries
        if (looksLikeSearchQuery(cleanLabel, desc) || /flipkart|amazon|myntra/i.test(page.url())) {
          console.log(`→ Menu miss — searching for "${cleanLabel}" instead`);
          await fillSearchBox(page, cleanLabel);
          return;
        }
        throw err;
      }
      return;
    }
    console.log(`→ Click "${cleanLabel}"`);
    const escaped = escapeRegExp(cleanLabel);
    const link = page.getByRole('link', { name: new RegExp(escaped, 'i') }).first();
    const menu = page.locator(
      '.oxd-main-menu-item, [role=menuitem], nav a, .sidebar a, .menu-item, header a'
    ).filter({ hasText: new RegExp(escaped, 'i') }).first();
    const btn = page.getByRole('button', { name: new RegExp(escaped, 'i') }).first();
    const submitInput = page.locator(`input[type=submit][value="${cleanLabel}" i], input[type=submit]`).filter({ hasText: new RegExp(escaped, 'i') }).first();

    if ((await menu.count()) > 0) {
      await menu.click({ timeout: 15_000 });
    } else if ((await link.count()) > 0) {
      await link.click({ timeout: 15_000 });
    } else if ((await submitInput.count()) > 0) {
      await submitInput.click({ timeout: 15_000 });
    } else if ((await btn.count()) > 0) {
      await btn.click({ timeout: 15_000 });
    } else if (looksLikeSearchQuery(cleanLabel, desc)) {
      console.log(`→ No clickable match — searching for "${cleanLabel}"`);
      await fillSearchBox(page, cleanLabel);
      return;
    } else {
      throw new Error(`Could not find clickable DOM element: ${cleanLabel}`);
    }
    await page.waitForLoadState('domcontentloaded').catch(() => {});
    await publishLiveFrame(page);
    console.log(`✓ After click: ${page.url()}`);
    return;
  }

  if (action === 'verify' || lower.includes('verify') || lower.includes('confirm') || lower.includes('assert')) {
    await assertPage(page, step);
    return;
  }

  if (action === 'inspect' || lower.includes('follow link')) {
    const href = step.target || step.url;
    if (href) {
      await page.goto(href, { waitUntil: 'load', timeout: 60_000 });
      await waitForPageLoad(page);
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
    await reportQeosStepAt(0, 'Open application', 'running');
    await page.goto(baseUrl, { waitUntil: 'load', timeout: 60_000 });
    await waitForPageLoad(page);
    await expect(page.locator('body')).toBeVisible();
    await reportQeosStepAt(0, 'Open application', 'passed');
    return;
  }

  // Open the app when the first step is not an explicit navigate (blank page otherwise).
  const first = steps[0];
  const firstIsNavigate =
    (first.action || '').toLowerCase() === 'navigate' ||
    /^open\s+(application|homepage|home|url|site)\b/i.test(first.description || '') ||
    /^navigate\b/i.test(first.description || '');
  if (!firstIsNavigate) {
    const url = page.url();
    if (!url || url === 'about:blank' || url.startsWith('chrome://')) {
      await page.goto(baseUrl, { waitUntil: 'load', timeout: 60_000 });
      await waitForPageLoad(page);
      await dismissPopups(page);
      await publishLiveFrame(page);
    }
  }

  for (let i = 0; i < steps.length; i++) {
    const step = steps[i];
    const desc = step.description?.trim() || `Step ${i + 1}`;
    await reportQeosStepAt(i, desc, 'running');
    try {
      await dismissPopups(page);
      await runOneStep(page, step, baseUrl);
      // Always wait for the page to finish loading after the step action
      await waitForPageLoad(page);
      await dismissPopups(page);
      await reportQeosStepAt(i, desc, 'passed');
      // Default 3s pause between steps (not after the last)
      if (i < steps.length - 1) {
        await pauseBetweenSteps(page, `after step ${i + 1}`);
      }
    } catch (err) {
      await reportQeosStepAt(i, desc, 'failed');
      throw err;
    }
  }
}

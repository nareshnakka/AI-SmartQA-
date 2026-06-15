"""Playwright-based application discovery with HTTP fallback."""

import re
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse

import httpx
import structlog

from app.config import settings

logger = structlog.get_logger()


class _LinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[str] = []
        self.title: str = ""
        self.forms: int = 0
        self.buttons: int = 0
        self.inputs: int = 0
        self._in_title = False

    def handle_starttag(self, tag: str, attrs: list) -> None:
        attr = dict(attrs)
        if tag == "a" and attr.get("href"):
            self.links.append(attr["href"])
        elif tag == "form":
            self.forms += 1
        elif tag in ("button", "input"):
            if tag == "button" or attr.get("type") in ("submit", "button"):
                self.buttons += 1
            if tag == "input":
                self.inputs += 1

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self.title += data

    def handle_startendtag(self, tag: str, attrs: list) -> None:
        if tag == "title":
            self._in_title = True

    def handle_endtag(self, tag: str) -> None:
        if tag == "title":
            self._in_title = False


async def crawl_application(
    base_url: str,
    max_pages: int | None = None,
    username: str | None = None,
    password: str | None = None,
) -> dict:
    max_pages = max_pages or settings.discovery_max_pages
    parsed = urlparse(base_url if "://" in base_url else f"https://{base_url}")
    origin = f"{parsed.scheme}://{parsed.netloc}"

    if settings.playwright_enabled:
        try:
            result = await _crawl_playwright(origin, base_url, max_pages, username, password)
            if result.get("pages"):
                return result
        except Exception as e:
            err = str(e).encode("ascii", errors="replace").decode("ascii")[:200]
            logger.warning("playwright_discovery_failed", error=err)

    return await _crawl_http(origin, base_url, max_pages)


async def _crawl_playwright(
    origin: str,
    start_url: str,
    max_pages: int,
    username: str | None,
    password: str | None,
) -> dict:
    from playwright.async_api import async_playwright

    pages: list[dict] = []
    visited: set[str] = set()
    queue = [start_url if "://" in start_url else origin]

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=settings.playwright_headless)
        context = await browser.new_context(ignore_https_errors=True)
        page = await context.new_page()

        if username and password:
            await _attempt_login(page, username, password)

        while queue and len(pages) < max_pages:
            url = queue.pop(0)
            if url in visited:
                continue
            visited.add(url)

            try:
                resp = await page.goto(url, timeout=settings.playwright_timeout_ms, wait_until="domcontentloaded")
                title = await page.title()
                links = await page.eval_on_selector_all(
                    "a[href]",
                    "els => els.map(e => e.getAttribute('href')).filter(Boolean)",
                )
                forms = await page.locator("form").count()
                buttons = await page.locator("button, input[type=submit]").count()
                inputs = await page.locator("input, textarea, select").count()

                pages.append({
                    "url": page.url,
                    "title": title,
                    "status": resp.status if resp else 0,
                    "forms": forms,
                    "buttons": buttons,
                    "inputs": inputs,
                })

                for href in links:
                    absolute = urljoin(page.url, href)
                    if _same_origin(origin, absolute) and absolute not in visited:
                        queue.append(absolute)
            except Exception as e:
                pages.append({"url": url, "title": "", "status": 0, "error": str(e)[:200]})

        await browser.close()

    return _build_discovery_result(origin, pages, mode="browser")


async def _attempt_login(page, username: str, password: str) -> None:
    for user_sel in ["input[name=username]", "input[name=email]", "input[type=email]", "#username"]:
        if await page.locator(user_sel).count():
            await page.fill(user_sel, username)
            break
    for pass_sel in ["input[name=password]", "input[type=password]", "#password"]:
        if await page.locator(pass_sel).count():
            await page.fill(pass_sel, password)
            break
    for btn in ["button[type=submit]", "input[type=submit]", "button:has-text('Log in')", "button:has-text('Sign in')"]:
        if await page.locator(btn).count():
            await page.locator(btn).first.click()
            await page.wait_for_timeout(2000)
            break


async def _crawl_http(origin: str, start_url: str, max_pages: int) -> dict:
    url = start_url if "://" in start_url else origin
    pages: list[dict] = []
    visited: set[str] = set()
    queue = [url]

    async with httpx.AsyncClient(follow_redirects=True, timeout=20, verify=False) as client:
        while queue and len(pages) < max_pages:
            current = queue.pop(0)
            if current in visited:
                continue
            visited.add(current)
            try:
                resp = await client.get(current)
                parser = _LinkParser()
                parser.feed(resp.text)
                pages.append({
                    "url": str(resp.url),
                    "title": parser.title.strip() or _title_from_html(resp.text),
                    "status": resp.status_code,
                    "forms": parser.forms,
                    "buttons": parser.buttons,
                    "inputs": parser.inputs,
                })
                for href in parser.links:
                    absolute = urljoin(str(resp.url), href)
                    if _same_origin(origin, absolute) and absolute not in visited:
                        queue.append(absolute)
            except Exception as e:
                pages.append({"url": current, "title": "", "status": 0, "error": str(e)[:200]})

    return _build_discovery_result(origin, pages, mode="http")


def _build_discovery_result(origin: str, pages: list[dict], mode: str) -> dict:
    screens = []
    flows = []
    apis: list[dict] = []

    for i, p in enumerate(pages):
        title = p.get("title") or f"Page {i + 1}"
        name = title[:80] if title else urlparse(p["url"]).path or "Home"
        screens.append({
            "name": name,
            "url": p["url"],
            "url_pattern": p["url"],
            "elements": {
                "forms": p.get("forms", 0),
                "buttons": p.get("buttons", 0),
                "inputs": p.get("inputs", 0),
            },
            "status": p.get("status", 0),
        })

    if pages:
        flows.append({
            "id": "flow-crawled",
            "name": "Crawled Navigation",
            "entry_url": pages[0]["url"],
            "steps": [s["name"] for s in screens[:8]],
            "risk": "medium",
            "source": mode,
        })

    for p in pages:
        path = urlparse(p["url"]).path
        if "/api/" in path:
            apis.append({"method": "GET", "path": path, "purpose": "discovered"})

    return {
        "mode": mode,
        "pages_crawled": len(pages),
        "pages": pages,
        "screens": screens,
        "flow_map": flows,
        "apis": apis,
    }


def _same_origin(origin: str, url: str) -> bool:
    try:
        return urlparse(origin).netloc == urlparse(url).netloc
    except Exception:
        return False


def _title_from_html(html: str) -> str:
    m = re.search(r"<title[^>]*>([^<]+)</title>", html, re.I)
    return m.group(1).strip() if m else ""

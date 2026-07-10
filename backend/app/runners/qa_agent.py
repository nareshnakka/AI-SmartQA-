"""QA Agent — navigates applications like a real tester and captures test cases."""

import re
import uuid
from datetime import datetime, timezone
from urllib.parse import urljoin, urlparse

import structlog

from app.config import settings

logger = structlog.get_logger()

SKIP_TEXT = re.compile(
    r"delete|remove|logout|log out|sign out|cancel subscription|destroy|upgrade",
    re.I,
)

_BLOCKED_EXTERNAL_HOSTS = (
    "facebook.com",
    "twitter.com",
    "x.com",
    "linkedin.com",
    "instagram.com",
    "youtube.com",
    "tiktok.com",
    "pinterest.com",
)


def _compact_nav_label(value: str) -> str:
    return re.sub(r"\s+", " ", (value or "").strip().lower())


def _score_nav_label_match(target: str, candidate: str) -> int:
    """Score how well a link/menu label matches the user's navigation target."""
    from app.runners.discovery_prompt import normalize_nav_target

    t = _compact_nav_label(normalize_nav_target(target))
    c = _compact_nav_label(candidate)
    if not t or not c:
        return 0
    if t == c:
        return 100
    t_compact = t.replace(" ", "")
    c_compact = c.replace(" ", "")
    if t_compact == c_compact:
        return 98
    if t in c or c in t:
        shorter = min(len(t), len(c))
        if shorter >= 4:
            return 72 + min(shorter, 20)
        return 0
    t_words = set(t.split())
    c_words = set(c.split())
    overlap = t_words & c_words
    if overlap and len(overlap) >= min(len(t_words), max(1, len(t_words) - 1)):
        return 58 + 12 * len(overlap)
    return 0


def _is_contact_form_url(url: str) -> bool:
    try:
        path = urlparse(url).path.lower()
    except Exception:
        return False
    return any(k in path for k in ("contact", "enquiry", "inquiry", "get-in-touch", "reach-us"))


def _case_looks_valid(case: dict, origin: str) -> bool:
    title = (case.get("title") or "").lower()
    if any(h in title for h in ("facebook", "twitter", "linkedin", "login to")):
        return False
    for step in case.get("steps") or []:
        url = step.get("url") or ""
        if url and not _is_allowed_nav_url(url, origin):
            return False
        desc = (step.get("description") or "").lower()
        if "base url" in desc and "http" in desc:
            return False
    return True


def _host_blocked(url: str) -> bool:
    try:
        host = urlparse(url).netloc.lower()
    except Exception:
        return False
    return any(host == h or host.endswith(f".{h}") for h in _BLOCKED_EXTERNAL_HOSTS)


def _is_allowed_nav_url(url: str, origin: str) -> bool:
    if not url or url.startswith("javascript:") or url == "#":
        return False
    if _host_blocked(url):
        return False
    return _same_origin(origin, url)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_id(prefix: str = "ptc") -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


def _discovery_cancelled(session_id: uuid.UUID | None) -> bool:
    if not session_id:
        return False
    from app.services.discovery_worker import is_discovery_cancel_requested

    return is_discovery_cancel_requested(session_id)


async def navigate_as_qa_user(
    base_url: str,
    username: str | None = None,
    password: str | None = None,
    max_pages: int | None = None,
    max_steps: int | None = None,
    requirements: str | None = None,
    on_event=None,
    session_id: uuid.UUID | None = None,
) -> dict:
    """
    Playwright-based QA exploration: navigate, interact, record steps, propose test cases.
    on_event(event_dict) called after each navigation action for live UI updates.
    """
    import asyncio
    import sys

    from app.runners.event_loop import run_isolated_async

    use_isolated = sys.platform == "win32"

    async def _run(on_event_cb) -> dict:
        from app.runners.setup_status import configure_playwright_browsers_env, _playwright_browsers_on_disk

        pw_ok, pw_hint = _playwright_browsers_on_disk()
        if not pw_ok:
            return await _fallback_http_agent(
                *_agent_urls(base_url),
                max_pages or settings.discovery_max_pages,
                on_event_cb,
                reason=pw_hint,
                requirements=requirements,
            )

        configure_playwright_browsers_env()

        try:
            from playwright.async_api import async_playwright  # noqa: F401
        except ImportError as exc:
            return await _fallback_http_agent(
                *_agent_urls(base_url),
                max_pages or settings.discovery_max_pages,
                on_event_cb,
                reason=str(exc) or "playwright package not installed",
                requirements=requirements,
            )

        try:
            return await _navigate_with_playwright(
                base_url,
                username,
                password,
                max_pages,
                max_steps,
                requirements,
                on_event_cb,
                session_id,
            )
        except NotImplementedError:
            logger.warning("playwright_subprocess_unsupported", platform=sys.platform)
            return await _fallback_http_agent(
                *_agent_urls(base_url),
                max_pages or settings.discovery_max_pages,
                on_event_cb,
                reason="Playwright subprocess not supported on this platform",
                requirements=requirements,
            )
        except Exception as e:
            err = str(e) or type(e).__name__
            logger.warning("playwright_agent_failed", error=err)
            from app.runners.setup_status import _playwright_browsers_on_disk

            _, hint = _playwright_browsers_on_disk()
            reason = hint or err[:300]
            return await _fallback_http_agent(
                *_agent_urls(base_url),
                max_pages or settings.discovery_max_pages,
                on_event_cb,
                reason=reason,
                requirements=requirements,
            )

    if use_isolated:
        import queue

        event_queue: queue.Queue = queue.Queue()
        done = asyncio.Event()
        result_box: dict = {}

        async def collect(event: dict) -> None:
            event_queue.put(event)

        async def factory() -> dict:
            return await _run(collect)

        async def pump_events() -> None:
            while not done.is_set() or not event_queue.empty():
                pumped = False
                while True:
                    try:
                        ev = event_queue.get_nowait()
                    except queue.Empty:
                        break
                    pumped = True
                    if on_event:
                        cb = on_event(ev)
                        if cb is not None and hasattr(cb, "__await__"):
                            await cb
                if done.is_set() and not pumped:
                    break
                await asyncio.sleep(0.2)

        async def run_agent() -> None:
            result_box["result"] = await run_isolated_async(factory)
            done.set()

        await asyncio.gather(pump_events(), run_agent())
        return result_box["result"]

    return await _run(on_event)


def _agent_urls(base_url: str) -> tuple[str, str]:
    parsed = urlparse(base_url if "://" in base_url else f"https://{base_url}")
    origin = f"{parsed.scheme}://{parsed.netloc}"
    start_url = base_url if "://" in base_url else origin
    return start_url, origin


def _keywords_from_requirements(requirements: str | None, explicit_targets: list[str] | None = None) -> list[str]:
    words: list[str] = []
    if requirements:
        words.extend(re.findall(r"[a-zA-Z]{3,}", requirements.lower()))
    for target in explicit_targets or []:
        words.extend(re.findall(r"[a-zA-Z]{3,}", target.lower()))
    stop = {"the", "and", "for", "want", "user", "that", "with", "from", "this", "have", "can", "then", "only", "just"}
    return [w for w in words if w not in stop]


def _score_nav_text(text: str, keywords: list[str], explicit_targets: list[str] | None = None) -> int:
    lower = text.lower()
    score = sum(2 for kw in keywords if kw in lower)
    for target in explicit_targets or []:
        t = target.lower()
        if t in lower or lower in t:
            score += 8
        elif any(part in lower for part in t.split() if len(part) > 2):
            score += 4
    return score


MENU_SELECTORS = (
    ".oxd-main-menu-item, [role=menuitem], nav a, .sidebar a, "
    ".menu-item, .nav-item, .sidebar-item, [class*='menu-item']"
)


async def _wait_for_spa(page, timeout_ms: int = 6000) -> None:
    try:
        await page.wait_for_load_state("domcontentloaded", timeout=timeout_ms)
    except Exception:
        pass
    try:
        await page.wait_for_load_state("networkidle", timeout=min(timeout_ms, 4000))
    except Exception:
        pass
    try:
        await page.wait_for_selector(
            "a[href], .oxd-main-menu-item, [role=menuitem], nav, main, [role=main]",
            timeout=3000,
        )
    except Exception:
        await page.wait_for_timeout(800)


async def _collect_menu_items(page) -> list[dict]:
    raw = await page.eval_on_selector_all(
        MENU_SELECTORS,
        """els => {
            const seen = new Set();
            const out = [];
            for (const e of els) {
                const text = (e.innerText || e.textContent || '').trim().replace(/\\s+/g, ' ');
                if (!text || text.length < 2 || seen.has(text)) continue;
                seen.add(text);
                const href = e.href || e.getAttribute('href') || null;
                out.push({ text, tag: e.tagName.toLowerCase(), href });
            }
            return out;
        }""",
    )
    return raw or []


async def _safe_click(page, locator, *, timeout_ms: int | None = None) -> bool:
    """Try several click strategies — never raise on timeout."""
    timeout_ms = timeout_ms or min(settings.playwright_timeout_ms, 15000)
    try:
        first = locator.first
        count = await locator.count()
        if not count:
            return False
        try:
            await first.scroll_into_view_if_needed(timeout=timeout_ms)
        except Exception:
            pass
        for attempt in (
            lambda: first.click(timeout=timeout_ms),
            lambda: first.click(timeout=timeout_ms, force=True),
            lambda: first.evaluate("el => el.click()"),
        ):
            try:
                await attempt()
                return True
            except Exception:
                continue
    except Exception:
        pass
    return False


async def _menu_item_href(page, text: str) -> str | None:
    """Resolve href for a menu label when the item is (or wraps) an anchor."""
    try:
        href = await page.evaluate(
            """(label) => {
                const norm = (s) => (s || '').trim().replace(/\\s+/g, ' ');
                const selectors = ['nav a', '.sidebar a', 'header a', 'a[href]'];
                for (const sel of selectors) {
                    for (const el of document.querySelectorAll(sel)) {
                        const t = norm(el.innerText || el.textContent);
                        if (t === norm(label) || t.includes(norm(label)) || norm(label).includes(t)) {
                            const href = el.getAttribute('href') || el.href;
                            if (href && href !== '#' && !href.startsWith('javascript:')) return href;
                        }
                    }
                }
                return null;
            }""",
            text,
        )
        return href or None
    except Exception:
        return None


async def _collect_nav_link_candidates(page, origin: str) -> list[dict]:
    raw = await page.eval_on_selector_all(
        "nav a, header a, .menu a, .navbar a, .nav a, [role=navigation] a, a[href]",
        """els => els.map(e => ({
            href: e.href,
            text: (e.innerText || e.textContent || e.getAttribute('aria-label') || '').trim().slice(0, 80)
        })).filter(x => x.href && x.text)""",
    )
    out: list[dict] = []
    seen: set[str] = set()
    for item in raw:
        href = item.get("href", "")
        if not _is_allowed_nav_url(href, origin):
            continue
        text = (item.get("text") or "").strip()
        if not text or text in seen or SKIP_TEXT.search(text):
            continue
        seen.add(text)
        out.append({"href": href, "text": text})
    return out


async def _click_menu_item(
    page, text: str, *, origin: str | None = None, min_score: int = 58, click_only: bool = False,
) -> bool:
    from app.runners.discovery_prompt import normalize_nav_target

    if SKIP_TEXT.search(text):
        return False

    target = normalize_nav_target(text)
    if not target:
        return False
    origin = origin or f"{urlparse(page.url).scheme}://{urlparse(page.url).netloc}"

    best_score = 0
    best: dict | None = None
    for item in await _collect_nav_link_candidates(page, origin):
        score = _score_nav_label_match(target, item["text"])
        if "contact" in target.lower() and re.search(r"contact", item.get("href", ""), re.I):
            score += 20
        if score > best_score:
            best_score = score
            best = item

    if best and best_score >= min_score:
        loc = page.get_by_role("link", name=best["text"], exact=True)
        if not await loc.count():
            loc = page.get_by_role("link", name=best["text"], exact=False)
        if await loc.count() and await _safe_click(page, loc.first):
            await _wait_for_spa(page)
            if _is_allowed_nav_url(page.url, origin):
                return True
        if not click_only:
            try:
                await page.goto(best["href"], timeout=settings.playwright_timeout_ms, wait_until="domcontentloaded")
                await _wait_for_spa(page)
                if _is_allowed_nav_url(page.url, origin):
                    return True
            except Exception:
                pass
            loc = page.get_by_role("link", name=best["text"], exact=True)
            if await loc.count() and await _safe_click(page, loc):
                await _wait_for_spa(page)
                return _is_allowed_nav_url(page.url, origin)

    for selector in [".oxd-main-menu-item", "[role=menuitem]", "nav a", ".sidebar a", "header nav a"]:
        loc = page.locator(selector).filter(has_text=re.compile(rf"^{re.escape(target)}$", re.I))
        if await loc.count():
            if await _safe_click(page, loc):
                await _wait_for_spa(page)
                return _is_allowed_nav_url(page.url, origin)
            break

    loc = page.get_by_role("link", name=target, exact=True)
    if await loc.count():
        if await _safe_click(page, loc):
            await _wait_for_spa(page)
            return _is_allowed_nav_url(page.url, origin)

    needles: list[str] = [target]
    if "," in target:
        needles.append(target.split(",")[0].strip())
    words = target.split()
    if words:
        needles.append(words[0])
    seen_needles: set[str] = set()
    for needle in needles:
        key = needle.lower().strip()
        if len(key) < 3 or key in seen_needles:
            continue
        seen_needles.add(key)
        pattern = re.compile(re.escape(needle), re.I)
        for selector in ("nav a", "header a", "[role=navigation] a", "footer a", "a[href]"):
            loc = page.locator(selector).filter(has_text=pattern)
            count = await loc.count()
            for i in range(min(count, 10)):
                item = loc.nth(i)
                try:
                    if not await item.is_visible():
                        continue
                    href = await item.get_attribute("href") or ""
                    if href and not _is_allowed_nav_url(href, origin):
                        continue
                    text_val = (await item.inner_text() or "").strip()
                    if SKIP_TEXT.search(text_val):
                        continue
                    if await _safe_click(page, item):
                        await _wait_for_spa(page)
                        if _is_allowed_nav_url(page.url, origin):
                            return True
                except Exception:
                    continue

    return False


async def _collect_nav_targets(
    page,
    origin: str,
    requirements: str | None,
    *,
    strict_follow: bool = False,
    explicit_targets: list[str] | None = None,
) -> list[dict]:
    keywords = _keywords_from_requirements(requirements, explicit_targets)
    targets: list[dict] = []

    for link in await _collect_actionable_links(page, origin):
        text = link["text"]
        score = _score_nav_text(text, keywords, explicit_targets)
        targets.append({"kind": "url", "text": text, "href": link["href"], "score": score})

    for item in await _collect_menu_items(page):
        text = item.get("text", "")
        if not text or SKIP_TEXT.search(text):
            continue
        href = item.get("href")
        score = _score_nav_text(text, keywords, explicit_targets) + 1
        if href:
            abs_href = href if "://" in str(href) else urljoin(page.url, str(href))
            if _same_origin(origin, abs_href):
                targets.append({"kind": "url", "text": text, "href": abs_href, "score": score})
                continue
        targets.append({"kind": "menu", "text": text, "href": href, "score": score})

    targets.sort(key=lambda t: t.get("score", 0), reverse=True)
    if strict_follow:
        targets = [t for t in targets if t.get("score", 0) > 0]
    seen: set[str] = set()
    unique: list[dict] = []
    for t in targets:
        key = t.get("href") or t["text"]
        if key in seen:
            continue
        seen.add(key)
        unique.append(t)
    return unique


async def _navigate_with_playwright(
    base_url: str,
    username: str | None,
    password: str | None,
    max_pages: int | None,
    max_steps: int | None,
    requirements: str | None,
    on_event,
    session_id: uuid.UUID | None = None,
) -> dict:
    from playwright.async_api import async_playwright
    from app.runners.discovery_prompt import resolve_discovery_auth

    login_user, login_pass, intent = resolve_discovery_auth(requirements, username, password)
    nav_requirements = intent.goals or requirements
    strict_follow = intent.strict_follow and not intent.broad_exploration
    explicit_targets = intent.explicit_targets

    max_pages = max_pages or settings.discovery_max_pages
    max_steps = max_steps or settings.discovery_max_steps
    if strict_follow:
        target_cap = max(len(explicit_targets), 1) + (1 if login_user else 0)
        max_pages = min(max_pages, max(target_cap + 1, 3))
        step_budget = max(len(explicit_targets) * 6 + 10, 15)
        if intent.menu_list_navigation:
            step_budget = max(len(explicit_targets) * 8 + 15, step_budget)
            max_pages = min(max_pages, max(len(explicit_targets) + 2, 5))
        max_steps = min(max_steps, step_budget)
    start_url, origin = _agent_urls(base_url)

    navigation_log: list[dict] = []
    journeys: list[dict] = []
    step_count = 0

    async def emit(event: dict) -> None:
        event["timestamp"] = _now()
        navigation_log.append(event)
        if on_event:
            result = on_event(event)
            if hasattr(result, "__await__"):
                await result

    proposed_cases: list[dict] = []
    visited_urls: set[str] = set()
    visited_menus: set[str] = set()
    queued_keys: set[str] = set()
    cancelled = False

    async with async_playwright() as p:
        await emit({"type": "status", "message": "Launching Chromium browser…"})
        browser = await p.chromium.launch(headless=settings.playwright_headless)
        context = await browser.new_context(ignore_https_errors=True, viewport={"width": 1280, "height": 720})
        page = await context.new_page()

        mode_label = "following your instructions only" if strict_follow else "broad exploration as requested"
        await emit({"type": "agent_start", "message": f"QA Agent starting — {mode_label} ({start_url})"})
        await emit({
            "type": "status",
            "message": f"Prompt understood — {intent.summary}",
        })
        if strict_follow:
            await emit({
                "type": "status",
                "message": "Strict mode — only actions that match your prompt. Add 'explore all modules' for wider discovery.",
            })
        if strict_follow and not nav_requirements and not explicit_targets and not intent.form_fields:
            await emit({
                "type": "warning",
                "message": "Discovery prompt has no actions after login — add what to open, verify, or submit (e.g. enquiry form with field values).",
            })
        if intent.should_login and not (login_user and login_pass):
            await emit({
                "type": "warning",
                "message": "Login mentioned in prompt but credentials not found. Add e.g. 'login as admin/admin123' in your prompt, or say 'no login' for public sites.",
            })

        logged_in = False
        if login_user and login_pass:
            await page.goto(start_url, timeout=settings.playwright_timeout_ms, wait_until="load")
            await page.wait_for_timeout(1500)
            logged_in = await _attempt_login(page, login_user, login_pass, emit)
            if logged_in:
                journeys.append(_build_journey_from_log(navigation_log, "Login Journey", "high"))
                await _wait_for_spa(page)
                step_count += 1
        else:
            await page.goto(start_url, timeout=settings.playwright_timeout_ms, wait_until="domcontentloaded")
            await _wait_for_spa(page)

        form_completed = False
        instruction_mode = (strict_follow and not intent.broad_exploration) or intent.menu_list_navigation

        if instruction_mode:
            from app.runners.discovery_prompt import has_actionable_instructions, navigation_targets

            await emit({
                "type": "status",
                "message": "Instruction mode — executing your prompt only (no menu crawl)",
            })
            form_completed = await _run_instruction_plan(
                page, intent, origin, emit, proposed_cases, logged_in,
                start_url=start_url, navigation_log=navigation_log,
            )
            step_count += max(len(intent.form_fields), 1)
        else:
            if intent.wants_form_submit or intent.form_fields:
                form_completed = await _execute_form_workflow(
                    page, intent, origin, emit, proposed_cases,
                    start_url=start_url, navigation_log=navigation_log,
                )
                if form_completed:
                    step_count += max(len(intent.form_fields), 1) + 2

            queue: list[dict] = []

            async def explore_current_page(source: str) -> None:
                nonlocal step_count
                title = await page.title()
                page_info = await _analyze_page(page)
                await emit({
                    "type": "observe",
                    "message": f"Found {page_info['links']} links, {page_info['menus']} menu items, {page_info['forms']} forms, {page_info['buttons']} buttons",
                    "url": page.url,
                    "elements": page_info,
                })
                if not strict_follow:
                    proposed_cases.append(_page_smoke_test(page.url, title, page_info))
                    if page_info["forms"] > 0:
                        form_case = await _probe_form(page, title, emit)
                        if form_case:
                            proposed_cases.append(form_case)
                            step_count += len(form_case.get("steps", []))
                targets = await _collect_nav_targets(
                    page,
                    origin,
                    nav_requirements,
                    strict_follow=strict_follow,
                    explicit_targets=explicit_targets,
                )
                if strict_follow and not targets and nav_requirements:
                    await emit({
                        "type": "warning",
                        "message": (
                            "No menus or links matched your instructions on this page. "
                            "Use exact module/page names from the app, or add 'explore all modules' for broader discovery."
                        ),
                        "url": page.url,
                    })
                for target in targets:
                    key = target.get("href") or f"menu:{target['text']}"
                    if key in queued_keys:
                        continue
                    if target["kind"] == "menu" and target["text"] in visited_menus:
                        continue
                    if target["kind"] == "url" and _normalize_url(target["href"]) in visited_urls:
                        continue
                    queued_keys.add(key)
                    queue.append(target)
                if source == "login":
                    await emit({
                        "type": "navigate",
                        "message": f"Logged in — dashboard: {title or page.url}",
                        "url": page.url,
                        "title": title,
                    })

            norm_current = _normalize_url(page.url)
            visited_urls.add(norm_current)
            await explore_current_page("login" if logged_in else "start")

            if form_completed and strict_follow and not intent.broad_exploration:
                queue.clear()

            if _discovery_cancelled(session_id):
                cancelled = True
            else:
                while queue and (len(visited_urls) + len(visited_menus)) < max_pages and step_count < max_steps:
                    if _discovery_cancelled(session_id):
                        cancelled = True
                        break
                    target = queue.pop(0)
                    prev_url = page.url

                    try:
                        if target["kind"] == "menu":
                            menu_text = target["text"]
                            if menu_text in visited_menus:
                                continue
                            visited_menus.add(menu_text)
                            await emit({
                                "type": "click",
                                "message": f"Open module \"{menu_text}\"",
                                "url": page.url,
                                "element": menu_text,
                            })
                            opened = await _click_menu_item(page, menu_text)
                            if not opened:
                                href = target.get("href")
                                if href:
                                    try:
                                        dest = href if "://" in str(href) else urljoin(page.url, str(href))
                                        await page.goto(dest, timeout=settings.playwright_timeout_ms, wait_until="domcontentloaded")
                                        opened = True
                                    except Exception as nav_err:
                                        await emit({
                                            "type": "warning",
                                            "message": f"Skipped \"{menu_text}\" — click and navigate failed: {str(nav_err)[:120]}",
                                            "url": page.url,
                                        })
                                        continue
                                else:
                                    await emit({
                                        "type": "warning",
                                        "message": f"Skipped menu \"{menu_text}\" — not clickable (continuing exploration)",
                                        "url": page.url,
                                    })
                                    continue
                            await _wait_for_spa(page)
                            step_count += 1
                            mod_title = await page.title()
                            if not (intent.menu_list_navigation and not intent.split_test_cases):
                                proposed_cases.append(_menu_module_test(menu_text, page.url, mod_title))
                            await emit({
                                "type": "navigate",
                                "message": f"Module opened: {menu_text} — {mod_title}",
                                "url": page.url,
                                "title": mod_title,
                            })
                        else:
                            href = target["href"]
                            norm = _normalize_url(href)
                            if norm in visited_urls:
                                continue
                            visited_urls.add(norm)
                            await emit({
                                "type": "inspect",
                                "message": f"Follow link \"{target['text']}\" → {href}",
                                "url": page.url,
                                "target": href,
                                "element": target["text"],
                            })
                            try:
                                resp = await page.goto(href, timeout=settings.playwright_timeout_ms, wait_until="domcontentloaded")
                                await _wait_for_spa(page)
                                title = await page.title()
                                status = resp.status if resp else 0
                                await emit({
                                    "type": "navigate",
                                    "message": f"Navigated to: {title or href}",
                                    "url": page.url,
                                    "title": title,
                                    "status": status,
                                })
                                proposed_cases.append(_link_navigation_test(prev_url, await page.title(), target))
                                step_count += 1
                            except Exception as e:
                                await emit({"type": "warning", "message": f"Navigation skipped: {str(e)[:200]}", "url": href})
                                continue

                        norm = _normalize_url(page.url)
                        if norm not in visited_urls:
                            visited_urls.add(norm)

                        await explore_current_page("explore")

                        if not strict_follow:
                            for btn in (await _collect_buttons(page))[:1]:
                                if step_count >= max_steps:
                                    break
                                if SKIP_TEXT.search(btn["text"] or ""):
                                    continue
                                try:
                                    await emit({
                                        "type": "click",
                                        "message": f"Click \"{btn['text']}\"",
                                        "url": page.url,
                                        "element": btn["text"],
                                    })
                                    btn_loc = page.locator(btn["selector"])
                                    if not await _safe_click(page, btn_loc):
                                        continue
                                    await _wait_for_spa(page)
                                    new_title = await page.title()
                                    await emit({
                                        "type": "verify",
                                        "message": f"After click, page: {new_title}",
                                        "url": page.url,
                                        "title": new_title,
                                    })
                                    proposed_cases.append(_button_click_test(page.url, btn, new_title))
                                    step_count += 2
                                    if _same_origin(origin, page.url) and _normalize_url(page.url) not in visited_urls:
                                        visited_urls.add(_normalize_url(page.url))
                                        await explore_current_page("button")
                                    await page.go_back(timeout=8000)
                                    await _wait_for_spa(page)
                                except Exception as e:
                                    await emit({"type": "warning", "message": f"Click skipped: {str(e)[:120]}", "url": page.url})
                    except Exception as step_err:
                        await emit({
                            "type": "warning",
                            "message": f"Step skipped — agent continuing: {str(step_err)[:180]}",
                            "url": page.url,
                        })
                        continue

        if cancelled:
            await emit({"type": "status", "message": "Discovery stopped by user"})

        await browser.close()

    if cancelled:
        await emit({
            "type": "agent_complete",
            "message": (
                f"Exploration stopped — {len(visited_urls)} pages, "
                f"{len(visited_menus)} modules, {len(proposed_cases)} test cases captured so far"
            ),
        })
    else:
        await emit({
            "type": "agent_complete",
            "message": (
                f"Exploration complete — {len(visited_urls)} pages, "
                f"{len(visited_menus)} modules, {len(proposed_cases)} test cases proposed"
            ),
        })

    # Deduplicate proposed cases by title
    proposed_cases = _consolidate_menu_list_cases(proposed_cases, start_url, intent)
    seen_titles: set[str] = set()
    unique_cases: list[dict] = []
    for case in proposed_cases:
        t = case["title"]
        if t not in seen_titles:
            seen_titles.add(t)
            unique_cases.append(case)

    # Journey-level test from log — never for form-submit prompts (structured case is built separately)
    has_form_flow = any(c.get("flow_kind") == "form_submit" for c in unique_cases)
    form_intent = bool(intent.form_fields) or intent.wants_form_submit
    unique_cases = [c for c in unique_cases if _case_looks_valid(c, origin)]
    has_menu_cases = any(
        (c.get("title") or "").startswith("Module flow —")
        or c.get("flow_kind") == "menu_journey"
        for c in unique_cases
    )
    if (
        len(navigation_log) > 3
        and strict_follow
        and not has_form_flow
        and not form_intent
        and not has_menu_cases
        and not intent.menu_list_navigation
    ):
        unique_cases.insert(0, _instruction_session_test(start_url, navigation_log, intent.goals or nav_requirements))
    elif len(navigation_log) > 3 and not strict_follow:
        unique_cases.insert(0, _full_session_test(start_url, navigation_log))

    return {
        "mode": "qa_agent",
        "cancelled": cancelled,
        "pages_crawled": len(visited_urls),
        "modules_explored": len(visited_menus),
        "navigation_log": navigation_log,
        "proposed_test_cases": unique_cases,
        "screens": _screens_from_log(navigation_log),
        "flow_map": _flows_from_cases(unique_cases, start_url),
        "apis": _apis_from_log(navigation_log),
    }


def _consolidate_menu_list_cases(cases: list[dict], start_url: str, intent) -> list[dict]:
    """Merge per-menu Module flow cases into one journey when user listed menus in the prompt."""
    if not intent.menu_list_navigation or intent.split_test_cases:
        return cases

    module_cases = [c for c in cases if (c.get("title") or "").startswith("Module flow —")]
    journey_cases = [c for c in cases if c.get("flow_kind") == "menu_journey"]

    if journey_cases and module_cases:
        return [c for c in cases if not (c.get("title") or "").startswith("Module flow —")]

    if len(module_cases) < 2:
        return cases

    navigated: list[tuple[str, str, str]] = []
    seen: set[str] = set()
    for name in intent.explicit_targets or []:
        key = name.lower()
        if key in seen:
            continue
        match = next(
            (c for c in module_cases if c.get("module") == name or c.get("title") == f"Module flow — {name}"),
            None,
        )
        if match:
            seen.add(key)
            navigated.append((name, start_url, match.get("screen") or name))

    for case in module_cases:
        name = (case.get("title") or "").replace("Module flow — ", "").strip()
        if not name or name.lower() in seen:
            continue
        seen.add(name.lower())
        navigated.append((name, start_url, case.get("screen") or name))

    if not navigated:
        return cases

    others = [c for c in cases if not (c.get("title") or "").startswith("Module flow —")]
    return others + [
        _build_combined_navigation_test_case(
            start_url,
            navigated,
            journey_name="Main menu navigation journey",
        )
    ]


async def _attempt_login(page, username: str, password: str, emit) -> bool:
    await emit({"type": "action", "message": "Attempting login as QA user", "url": page.url})
    try:
        await page.wait_for_selector(
            "input[name=username], input[name=email], input[type=email], #txtUsername",
            timeout=15000,
        )
    except Exception:
        await emit({"type": "error", "message": "Login form not found on page", "url": page.url})
        return False
    filled_user = filled_pass = False
    for user_sel in ["input[name=username]", "input[name=email]", "input[type=email]", "#username", "#txtUsername"]:
        if await page.locator(user_sel).count():
            await page.fill(user_sel, username)
            filled_user = True
            await emit({"type": "fill", "message": f"Enter username in {user_sel}", "url": page.url, "field": "username"})
            break
    for pass_sel in ["input[name=password]", "input[type=password]", "#password", "#txtPassword"]:
        if await page.locator(pass_sel).count():
            await page.fill(pass_sel, password)
            filled_pass = True
            await emit({"type": "fill", "message": f"Enter password", "url": page.url, "field": "password"})
            break
    if not (filled_user and filled_pass):
        return False
    for btn in ["button[type=submit]", "input[type=submit]", "button:has-text('Login')", "button:has-text('Log in')", "button:has-text('Sign in')"]:
        if await page.locator(btn).count():
            await emit({"type": "click", "message": "Click login button", "url": page.url, "element": "Login"})
            await page.locator(btn).first.click()
            await page.wait_for_timeout(3500)
            try:
                await page.wait_for_selector(".oxd-main-menu-item, [role=main], main", timeout=8000)
            except Exception:
                pass
            await emit({"type": "verify", "message": f"Post-login URL: {page.url}", "url": page.url, "title": await page.title()})
            return True
    return False


async def _analyze_page(page) -> dict:
    links = await page.locator("a[href]").count()
    menus = len(await _collect_menu_items(page))
    forms = await page.locator("form").count()
    buttons = await page.locator("button, input[type=submit], [role=button]").count()
    inputs = await page.locator("input, textarea, select").count()
    return {"links": links, "menus": menus, "forms": forms, "buttons": buttons, "inputs": inputs}


async def _collect_actionable_links(page, origin: str) -> list[dict]:
    raw = await page.eval_on_selector_all(
        "a[href]",
        """els => els.map(e => ({
            href: e.href,
            text: (e.innerText || e.textContent || '').trim().slice(0, 80)
        })).filter(x => x.href && x.text)""",
    )
    out = []
    seen = set()
    for item in raw:
        href = item.get("href", "")
        if not _same_origin(origin, href):
            continue
        text = item.get("text", "")
        if not text or text in seen:
            continue
        if SKIP_TEXT.search(text):
            continue
        seen.add(text)
        out.append({"href": href, "text": text})
    return out


async def _collect_buttons(page) -> list[dict]:
    raw = await page.eval_on_selector_all(
        "button, input[type=submit], input[type=button]",
        """els => els.slice(0, 8).map((e, i) => ({
            text: (e.innerText || e.value || e.getAttribute('aria-label') || 'Button').trim().slice(0, 60),
            idx: i
        })).filter(x => x.text)""",
    )
    return [{"text": r["text"], "selector": f"button, input[type=submit], input[type=button] >> nth={r['idx']}"} for r in raw]


_FORM_LINK_KEYWORDS = (
    "enquiry", "inquiry", "contact", "contact us", "get in touch", "feedback", "request", "support",
)

_CONTACT_PAGE_PATHS = (
    "/contact-us.html",
    "/contact-us",
    "/contactus.html",
    "/contact.html",
    "/contactus",
    "/contact",
    "/enquiry.html",
    "/enquiry",
    "/get-in-touch",
    "/reach-us",
)

# Prompt label → common input name / id attributes (Vivilex uses name=comments for Message)
_FIELD_NAME_ALIASES: dict[str, list[str]] = {
    "your name": ["name", "fullname", "full_name", "your_name"],
    "name": ["name", "fullname", "full_name"],
    "e-mail": ["email", "e-mail", "mail"],
    "email": ["email", "e-mail", "mail"],
    "mobile number": ["mobile", "phone", "tel", "mobile_number"],
    "mobile": ["mobile", "phone", "tel"],
    "phone": ["phone", "mobile", "tel"],
    "organization name": ["organization", "company", "org", "organisation"],
    "organization": ["organization", "company", "org", "organisation"],
    "company": ["company", "organization", "org"],
    "message": ["comments", "message", "body", "enquiry", "inquiry", "description"],
}


def _field_name_candidates(label: str) -> list[str]:
    key = re.sub(r"\s*\*+\s*$", "", label.strip().lower())
    key = re.sub(r"\s+", " ", key)
    names: list[str] = []
    seen: set[str] = set()

    def add(name: str) -> None:
        n = name.strip().lower()
        if n and n not in seen:
            seen.add(n)
            names.append(n)

    for alias in _FIELD_NAME_ALIASES.get(key, []):
        add(alias)
    compact = key.replace(" ", "").replace("-", "")
    if compact:
        add(compact)
    for token in key.split():
        if len(token) >= 3:
            add(token)
    return names


async def _scroll_to_form(page) -> None:
    try:
        form = page.locator("form").first
        if await form.count():
            await form.scroll_into_view_if_needed(timeout=8000)
            return
        section = page.locator(".send_message, .contact-form, #contact, [class*='contact']").first
        if await section.count():
            await section.scroll_into_view_if_needed(timeout=8000)
    except Exception:
        pass


async def _discover_form_inputs(page) -> list[dict]:
    """List visible inputs/textareas with nearby label text."""
    try:
        return await page.evaluate(
            """() => {
                const skipTypes = new Set(['hidden', 'submit', 'button', 'reset', 'image']);
                const items = [];
                const visible = (el) => {
                    const s = window.getComputedStyle(el);
                    return s.display !== 'none' && s.visibility !== 'hidden' && el.offsetParent !== null;
                };
                const clean = (t) => (t || '').replace(/\\s*\\*+\\s*$/g, '').trim();
                const labelFor = (el) => {
                    if (el.id) {
                        const lb = document.querySelector('label[for="' + el.id + '"]');
                        if (lb) return clean(lb.innerText || lb.textContent);
                    }
                    let node = el.parentElement;
                    for (let i = 0; i < 6 && node; i++) {
                        const prev = node.previousElementSibling;
                        if (prev) {
                            const t = clean(prev.innerText || prev.textContent);
                            if (t) return t;
                        }
                        const lab = node.querySelector('p.label, .label, label, legend, .form-label');
                        if (lab) return clean(lab.innerText || lab.textContent);
                        node = node.parentElement;
                    }
                    return clean(el.getAttribute('aria-label') || el.placeholder || '');
                };
                for (const el of document.querySelectorAll('input, textarea, select')) {
                    const typ = (el.type || el.tagName).toLowerCase();
                    if (skipTypes.has(typ)) continue;
                    if (!visible(el)) continue;
                    items.push({
                        name: el.name || '',
                        id: el.id || '',
                        type: typ,
                        tag: el.tagName.toLowerCase(),
                        label: labelFor(el),
                        placeholder: el.placeholder || '',
                    });
                }
                return items;
            }"""
        )
    except Exception:
        return []


def _score_prompt_field_to_input(prompt_label: str, discovered: dict) -> int:
    key = re.sub(r"\s*\*+\s*$", "", prompt_label.strip().lower())
    label = re.sub(r"\s*\*+\s*$", "", (discovered.get("label") or "").lower()).strip()
    name = (discovered.get("name") or discovered.get("id") or "").lower()
    placeholder = (discovered.get("placeholder") or "").lower()

    for candidate in _field_name_candidates(prompt_label):
        if candidate == name or candidate == (discovered.get("id") or "").lower():
            return 100
        if candidate in name or name in candidate:
            return 92

    if key and label:
        if key == label or key in label or label in key:
            return 85
        key_compact = key.replace(" ", "").replace("-", "")
        label_compact = label.replace(" ", "").replace("-", "")
        if key_compact and key_compact in label_compact:
            return 78

    if key and placeholder and (key in placeholder or placeholder in key):
        return 70

    return 0


async def _click_then_fill(el, value: str) -> None:
    await el.click(timeout=5000)
    await el.fill(value, timeout=8000)


async def _type_value_into_locator(locator, value: str) -> bool:
    """Click, fill, and verify — with JS fallback for stubborn legacy forms."""
    try:
        el = locator.first
        if not await locator.count():
            return False
    except Exception:
        return False

    try:
        await el.scroll_into_view_if_needed(timeout=6000)
    except Exception:
        pass

    for fill_fn in (
        lambda: el.fill(value, timeout=8000),
        lambda: _click_then_fill(el, value),
        lambda: el.fill(value, force=True, timeout=8000),
    ):
        try:
            await fill_fn()
            current = await el.input_value()
            if current == value or (value and value[:8] in (current or "")):
                return True
        except Exception:
            continue

    try:
        ok = await el.evaluate(
            """(element, val) => {
                element.focus();
                element.scrollIntoView({ block: 'center' });
                element.value = val;
                element.dispatchEvent(new Event('input', { bubbles: true }));
                element.dispatchEvent(new Event('change', { bubbles: true }));
                return element.value === val || (val && element.value.includes(val.slice(0, 8)));
            }""",
            value,
        )
        return bool(ok)
    except Exception:
        return False


async def _fill_input_by_name(page, name: str, value: str) -> bool:
    if not name:
        return False
    for sel in (
        f"input[name='{name}']",
        f"textarea[name='{name}']",
        f"select[name='{name}']",
        f"#{name}",
    ):
        loc = page.locator(sel)
        if await loc.count():
            return await _type_value_into_locator(loc, value)
    return False


async def _page_ready_for_contact_form(page) -> bool:
    try:
        score = await page.evaluate(
            """() => {
                const fields = Array.from(document.querySelectorAll(
                    'input:not([type=hidden]):not([type=submit]):not([type=button]), textarea'
                )).filter(el => el.offsetParent !== null);
                if (fields.length < 2) return 0;
                const blob = fields.map(el =>
                    ((el.name || '') + ' ' + (el.id || '') + ' ' + (el.type || '')).toLowerCase()
                ).join(' ');
                let s = fields.length;
                if (/name|email|mail|mobile|phone|organization|comment|message/.test(blob)) s += 10;
                if (document.querySelector('textarea')) s += 5;
                if (document.querySelector('form')) s += 3;
                return s;
            }"""
        )
        return int(score or 0) >= 8
    except Exception:
        return False


async def _ensure_contact_form_page(
    page, origin: str, emit, explicit_targets: list[str] | None = None,
) -> bool:
    """Navigate until a real contact/enquiry form is visible."""
    if await _page_ready_for_contact_form(page):
        return True

    if await _navigate_to_form_page(page, origin, emit, explicit_targets):
        await _scroll_to_form(page)
        if await _page_ready_for_contact_form(page):
            return True

    if await _try_same_origin_contact_paths(page, origin, emit):
        await _scroll_to_form(page)
        if await _page_ready_for_contact_form(page) or await _page_has_fillable_form(page):
            return True

    return False


async def _fill_all_prompt_fields(page, form_fields: list, emit) -> tuple[int, list[str]]:
    """Fill every prompt field using name aliases, discovery, and label heuristics."""
    discovered = await _discover_form_inputs(page)
    await emit({
        "type": "observe",
        "message": f"Form scan — {len(discovered)} fillable field(s) on {urlparse(page.url).path or page.url}",
        "url": page.url,
        "elements": {"form_fields": len(discovered)},
    })

    filled_labels: set[str] = set()
    missing: list[str] = []

    for field in form_fields:
        label = field.label.strip()
        value = field.value.strip()
        if not label or not value:
            continue
        if label.lower() in filled_labels:
            continue

        done = False

        for name in _field_name_candidates(label):
            if await _fill_input_by_name(page, name, value):
                done = True
                break

        if not done and discovered:
            best_score = 0
            best_idx = -1
            for i, meta in enumerate(discovered):
                if meta.get("_used"):
                    continue
                score = _score_prompt_field_to_input(label, meta)
                if score > best_score:
                    best_score = score
                    best_idx = i
            if best_idx >= 0 and best_score >= 70:
                meta = discovered[best_idx]
                sel_parts = []
                if meta.get("name"):
                    sel_parts.append(f"[name='{meta['name']}']")
                if meta.get("id"):
                    sel_parts.append(f"#{meta['id']}")
                for sel in sel_parts:
                    tag = meta.get("tag") or "input"
                    loc = page.locator(f"{tag}{sel}")
                    if await loc.count() and await _type_value_into_locator(loc, value):
                        discovered[best_idx]["_used"] = True
                        done = True
                        break

        if not done:
            done = await _fill_by_paragraph_label(page, label, value)

        if not done:
            for sel in (
                f"input[name='{label.lower().replace(' ', '')}']",
                f"textarea[name='{label.lower().replace(' ', '')}']",
            ):
                loc = page.locator(sel)
                if await loc.count() and await _type_value_into_locator(loc, value):
                    done = True
                    break

        if done:
            filled_labels.add(label.lower())
            await emit({
                "type": "fill",
                "message": f"Filled '{label}' → {value[:60]}",
                "url": page.url,
                "field": label,
            })
        else:
            missing.append(label)

    if missing:
        extra = await _fill_remaining_fields_sequential(page, form_fields, filled_labels, emit)
        if extra:
            for field in form_fields:
                if field.label.lower() not in filled_labels:
                    for name in _field_name_candidates(field.label):
                        loc = page.locator(f"input[name='{name}'], textarea[name='{name}'], #{name}")
                        if await loc.count():
                            val = await loc.first.input_value()
                            if val and field.value[:6] in val:
                                filled_labels.add(field.label.lower())
                                break
        missing = [f.label for f in form_fields if f.label.lower() not in filled_labels]

    return len(filled_labels), missing


async def _try_same_origin_contact_paths(page, origin: str, emit) -> bool:
    """Common contact URL paths when menu matching fails."""
    base = origin.rstrip("/")
    paths = _CONTACT_PAGE_PATHS
    for path in paths:
        url = f"{base}{path}"
        try:
            await emit({
                "type": "navigate",
                "message": f"Trying contact page — {url}",
                "url": page.url,
                "target": url,
            })
            resp = await page.goto(url, timeout=settings.playwright_timeout_ms, wait_until="domcontentloaded")
            await _wait_for_spa(page)
            if not _is_allowed_nav_url(page.url, origin):
                continue
            status = resp.status if resp else 0
            if status == 404:
                continue
            if await _page_has_fillable_form(page):
                return True
            body = (await page.locator("body").inner_text())[:1500].lower()
            if any(k in body for k in ("contact", "enquiry", "message", "your name", "e-mail", "email")):
                return True
        except Exception:
            continue
    return False


async def _open_named_target(page, target: str, origin: str, emit, *, menu_list_mode: bool = False) -> bool:
    """Navigate to a page or module named in the user's prompt."""
    from app.runners.discovery_prompt import normalize_nav_target

    target_clean = normalize_nav_target(target.strip())
    if not target_clean:
        return False

    await emit({
        "type": "click",
        "message": f"Open \"{target_clean}\" as instructed",
        "url": page.url,
        "element": target_clean,
    })

    if await _click_menu_item(
        page, target_clean, origin=origin,
        min_score=50 if menu_list_mode else 58,
        click_only=menu_list_mode,
    ):
        title = await page.title()
        await emit({
            "type": "navigate",
            "message": f"Opened {target_clean} — {title or page.url}",
            "url": page.url,
            "title": title,
        })
        return True

    best_score = 0
    best: dict | None = None
    for link in await _collect_nav_link_candidates(page, origin):
        score = _score_nav_label_match(target_clean, link["text"])
        if "contact" in target_clean.lower() and re.search(r"contact", link.get("href", ""), re.I):
            score += 20
        if score > best_score:
            best_score = score
            best = link

    if best and best_score >= (50 if menu_list_mode else 58):
        if menu_list_mode:
            loc = page.get_by_role("link", name=best["text"], exact=False)
            if await loc.count() and await _safe_click(page, loc.first):
                await _wait_for_spa(page)
                if _is_allowed_nav_url(page.url, origin):
                    title = await page.title()
                    await emit({
                        "type": "navigate",
                        "message": f"Opened {target_clean} via menu click — {title or page.url}",
                        "url": page.url,
                        "title": title,
                    })
                    return True
        else:
            try:
                await emit({
                    "type": "navigate",
                    "message": f"Following link \"{best['text']}\" → {best['href']}",
                    "url": page.url,
                    "target": best["href"],
                    "element": best["text"],
                })
                await page.goto(best["href"], timeout=settings.playwright_timeout_ms, wait_until="domcontentloaded")
                await _wait_for_spa(page)
                if _is_allowed_nav_url(page.url, origin):
                    title = await page.title()
                    await emit({
                        "type": "navigate",
                        "message": f"Opened {target_clean} — {title or page.url}",
                        "url": page.url,
                        "title": title,
                    })
                    return True
                await emit({
                    "type": "warning",
                    "message": f"Skipped \"{best['text']}\" — left the application (external site)",
                    "url": page.url,
                })
            except Exception as exc:
                await emit({
                    "type": "warning",
                    "message": f"Could not follow link \"{best['text']}\": {str(exc)[:120]}",
                    "url": best["href"],
                })

    contact_related = bool(re.search(r"\bcontact|enquiry|inquiry|get\s+in\s+touch\b", target_clean, re.I))
    if contact_related and await _try_same_origin_contact_paths(page, origin, emit):
        title = await page.title()
        await emit({
            "type": "navigate",
            "message": f"Opened contact page — {title or page.url}",
            "url": page.url,
            "title": title,
        })
        return True

    await emit({
        "type": "warning",
        "message": (
            f"Could not find \"{target_clean}\" on this site — "
            "check the menu label or put the contact page URL in Base URL"
        ),
        "url": page.url,
    })
    return False


async def _run_instruction_plan(
    page,
    intent,
    origin: str,
    emit,
    proposed_cases: list[dict],
    logged_in: bool,
    *,
    start_url: str = "",
    navigation_log: list[dict] | None = None,
) -> bool:
    """Execute prompt instructions only — no menu crawl."""
    from app.runners.discovery_prompt import has_actionable_instructions, navigation_targets

    if not has_actionable_instructions(intent):
        await emit({
            "type": "warning",
            "message": "No actionable instructions in prompt — add what to open, verify, or submit.",
            "url": page.url,
        })
        return False

    completed = False
    nav_targets = navigation_targets(intent)
    if (intent.wants_form_submit or intent.form_fields) and not intent.menu_list_navigation:
        if _is_contact_form_url(start_url) or _is_contact_form_url(page.url) or await _page_ready_for_contact_form(page):
            nav_targets = []

    navigated: list[tuple[str, str, str]] = []
    home_url = start_url or page.url
    for target in nav_targets:
        if home_url and page.url.split("#")[0].rstrip("/") != home_url.split("#")[0].rstrip("/"):
            try:
                await page.goto(home_url, timeout=settings.playwright_timeout_ms, wait_until="domcontentloaded")
                await _wait_for_spa(page)
            except Exception:
                pass
        if not await _open_named_target(
            page, target, origin, emit, menu_list_mode=intent.menu_list_navigation,
        ):
            await emit({
                "type": "warning",
                "message": f"Skipped navigation to \"{target}\" — continuing with remaining menus",
                "url": page.url,
            })
            continue
        if not _is_allowed_nav_url(page.url, origin):
            await emit({
                "type": "error",
                "message": f"Left application site while opening \"{target}\" — stopping navigation",
                "url": page.url,
            })
            break
        title = await page.title()
        navigated.append((target, page.url, title or target))

    if intent.wants_form_submit or intent.form_fields:
        completed = await _execute_form_workflow(
            page, intent, origin, emit, proposed_cases,
            start_url=start_url, navigation_log=navigation_log or [],
        )
    elif navigated:
        home = start_url or home_url
        if intent.split_test_cases:
            for target, _url, title in navigated:
                proposed_cases.append(
                    _menu_module_test(target, home, title, logged_in=logged_in, home_url=home)
                )
        else:
            proposed_cases.append(
                _build_combined_navigation_test_case(
                    home,
                    navigated,
                    journey_name="Main menu navigation journey",
                    logged_in=logged_in,
                )
            )
        await emit({
            "type": "verify",
            "message": f"Completed navigation to: {', '.join(t for t, _, _ in navigated)}",
            "url": page.url,
            "title": navigated[-1][2],
        })
        completed = True
    elif logged_in and intent.should_login:
        await emit({
            "type": "verify",
            "message": "Login completed as instructed",
            "url": page.url,
        })
        completed = True

    return completed


async def _fill_remaining_fields_sequential(page, fields: list, filled_labels: set[str], emit) -> int:
    """Fill unmatched fields by visible input order (text → email → tel → textarea)."""
    selectors = [
        "input[type=text]:visible",
        "input:not([type]):visible",
        "input[type=email]:visible",
        "input[type=tel]:visible",
        "textarea:visible",
    ]
    locators = []
    for sel in selectors:
        loc = page.locator(sel)
        count = await loc.count()
        for i in range(count):
            locators.append(loc.nth(i))

    extra = 0
    idx = 0
    for field in fields:
        if field.label.lower() in filled_labels:
            continue
        while idx < len(locators):
            el = locators[idx]
            idx += 1
            try:
                if not await el.is_visible():
                    continue
                if await el.input_value():
                    continue
                tag = (await el.evaluate("e => e.tagName.toLowerCase()")) or "input"
                input_type = (await el.get_attribute("type") or "").lower()
                if tag == "select":
                    try:
                        await el.select_option(label=field.value)
                    except Exception:
                        await el.select_option(value=field.value)
                elif input_type in ("checkbox", "radio"):
                    await el.check()
                else:
                    if not await _type_value_into_locator(el, field.value):
                        continue
                await emit({
                    "type": "fill",
                    "message": f"Filled '{field.label}' → {field.value[:60]} (by field order)",
                    "url": page.url,
                    "field": field.label,
                })
                filled_labels.add(field.label.lower())
                extra += 1
                break
            except Exception:
                continue
    return extra


async def _page_has_fillable_form(page) -> bool:
    forms = await page.locator("form").count()
    fields = await page.locator(
        "input:not([type=hidden]):not([type=submit]):not([type=button]), textarea, select"
    ).count()
    return forms > 0 or fields >= 2


async def _navigate_to_form_page(page, origin: str, emit, explicit_targets: list[str] | None = None) -> bool:
    if not _is_allowed_nav_url(page.url, origin):
        await emit({
            "type": "error",
            "message": "Not on the application site — cannot fill the contact form on an external page",
            "url": page.url,
        })
        return False
    if await _page_has_fillable_form(page):
        return True

    from app.runners.discovery_prompt import normalize_nav_target

    keywords = list(_FORM_LINK_KEYWORDS)
    for target in explicit_targets or []:
        cleaned = normalize_nav_target(target).lower()
        if cleaned and cleaned not in keywords:
            keywords.append(cleaned)

    best_score = 0
    best: dict | None = None
    for link in await _collect_nav_link_candidates(page, origin):
        text = link["text"].lower()
        score = max(
            (_score_nav_label_match(k, link["text"]) for k in keywords),
            default=0,
        )
        if any(k in text for k in keywords):
            score = max(score, 65)
        if score > best_score:
            best_score = score
            best = link

    if best and best_score >= 58:
        try:
            await emit({
                "type": "navigate",
                "message": f"Opening form page — \"{best['text']}\"",
                "url": page.url,
                "target": best["href"],
            })
            await page.goto(best["href"], timeout=settings.playwright_timeout_ms, wait_until="domcontentloaded")
            await _wait_for_spa(page)
            if _is_allowed_nav_url(page.url, origin) and await _page_has_fillable_form(page):
                return True
        except Exception as exc:
            await emit({"type": "warning", "message": f"Could not open form link: {str(exc)[:120]}", "url": best["href"]})

    for item in await _collect_menu_items(page):
        text = (item.get("text") or "").strip()
        if not text or SKIP_TEXT.search(text):
            continue
        if max((_score_nav_label_match(k, text) for k in keywords), default=0) >= 58:
            await emit({"type": "click", "message": f"Open \"{text}\" for form", "url": page.url, "element": text})
            if await _click_menu_item(page, text, origin=origin):
                await _wait_for_spa(page)
                if _is_allowed_nav_url(page.url, origin) and await _page_has_fillable_form(page):
                    return True

    return await _try_same_origin_contact_paths(page, origin, emit)


async def _fill_by_paragraph_label(page, label_clean: str, value: str) -> bool:
    """Sites that use <p class=\"label\"> instead of <label for=\"\">."""
    core = re.sub(r"\s*\*+\s*$", "", label_clean).strip()
    if not core:
        return False
    pattern = re.compile(re.escape(core), re.I)
    for sel in ("p.label", ".label", "label", "span.label", ".form-label", "legend"):
        loc = page.locator(sel).filter(has_text=pattern)
        count = await loc.count()
        for i in range(count):
            label_el = loc.nth(i)
            try:
                field = label_el.locator("xpath=following::input[1] | following::textarea[1] | following::select[1]")
                if not await field.count():
                    field = label_el.locator("xpath=..//input | xpath=..//textarea | xpath=..//select")
                if not await field.count():
                    field = label_el.locator("xpath=ancestor::*[1]//input | ancestor::*[1]//textarea | ancestor::*[1]//select")
                if not await field.count():
                    continue
                if await _type_value_into_locator(field, value):
                    return True
            except Exception:
                continue
    return False


async def _fill_form_field(page, label: str, value: str, emit) -> bool:
    label_clean = label.strip()
    label_lower = label_clean.lower()
    escaped = re.escape(re.sub(r"\s*\*+\s*$", "", label_clean))

    strategies: list = []

    for name in _field_name_candidates(label_clean):
        strategies.append(
            lambda n=name: page.locator(
                f"input[name='{n}'], textarea[name='{n}'], select[name='{n}'], "
                f"input#{n}, textarea#{n}, select#{n}"
            )
        )
        strategies.append(lambda n=name: page.locator(f"input[name*='{n}'], textarea[name*='{n}']"))

    strategies.extend([
        lambda: page.get_by_label(re.compile(escaped, re.I)),
        lambda: page.get_by_placeholder(re.compile(escaped, re.I)),
        lambda: page.locator(
            f"input[name*='{label_lower.replace(' ', '')}'], textarea[name*='{label_lower.replace(' ', '')}']"
        ),
        lambda: page.get_by_role("textbox", name=re.compile(escaped, re.I)),
    ])

    if "email" in label_lower or "e-mail" in label_lower:
        strategies.insert(0, lambda: page.locator("input[type=email], input[name='email'], input#email"))
    if any(k in label_lower for k in ("phone", "mobile", "tel")):
        strategies.insert(0, lambda: page.locator(
            "input[type=tel], input[name='mobile'], input#mobile, input[name*='phone'], input[name*='mobile']"
        ))
    if any(k in label_lower for k in ("message", "comment", "enquiry", "inquiry", "description", "details")):
        strategies.insert(0, lambda: page.locator(
            "textarea, textarea[name='comments'], textarea#comments, textarea[name='message']"
        ))
    if "name" in label_lower and "organization" not in label_lower:
        strategies.insert(0, lambda: page.locator("input[name='name'], input#name"))

    for strategy in strategies:
        try:
            loc = strategy()
            if not await loc.count():
                continue
            el = loc.first
            tag = (await el.evaluate("e => e.tagName.toLowerCase()")) or "input"
            input_type = (await el.get_attribute("type") or "").lower()
            if tag == "select":
                try:
                    await el.select_option(label=value)
                except Exception:
                    await el.select_option(value=value)
            elif input_type in ("checkbox", "radio"):
                await el.check()
            else:
                await el.fill(value)
            await emit({
                "type": "fill",
                "message": f"Filled '{label_clean}' → {value[:60]}",
                "url": page.url,
                "field": label_clean,
            })
            return True
        except Exception:
            continue

    if await _fill_by_paragraph_label(page, label_clean, value):
        await emit({
            "type": "fill",
            "message": f"Filled '{label_clean}' → {value[:60]}",
            "url": page.url,
            "field": label_clean,
        })
        return True
    return False


async def _click_form_submit(page, emit) -> bool:
    submit_patterns = [
        "input[type=submit]",
        "button[type=submit]",
        "form input.btn[type=submit]",
        "form .general_button",
    ]
    for sel in submit_patterns:
        loc = page.locator(sel)
        if await loc.count() and await _safe_click(page, loc):
            val = await loc.first.get_attribute("value")
            label = (val or "Submit").strip()
            await emit({"type": "click", "message": f"Click \"{label}\"", "url": page.url, "element": label})
            return True

    for name in (
        "Send Message",
        "Send message",
        "Submit",
        "Send",
        "Enquiry",
        "Inquiry",
        "Contact",
        "Send enquiry",
    ):
        loc = page.get_by_role("button", name=name, exact=False)
        if await loc.count() and await _safe_click(page, loc):
            await emit({"type": "click", "message": f"Click \"{name}\"", "url": page.url, "element": name})
            return True
    return False


async def _verify_form_submitted(page, before_url: str, emit) -> bool:
    await page.wait_for_timeout(1500)
    try:
        await page.wait_for_load_state("domcontentloaded", timeout=5000)
    except Exception:
        pass
    after_url = page.url
    body = (await page.locator("body").inner_text())[:2000].lower()
    success_words = ("thank", "success", "received", "submitted", "sent", "confirmation")
    if after_url != before_url:
        await emit({"type": "verify", "message": f"Form submitted — navigated to {after_url}", "url": after_url})
        return True
    if any(w in body for w in success_words):
        await emit({"type": "verify", "message": "Form submitted — success message displayed", "url": after_url})
        return True
    await emit({"type": "warning", "message": "Submit clicked — no clear success message (check required fields)", "url": after_url})
    return False


def _extract_submit_label(log: list[dict]) -> str:
    for e in reversed(log):
        if e.get("type") != "click":
            continue
        msg = e.get("message", "")
        m = re.search(r'Click "([^"]+)"', msg)
        if m:
            label = m.group(1).strip()
            if any(w in label.lower() for w in ("send", "submit", "message", "enquiry", "contact")):
                return label
    return "Send Message"


def _build_form_flow_test_case(
    start_url: str,
    intent,
    form_url: str,
    submitted: bool,
    navigation_log: list[dict],
    form_fields: list | None = None,
) -> dict:
    """One clean test case: navigate → open target → fill fields → submit → verify."""
    from app.runners.discovery_prompt import navigation_targets

    nav_targets = navigation_targets(intent)
    fields = form_fields or intent.form_fields
    steps: list[dict] = []
    order = 1

    steps.append({
        "order": order,
        "action": "navigate",
        "description": f"Navigate to {start_url}",
        "url": start_url,
    })
    order += 1

    for target in nav_targets:
        steps.append({
            "order": order,
            "action": "click",
            "description": f"Open {target}",
            "element": target,
        })
        order += 1

    norm_start = _normalize_url(start_url)
    norm_form = _normalize_url(form_url)
    if norm_form != norm_start:
        verify_label = nav_targets[0] if nav_targets else "Contact form"
        steps.append({
            "order": order,
            "action": "verify",
            "description": f"Verify {verify_label} page is displayed with enquiry form",
            "url": form_url,
        })
        order += 1

    for field in fields:
        label = field.label.strip()
        steps.append({
            "order": order,
            "action": "fill",
            "description": f"Enter {label}: {field.value}",
            "field": label,
        })
        order += 1

    submit_label = _extract_submit_label(navigation_log)
    steps.append({
        "order": order,
        "action": "click",
        "description": f"Click {submit_label}",
        "element": submit_label,
    })
    order += 1

    steps.append({
        "order": order,
        "action": "verify",
        "description": "Confirm enquiry submitted successfully",
    })

    flow_name = nav_targets[0] if nav_targets else "Contact form"
    return {
        "id": _new_id(),
        "title": f"{flow_name} — submit enquiry form",
        "type": "functional",
        "priority": "critical",
        "source": "qa_agent",
        "risk": "high",
        "flow_kind": "form_submit",
        "module": "Forms",
        "screen": flow_name,
        "steps": steps,
        "expected_results": [
            f"{flow_name} page opens with the enquiry form visible",
            "All required fields accept the provided data",
            "Form submits without validation errors",
            "Success confirmation or thank-you message is shown" if submitted else "Form submission completes",
        ],
    }


def _form_submission_test_case(
    page_url: str,
    page_title: str,
    fields: list,
    submitted: bool,
) -> dict:
    from app.runners.discovery_prompt import FormFieldSpec

    steps = [{"order": 1, "action": "navigate", "description": f"Open {page_url}", "url": page_url}]
    order = 2
    for field in fields:
        spec = field if isinstance(field, FormFieldSpec) else FormFieldSpec(str(field.get("label", "")), str(field.get("value", "")))
        steps.append({
            "order": order,
            "action": "fill",
            "description": f"Enter '{spec.value}' in {spec.label}",
            "field": spec.label,
        })
        order += 1
    steps.append({"order": order, "action": "click", "description": "Click Submit / Send"})
    steps.append({
        "order": order + 1,
        "action": "verify",
        "description": "Confirm enquiry submitted successfully",
    })
    return {
        "id": _new_id(),
        "title": f"Enquiry form — {page_title or 'submission'}",
        "type": "functional",
        "priority": "critical",
        "source": "qa_agent",
        "risk": "high",
        "module": "Forms",
        "screen": page_title,
        "steps": steps,
        "expected_results": [
            "All instructed fields accept the provided data",
            "Form submits without validation errors",
            "Success confirmation or thank-you page is shown" if submitted else "Form submission completes",
        ],
    }


async def _execute_form_workflow(
    page,
    intent,
    origin: str,
    emit,
    proposed_cases: list[dict],
    *,
    start_url: str = "",
    navigation_log: list[dict] | None = None,
) -> bool:
    """Fill and submit a form using field values from the discovery prompt."""
    from app.runners.discovery_prompt import DiscoveryIntent, filter_form_fields

    if not isinstance(intent, DiscoveryIntent):
        return False
    if not intent.wants_form_submit and not intent.form_fields:
        return False
    fields = filter_form_fields(intent.form_fields)
    if not fields:
        await emit({
            "type": "warning",
            "message": "Form submission requested but no field values found — add lines like 'Name: John, Email: john@test.com'",
            "url": page.url,
        })
        return False

    await emit({"type": "action", "message": "Starting form submission from your prompt…", "url": page.url})
    if not _is_allowed_nav_url(page.url, origin):
        await emit({
            "type": "error",
            "message": (
                "Cannot submit the form — browser left your application "
                f"(now on {urlparse(page.url).netloc}). Stay on the same site only."
            ),
            "url": page.url,
        })
        return False

    if not await _ensure_contact_form_page(page, origin, emit, intent.explicit_targets):
        await emit({
            "type": "error",
            "message": (
                "Could not find enquiry/contact form — set Base URL to the contact page "
                "(e.g. https://www.vivilextech.com/contact-us.html) or say 'open Contact Us'"
            ),
            "url": page.url,
        })
        return False

    await _scroll_to_form(page)
    await page.wait_for_timeout(800)

    filled, missing = await _fill_all_prompt_fields(page, fields, emit)
    if missing:
        await emit({
            "type": "warning",
            "message": f"Could not locate field(s): {', '.join(missing)} — check labels match the form on the page",
            "url": page.url,
        })
    if filled == 0:
        await emit({
            "type": "error",
            "message": "No form fields could be filled — ensure Playwright is running (not HTTP crawl fallback)",
            "url": page.url,
        })
        return False

    before_url = page.url
    if not await _click_form_submit(page, emit):
        await emit({"type": "error", "message": "Submit button not found on the form", "url": page.url})
        return False

    if not _is_allowed_nav_url(page.url, origin):
        await emit({"type": "error", "message": "Form submit aborted — not on application site", "url": page.url})
        return False

    submitted = await _verify_form_submitted(page, before_url, emit)
    proposed_cases.append(_build_form_flow_test_case(
        start_url or page.url,
        intent,
        page.url,
        submitted,
        navigation_log or [],
        form_fields=fields,
    ))
    return True


async def _probe_form(page, page_title: str, emit) -> dict | None:
    fields = await page.eval_on_selector_all(
        "input:not([type=hidden]):not([type=submit]), textarea, select",
        """els => els.slice(0, 6).map(e => ({
            name: e.name || e.id || e.placeholder || e.type,
            type: e.type || e.tagName.toLowerCase(),
            placeholder: e.placeholder || ''
        }))""",
    )
    if not fields:
        return None
    case_id = _new_id()
    steps = [
        {"order": 1, "action": "navigate", "description": f"Navigate to {page.url}", "url": page.url},
    ]
    for i, field in enumerate(fields, start=2):
        label = field.get("name") or field.get("placeholder") or f"field_{i}"
        await emit({"type": "inspect", "message": f"Form field detected: {label} ({field.get('type')})", "url": page.url})
        steps.append({
            "order": i,
            "action": "fill" if field.get("type") != "select" else "select",
            "description": f"Enter valid data in '{label}' field",
            "field": label,
            "field_type": field.get("type"),
        })
    steps.append({
        "order": len(steps) + 1,
        "action": "verify",
        "description": "Verify form accepts input and submit button is enabled",
    })
    return {
        "id": case_id,
        "title": f"Form validation — {page_title or 'Page'}",
        "type": "functional",
        "priority": "high",
        "source": "qa_agent",
        "risk": "high",
        "module": (page_title or "General").split()[0][:40],
        "screen": page_title,
        "steps": steps,
        "expected_results": [
            "All required fields accept valid input",
            "Form validation messages display correctly for invalid data",
            "Submit action completes successfully",
        ],
    }


def _build_combined_navigation_test_case(
    start_url: str,
    navigated: list[tuple[str, str, str]],
    *,
    journey_name: str = "Navigation journey",
    logged_in: bool = False,
) -> dict:
    """One end-to-end test case: start at base URL, open each menu from the homepage in order."""
    steps: list[dict] = []
    order = 1

    if logged_in:
        steps.append({
            "order": order,
            "action": "navigate",
            "description": "Login and reach application dashboard",
            "url": start_url,
            "expected": "Dashboard loads successfully",
        })
    else:
        steps.append({
            "order": order,
            "action": "navigate",
            "description": f"Navigate to {start_url}",
            "url": start_url,
            "expected": "Application homepage loads without errors",
        })
    order += 1

    for idx, (target, _page_url, title) in enumerate(navigated):
        if idx > 0:
            steps.append({
                "order": order,
                "action": "navigate",
                "description": f"Return to homepage ({start_url})",
                "url": start_url,
                "expected": "Homepage is displayed before opening the next menu",
            })
            order += 1
        steps.append({
            "order": order,
            "action": "click",
            "description": f"Open '{target}' from main menu",
            "element": target,
            "expected": f"{target} category or module page opens",
        })
        order += 1
        page_title = title or target
        steps.append({
            "order": order,
            "action": "verify",
            "description": f"Verify {target} page loads ({page_title})",
            "expected": f"{target} content is displayed",
        })
        order += 1

    labels = [t for t, _, _ in navigated]
    title_suffix = ", ".join(labels[:4])
    if len(labels) > 4:
        title_suffix += f" (+{len(labels) - 4} more)"

    return {
        "id": _new_id(),
        "title": f"{journey_name} — {title_suffix}",
        "type": "e2e",
        "priority": "high",
        "source": "qa_agent",
        "risk": "high",
        "module": labels[0] if labels else "Navigation",
        "screen": journey_name,
        "flow_kind": "menu_journey",
        "steps": steps,
        "expected_results": [
            f"Journey starts from {start_url}",
            "Each menu is opened from the homepage (not via deep links)",
            "All requested menus load without errors",
        ],
    }


def _menu_module_test(module_name: str, url: str, title: str, *, logged_in: bool = False, home_url: str = "") -> dict:
    start_url = home_url or url
    entry_step = (
        "Login and reach application dashboard"
        if logged_in
        else f"Navigate to {start_url}"
    )
    page_title = title or module_name
    return {
        "id": _new_id(),
        "title": f"Module flow — {module_name}",
        "type": "functional",
        "priority": "high",
        "source": "qa_agent",
        "risk": "high",
        "module": module_name,
        "screen": page_title,
        "steps": [
            {
                "order": 1,
                "action": "navigate",
                "description": entry_step,
                "url": start_url,
                "expected": "Application homepage loads without errors",
            },
            {
                "order": 2,
                "action": "click",
                "description": f"Open '{module_name}' from main menu",
                "element": module_name,
                "expected": f"{module_name} category or module page opens",
            },
            {
                "order": 3,
                "action": "verify",
                "description": f"Verify {module_name} module loads ({page_title})",
                "expected": f"Page title contains expected content for {module_name}",
            },
            {
                "order": 4,
                "action": "verify",
                "description": f"Verify key lists, forms, or actions are visible in {module_name}",
                "expected": f"Primary {module_name} content is displayed",
            },
        ],
        "expected_results": [
            f"{module_name} module opens without errors",
            "Primary module content is displayed",
            "User can interact with module features",
        ],
    }


def _page_smoke_test(url: str, title: str, info: dict) -> dict:
    return {
        "id": _new_id(),
        "title": f"Smoke test — {title or urlparse(url).path or 'Homepage'}",
        "type": "smoke",
        "priority": "medium",
        "source": "qa_agent",
        "risk": "medium",
        "module": (title or "General").split()[0][:40] if title else "General",
        "screen": title,
        "steps": [
            {"order": 1, "action": "navigate", "description": f"Open {url}", "url": url},
            {"order": 2, "action": "verify", "description": f"Verify page loads with title '{title}'", "expected": title},
            {"order": 3, "action": "verify", "description": f"Verify page has {info['links']} links, {info.get('menus', 0)} menu items, and {info['buttons']} interactive elements"},
        ],
        "expected_results": [
            f"Page '{title}' loads successfully (HTTP 200)",
            "Primary navigation elements are visible",
            "No critical JavaScript errors on load",
        ],
    }


def _link_navigation_test(from_url: str, from_title: str, link: dict) -> dict:
    return {
        "id": _new_id(),
        "title": f"Navigation — {link['text'][:50]}",
        "type": "functional",
        "priority": "medium",
        "source": "qa_agent",
        "risk": "medium",
        "module": (from_title or "General").split()[0][:40] if from_title else "General",
        "screen": from_title,
        "steps": [
            {"order": 1, "action": "navigate", "description": f"Start at {from_title or from_url}", "url": from_url},
            {"order": 2, "action": "click", "description": f"Click link \"{link['text']}\"", "element": link["text"], "target": link["href"]},
            {"order": 3, "action": "verify", "description": f"Verify browser navigates to {link['href']}", "expected": link["href"]},
        ],
        "expected_results": [
            f"Link \"{link['text']}\" is clickable",
            "Target page loads without errors",
            "URL matches expected destination",
        ],
    }


def _button_click_test(from_url: str, btn: dict, result_title: str) -> dict:
    return {
        "id": _new_id(),
        "title": f"Interaction — Click '{btn['text'][:40]}'",
        "type": "functional",
        "priority": "medium",
        "source": "qa_agent",
        "risk": "medium",
        "steps": [
            {"order": 1, "action": "navigate", "description": f"Navigate to {from_url}", "url": from_url},
            {"order": 2, "action": "click", "description": f"Click button \"{btn['text']}\"", "element": btn["text"]},
            {"order": 3, "action": "verify", "description": f"Verify result page: {result_title}", "expected": result_title},
        ],
        "expected_results": [
            f"Button \"{btn['text']}\" responds to click",
            "Expected page transition or action occurs",
            "No error messages displayed",
        ],
    }


def _instruction_session_test(start_url: str, log: list[dict], goals: str | None) -> dict:
    """One test case summarizing only what the agent did per user instructions."""
    skip_types = {"status", "warning", "error", "observe", "agent_start", "agent_complete"}
    action_types = {"navigate", "click", "fill", "verify", "inspect"}
    nav_events = [
        e for e in log
        if e.get("type") in action_types
        and e.get("type") not in skip_types
        and not (e.get("type") == "action" and "starting form" in (e.get("message") or "").lower())
    ]
    nav_events.sort(key=lambda e: e.get("timestamp") or "")
    steps = []
    for i, e in enumerate(nav_events[:20], start=1):
        step: dict = {
            "order": i,
            "action": e.get("type", "action"),
            "description": e.get("message", ""),
        }
        if e.get("url"):
            step["url"] = e["url"]
        if e.get("element"):
            step["element"] = e["element"]
        if e.get("field"):
            step["field"] = e["field"]
        steps.append(step)
    goal_snippet = (goals or "session").split("\n")[0][:60]
    title = f"Instruction flow — {goal_snippet}"
    return {
        "id": _new_id(),
        "title": title,
        "type": "e2e",
        "priority": "high",
        "source": "qa_agent",
        "risk": "high",
        "steps": steps or [{"order": 1, "action": "navigate", "description": f"Open {start_url}", "url": start_url}],
        "expected_results": [
            "Agent completes only the steps described in the Discovery prompt",
            "No unrequested modules or pages are explored",
        ],
    }


def _full_session_test(start_url: str, log: list[dict]) -> dict:
    nav_events = [e for e in log if e.get("type") in ("navigate", "click", "fill", "verify")]
    nav_events.sort(key=lambda e: e.get("timestamp") or "")
    steps = []
    for i, e in enumerate(nav_events[:15], start=1):
        steps.append({
            "order": i,
            "action": e.get("type", "action"),
            "description": e.get("message", ""),
            "url": e.get("url"),
        })
    return {
        "id": _new_id(),
        "title": "End-to-end session walkthrough",
        "type": "e2e",
        "priority": "critical",
        "source": "qa_agent",
        "risk": "high",
        "steps": steps,
        "expected_results": [
            "Complete user session executes without blocking errors",
            "All visited pages render correctly",
            "Navigation flow matches application design",
        ],
    }


def _build_journey_from_log(log: list[dict], name: str, risk: str) -> dict:
    return {"name": name, "risk": risk, "events": len(log)}


def _screens_from_log(log: list[dict]) -> list[dict]:
    screens = []
    seen = set()
    for e in log:
        if e.get("type") != "navigate":
            continue
        url = e.get("url", "")
        title = e.get("title") or url
        if url in seen:
            continue
        seen.add(url)
        screens.append({"name": title[:80], "url": url, "url_pattern": url, "elements": {}})
    return screens


def _flows_from_cases(cases: list[dict], start_url: str) -> list[dict]:
    return [{
        "id": "flow-qa-agent",
        "name": "QA Agent Exploration",
        "entry_url": start_url,
        "steps": [c["title"] for c in cases[:10]],
        "risk": "high",
        "source": "qa_agent",
        "test_cases_count": len(cases),
    }]


def _apis_from_log(log: list[dict]) -> list[dict]:
    apis = []
    for e in log:
        url = e.get("url") or e.get("target") or ""
        if "/api/" in url:
            path = urlparse(url).path
            apis.append({"method": "GET", "path": path, "purpose": "discovered"})
    return apis


def _normalize_url(url: str) -> str:
    return url.rstrip("/").split("#")[0].split("?")[0]


def _same_origin(origin: str, url: str) -> bool:
    try:
        return urlparse(origin).netloc == urlparse(url).netloc
    except Exception:
        return False


async def _fallback_http_agent(
    start_url: str, origin: str, max_pages: int, emit, *, reason: str | None = None, requirements: str | None = None
) -> dict:
    from app.runners.browser_discovery import crawl_application

    nav: list[dict] = []

    async def log_event(event: dict) -> None:
        event["timestamp"] = _now()
        nav.append(event)
        await emit(event)

    detail = reason or "browser automation not available"
    if "cursor-sandbox-cache" in detail or "sandbox-cache" in detail:
        detail = "stale browser path (run update-and-install.bat, then restart.bat)"
    await log_event({
        "type": "agent_start",
        "message": f"Playwright unavailable ({detail}) — using HTTP crawl fallback",
    })
    if reason and ("install" in reason.lower() or "sandbox" in reason.lower() or "Executable doesn't exist" in reason):
        await log_event({
            "type": "warning",
            "message": "Fix: run update-and-install.bat, then restart.bat. HTTP crawl only fetches static pages — use Playwright for login and menus.",
        })
    await log_event({
        "type": "error",
        "message": (
            "Prompt instructions (login, form submit, open pages) cannot run without Playwright. "
            "HTTP crawl only lists static links — it cannot fill or submit forms."
        ),
    })
    from app.runners.discovery_prompt import parse_discovery_prompt

    prompt_intent = parse_discovery_prompt(requirements)
    if prompt_intent.form_fields or prompt_intent.wants_form_submit:
        await log_event({
            "type": "error",
            "message": (
                "Form fill was requested but Playwright browser is not available. "
                "Run update-and-install.bat then restart.bat."
            ),
        })
    crawled = await crawl_application(start_url, max_pages=max_pages)
    for p in crawled.get("pages", []):
        await log_event({"type": "navigate", "message": f"Fetched {p.get('title') or p['url']}", "url": p["url"], "title": p.get("title")})
    cases = []
    for p in crawled.get("pages", []):
        cases.append(_page_smoke_test(p["url"], p.get("title", ""), {"links": 0, "forms": p.get("forms", 0), "buttons": p.get("buttons", 0), "inputs": p.get("inputs", 0)}))
    await log_event({"type": "agent_complete", "message": f"HTTP crawl complete — {len(cases)} test cases proposed"})
    return {
        "mode": "http_fallback",
        "pages_crawled": crawled.get("pages_crawled", 0),
        "navigation_log": nav,
        "proposed_test_cases": cases,
        "screens": crawled.get("screens", []),
        "flow_map": crawled.get("flow_map", []),
        "apis": crawled.get("apis", []),
    }

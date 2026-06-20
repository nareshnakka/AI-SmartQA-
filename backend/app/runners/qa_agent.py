"""QA Agent — navigates applications like a real tester and captures test cases."""

import re
import uuid
from datetime import datetime, timezone
from urllib.parse import urlparse

import structlog

from app.config import settings

logger = structlog.get_logger()

SKIP_TEXT = re.compile(
    r"delete|remove|logout|log out|sign out|cancel subscription|destroy|upgrade",
    re.I,
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_id(prefix: str = "ptc") -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


async def navigate_as_qa_user(
    base_url: str,
    username: str | None = None,
    password: str | None = None,
    max_pages: int | None = None,
    max_steps: int | None = None,
    requirements: str | None = None,
    on_event=None,
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
        from app.runners.setup_status import _playwright_browsers_on_disk

        pw_ok, pw_hint = _playwright_browsers_on_disk()
        if not pw_ok:
            return await _fallback_http_agent(
                *_agent_urls(base_url),
                max_pages or settings.discovery_max_pages,
                on_event_cb,
                reason=pw_hint,
            )

        try:
            from playwright.async_api import async_playwright  # noqa: F401
        except ImportError as exc:
            return await _fallback_http_agent(
                *_agent_urls(base_url),
                max_pages or settings.discovery_max_pages,
                on_event_cb,
                reason=str(exc) or "playwright package not installed",
            )

        try:
            return await _navigate_with_playwright(
                base_url, username, password, max_pages, max_steps, requirements, on_event_cb
            )
        except NotImplementedError:
            logger.warning("playwright_subprocess_unsupported", platform=sys.platform)
            return await _fallback_http_agent(
                *_agent_urls(base_url),
                max_pages or settings.discovery_max_pages,
                on_event_cb,
                reason="Playwright subprocess not supported on this platform",
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
            )

    if use_isolated:
        collected: list[dict] = []
        done = asyncio.Event()
        result_box: dict = {}

        async def collect(event: dict) -> None:
            collected.append(event)

        async def factory() -> dict:
            return await _run(collect)

        async def replay_events() -> None:
            last = 0
            while not done.is_set() or last < len(collected):
                while last < len(collected):
                    if on_event:
                        cb = on_event(collected[last])
                        if cb is not None and hasattr(cb, "__await__"):
                            await cb
                    last += 1
                if done.is_set():
                    break
                await asyncio.sleep(0.75)

        async def run_agent() -> None:
            result_box["result"] = await run_isolated_async(factory)
            done.set()

        await asyncio.gather(replay_events(), run_agent())
        return result_box["result"]

    return await _run(on_event)


def _agent_urls(base_url: str) -> tuple[str, str]:
    parsed = urlparse(base_url if "://" in base_url else f"https://{base_url}")
    origin = f"{parsed.scheme}://{parsed.netloc}"
    start_url = base_url if "://" in base_url else origin
    return start_url, origin


def _keywords_from_requirements(requirements: str | None) -> list[str]:
    if not requirements:
        return []
    words = re.findall(r"[a-zA-Z]{3,}", requirements.lower())
    stop = {"the", "and", "for", "want", "user", "that", "with", "from", "this", "have", "can"}
    return [w for w in words if w not in stop]


def _score_nav_text(text: str, keywords: list[str]) -> int:
    lower = text.lower()
    return sum(2 for kw in keywords if kw in lower)


MENU_SELECTORS = (
    ".oxd-main-menu-item, [role=menuitem], nav a, .sidebar a, "
    ".menu-item, .nav-item, .sidebar-item, [class*='menu-item']"
)


async def _wait_for_spa(page, timeout_ms: int = 12000) -> None:
    try:
        await page.wait_for_load_state("networkidle", timeout=timeout_ms)
    except Exception:
        pass
    try:
        await page.wait_for_selector(
            "a[href], .oxd-main-menu-item, [role=menuitem], nav, main, [role=main]",
            timeout=5000,
        )
    except Exception:
        await page.wait_for_timeout(2000)


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
                out.push({ text, tag: e.tagName.toLowerCase() });
            }
            return out;
        }""",
    )
    return raw or []


async def _click_menu_item(page, text: str) -> bool:
    if SKIP_TEXT.search(text):
        return False
    for selector in [".oxd-main-menu-item", "[role=menuitem]", "nav a", ".sidebar a"]:
        loc = page.locator(selector).filter(has_text=text)
        if await loc.count():
            await loc.first.click(timeout=8000)
            return True
    loc = page.get_by_text(text, exact=True)
    if await loc.count():
        await loc.first.click(timeout=8000)
        return True
    return False


async def _collect_nav_targets(page, origin: str, requirements: str | None) -> list[dict]:
    keywords = _keywords_from_requirements(requirements)
    targets: list[dict] = []

    for link in await _collect_actionable_links(page, origin):
        targets.append({"kind": "url", "text": link["text"], "href": link["href"], "score": _score_nav_text(link["text"], keywords)})

    for item in await _collect_menu_items(page):
        text = item.get("text", "")
        if not text or SKIP_TEXT.search(text):
            continue
        targets.append({"kind": "menu", "text": text, "score": _score_nav_text(text, keywords) + 1})

    targets.sort(key=lambda t: t.get("score", 0), reverse=True)
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
) -> dict:
    from playwright.async_api import async_playwright

    max_pages = max_pages or settings.discovery_max_pages
    max_steps = max_steps or settings.discovery_max_steps
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

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=settings.playwright_headless)
        context = await browser.new_context(ignore_https_errors=True, viewport={"width": 1280, "height": 720})
        page = await context.new_page()

        await emit({"type": "agent_start", "message": f"QA Agent starting exploration of {start_url}"})

        logged_in = False
        if username and password:
            await page.goto(start_url, timeout=settings.playwright_timeout_ms, wait_until="load")
            await page.wait_for_timeout(1500)
            logged_in = await _attempt_login(page, username, password, emit)
            if logged_in:
                journeys.append(_build_journey_from_log(navigation_log, "Login Journey", "high"))
                await _wait_for_spa(page)
                step_count += 1
        else:
            await page.goto(start_url, timeout=settings.playwright_timeout_ms, wait_until="domcontentloaded")
            await _wait_for_spa(page)

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
            proposed_cases.append(_page_smoke_test(page.url, title, page_info))
            if page_info["forms"] > 0:
                form_case = await _probe_form(page, title, emit)
                if form_case:
                    proposed_cases.append(form_case)
                    step_count += len(form_case.get("steps", []))
            for target in await _collect_nav_targets(page, origin, requirements):
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

        # Seed queue from post-login / landing page
        norm_current = _normalize_url(page.url)
        visited_urls.add(norm_current)
        await explore_current_page("login" if logged_in else "start")

        while queue and (len(visited_urls) + len(visited_menus)) < max_pages and step_count < max_steps:
            target = queue.pop(0)
            prev_url = page.url

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
                if not await _click_menu_item(page, menu_text):
                    await emit({"type": "error", "message": f"Could not open menu: {menu_text}", "url": page.url})
                    continue
                await _wait_for_spa(page)
                step_count += 1
                mod_title = await page.title()
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
                    await emit({"type": "error", "message": f"Navigation failed: {str(e)[:200]}", "url": href})
                    continue

            norm = _normalize_url(page.url)
            if norm not in visited_urls:
                visited_urls.add(norm)

            title = await page.title()
            await explore_current_page("explore")

            # Optionally click one safe button per page (skip promos / destructive actions)
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
                    await page.locator(btn["selector"]).first.click(timeout=5000)
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
                    await emit({"type": "error", "message": f"Click failed: {str(e)[:120]}", "url": page.url})

        await browser.close()

    await emit({"type": "agent_complete", "message": f"Exploration complete — {len(visited_urls)} pages, {len(visited_menus)} modules, {len(proposed_cases)} test cases proposed"})

    # Deduplicate proposed cases by title
    seen_titles: set[str] = set()
    unique_cases: list[dict] = []
    for case in proposed_cases:
        t = case["title"]
        if t not in seen_titles:
            seen_titles.add(t)
            unique_cases.append(case)

    # Journey-level test cases from full navigation log
    if len(navigation_log) > 3:
        unique_cases.insert(0, _full_session_test(start_url, navigation_log))

    return {
        "mode": "qa_agent",
        "pages_crawled": len(visited_urls),
        "modules_explored": len(visited_menus),
        "navigation_log": navigation_log,
        "proposed_test_cases": unique_cases,
        "screens": _screens_from_log(navigation_log),
        "flow_map": _flows_from_cases(unique_cases, start_url),
        "apis": _apis_from_log(navigation_log),
    }


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


def _menu_module_test(module_name: str, url: str, title: str) -> dict:
    return {
        "id": _new_id(),
        "title": f"Module flow — {module_name}",
        "type": "functional",
        "priority": "high",
        "source": "qa_agent",
        "risk": "high",
        "module": module_name,
        "screen": title or module_name,
        "steps": [
            {"order": 1, "action": "navigate", "description": "Login and reach application dashboard", "url": url},
            {"order": 2, "action": "click", "description": f"Open '{module_name}' from main menu", "element": module_name},
            {"order": 3, "action": "verify", "description": f"Verify {module_name} module loads ({title or module_name})", "expected": title or module_name},
            {"order": 4, "action": "verify", "description": f"Verify key lists, forms, or actions are visible in {module_name}"},
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


def _full_session_test(start_url: str, log: list[dict]) -> dict:
    nav_events = [e for e in log if e.get("type") in ("navigate", "click", "fill", "verify")]
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
    start_url: str, origin: str, max_pages: int, emit, *, reason: str | None = None
) -> dict:
    from app.runners.browser_discovery import crawl_application

    nav: list[dict] = []

    async def log_event(event: dict) -> None:
        event["timestamp"] = _now()
        nav.append(event)
        await emit(event)

    detail = reason or "browser automation not available"
    await log_event({
        "type": "agent_start",
        "message": f"Playwright unavailable ({detail}) — using HTTP crawl fallback",
    })
    if reason and "install" in reason.lower():
        await log_event({
            "type": "warning",
            "message": "Fix: run scripts\\install-playwright.bat from the project root, then restart the backend.",
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

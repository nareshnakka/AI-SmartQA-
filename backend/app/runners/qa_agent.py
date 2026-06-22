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


async def _click_menu_item(page, text: str) -> bool:
    if SKIP_TEXT.search(text):
        return False

    for selector in [".oxd-main-menu-item", "[role=menuitem]", "nav a", ".sidebar a", "header nav a"]:
        loc = page.locator(selector).filter(has_text=text)
        if await loc.count():
            if await _safe_click(page, loc):
                return True
            break

    loc = page.get_by_role("link", name=text, exact=False)
    if await loc.count():
        if await _safe_click(page, loc):
            return True

    loc = page.get_by_text(text, exact=True)
    if await loc.count():
        if await _safe_click(page, loc):
            return True

    href = await _menu_item_href(page, text)
    if href:
        try:
            dest = urljoin(page.url, href)
            await page.goto(dest, timeout=settings.playwright_timeout_ms, wait_until="domcontentloaded")
            return True
        except Exception:
            pass
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
        max_steps = min(max_steps, max(len(explicit_targets) * 8 + 10, 15))
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
        instruction_mode = strict_follow and not intent.broad_exploration

        if instruction_mode:
            from app.runners.discovery_prompt import has_actionable_instructions, navigation_targets

            await emit({
                "type": "status",
                "message": "Instruction mode — executing your prompt only (no menu crawl)",
            })
            form_completed = await _run_instruction_plan(
                page, intent, origin, emit, proposed_cases, logged_in,
            )
            step_count += max(len(intent.form_fields), 1)
        else:
            if intent.wants_form_submit or intent.form_fields:
                form_completed = await _execute_form_workflow(page, intent, origin, emit, proposed_cases)
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
    seen_titles: set[str] = set()
    unique_cases: list[dict] = []
    for case in proposed_cases:
        t = case["title"]
        if t not in seen_titles:
            seen_titles.add(t)
            unique_cases.append(case)

    # Journey-level test cases from navigation log (strict: only from actual agent actions)
    if len(navigation_log) > 3:
        if strict_follow:
            unique_cases.insert(0, _instruction_session_test(start_url, navigation_log, nav_requirements))
        else:
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


async def _open_named_target(page, target: str, origin: str, emit) -> bool:
    """Navigate to a page or module named in the user's prompt."""
    target_clean = target.strip()
    if not target_clean:
        return False

    target_lower = target_clean.lower()
    await emit({
        "type": "click",
        "message": f"Open \"{target_clean}\" as instructed",
        "url": page.url,
        "element": target_clean,
    })

    if await _click_menu_item(page, target_clean):
        await _wait_for_spa(page)
        title = await page.title()
        await emit({
            "type": "navigate",
            "message": f"Opened {target_clean} — {title or page.url}",
            "url": page.url,
            "title": title,
        })
        return True

    for link in await _collect_actionable_links(page, origin):
        text_lower = link["text"].lower()
        if target_lower in text_lower or text_lower in target_lower:
            try:
                await emit({
                    "type": "navigate",
                    "message": f"Following link \"{link['text']}\" → {link['href']}",
                    "url": page.url,
                    "target": link["href"],
                    "element": link["text"],
                })
                await page.goto(link["href"], timeout=settings.playwright_timeout_ms, wait_until="domcontentloaded")
                await _wait_for_spa(page)
                title = await page.title()
                await emit({
                    "type": "navigate",
                    "message": f"Opened {target_clean} — {title or page.url}",
                    "url": page.url,
                    "title": title,
                })
                return True
            except Exception as exc:
                await emit({
                    "type": "warning",
                    "message": f"Could not follow link \"{link['text']}\": {str(exc)[:120]}",
                    "url": link["href"],
                })

    for item in await _collect_menu_items(page):
        text = (item.get("text") or "").strip()
        if not text or SKIP_TEXT.search(text):
            continue
        text_lower = text.lower()
        if target_lower in text_lower or text_lower in target_lower:
            if await _click_menu_item(page, text):
                await _wait_for_spa(page)
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
        "message": (
            f"Could not find \"{target_clean}\" on this page — "
            "check spelling matches a menu or link, or put the form URL in Base URL"
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

    for target in nav_targets:
        await _open_named_target(page, target, origin, emit)

    if intent.wants_form_submit or intent.form_fields:
        completed = await _execute_form_workflow(page, intent, origin, emit, proposed_cases)
    elif nav_targets:
        title = await page.title()
        for target in nav_targets:
            proposed_cases.append(_menu_module_test(target, page.url, title))
        await emit({
            "type": "verify",
            "message": f"Completed navigation to: {', '.join(nav_targets)}",
            "url": page.url,
            "title": title,
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
                    await el.fill(field.value)
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
    if await _page_has_fillable_form(page):
        return True

    keywords = list(_FORM_LINK_KEYWORDS)
    for target in explicit_targets or []:
        if target.lower() not in keywords:
            keywords.append(target.lower())

    for link in await _collect_actionable_links(page, origin):
        text = link["text"].lower()
        if any(k in text for k in keywords):
            try:
                await emit({
                    "type": "navigate",
                    "message": f"Opening form page — \"{link['text']}\"",
                    "url": page.url,
                    "target": link["href"],
                })
                await page.goto(link["href"], timeout=settings.playwright_timeout_ms, wait_until="domcontentloaded")
                await _wait_for_spa(page)
                return await _page_has_fillable_form(page)
            except Exception as exc:
                await emit({"type": "warning", "message": f"Could not open form link: {str(exc)[:120]}", "url": link["href"]})

    for item in await _collect_menu_items(page):
        text = (item.get("text") or "").strip()
        if not text or SKIP_TEXT.search(text):
            continue
        if any(k in text.lower() for k in keywords):
            await emit({"type": "click", "message": f"Open \"{text}\" for form", "url": page.url, "element": text})
            if await _click_menu_item(page, text):
                await _wait_for_spa(page)
                if await _page_has_fillable_form(page):
                    return True
    return False


async def _fill_form_field(page, label: str, value: str, emit) -> bool:
    label_clean = label.strip()
    label_lower = label_clean.lower()
    escaped = re.escape(label_clean)

    strategies: list = [
        lambda: page.get_by_label(re.compile(escaped, re.I)),
        lambda: page.get_by_placeholder(re.compile(escaped, re.I)),
        lambda: page.locator(
            f"input[name*='{label_lower}'], textarea[name*='{label_lower}'], select[name*='{label_lower}']"
        ),
        lambda: page.locator(
            f"input[id*='{label_lower}'], textarea[id*='{label_lower}'], select[id*='{label_lower}']"
        ),
        lambda: page.get_by_role("textbox", name=re.compile(escaped, re.I)),
    ]

    if "email" in label_lower:
        strategies.insert(0, lambda: page.locator("input[type=email]"))
    if any(k in label_lower for k in ("phone", "mobile", "tel")):
        strategies.insert(0, lambda: page.locator("input[type=tel], input[name*='phone'], input[name*='mobile']"))
    if any(k in label_lower for k in ("message", "comment", "enquiry", "inquiry", "description", "details")):
        strategies.insert(0, lambda: page.locator("textarea"))

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
    return False


async def _click_form_submit(page, emit) -> bool:
    submit_patterns = [
        "button[type=submit]",
        "input[type=submit]",
    ]
    for sel in submit_patterns:
        loc = page.locator(sel)
        if await loc.count() and await _safe_click(page, loc):
            await emit({"type": "click", "message": "Click submit button", "url": page.url, "element": "Submit"})
            return True

    for name in ("Submit", "Send", "Enquiry", "Inquiry", "Contact", "Send message", "Send enquiry"):
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


async def _execute_form_workflow(page, intent, origin: str, emit, proposed_cases: list[dict]) -> bool:
    """Fill and submit a form using field values from the discovery prompt."""
    from app.runners.discovery_prompt import DiscoveryIntent

    if not isinstance(intent, DiscoveryIntent):
        return False
    if not intent.wants_form_submit and not intent.form_fields:
        return False
    if not intent.form_fields:
        await emit({
            "type": "warning",
            "message": "Form submission requested but no field values found — add lines like 'Name: John, Email: john@test.com'",
            "url": page.url,
        })
        return False

    await emit({"type": "action", "message": "Starting form submission from your prompt…", "url": page.url})
    if not await _navigate_to_form_page(page, origin, emit, intent.explicit_targets):
        await emit({
            "type": "error",
            "message": "Could not find enquiry/contact form — add a link target (e.g. 'open Contact page') or put the form URL in Base URL",
            "url": page.url,
        })
        return False

    filled = 0
    missing: list[str] = []
    filled_labels: set[str] = set()
    for field in intent.form_fields:
        if await _fill_form_field(page, field.label, field.value, emit):
            filled += 1
            filled_labels.add(field.label.lower())
        else:
            missing.append(field.label)

    if missing:
        filled += await _fill_remaining_fields_sequential(page, intent.form_fields, filled_labels, emit)
        missing = [f.label for f in intent.form_fields if f.label.lower() not in filled_labels]
        if missing:
            await emit({
                "type": "warning",
                "message": f"Could not locate field(s): {', '.join(missing)} — check labels match the form on the page",
                "url": page.url,
            })
    if filled == 0:
        await emit({"type": "error", "message": "No form fields could be filled", "url": page.url})
        return False

    before_url = page.url
    if not await _click_form_submit(page, emit):
        await emit({"type": "error", "message": "Submit button not found on the form", "url": page.url})
        return False

    submitted = await _verify_form_submitted(page, before_url, emit)
    title = await page.title()
    proposed_cases.append(_form_submission_test_case(page.url, title, intent.form_fields, submitted))
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


def _instruction_session_test(start_url: str, log: list[dict], goals: str | None) -> dict:
    """One test case summarizing only what the agent did per user instructions."""
    action_types = {"navigate", "click", "fill", "verify", "action", "inspect"}
    nav_events = [e for e in log if e.get("type") in action_types and e.get("type") != "observe"]
    nav_events.sort(key=lambda e: e.get("timestamp") or "")
    steps = []
    for i, e in enumerate(nav_events[:20], start=1):
        steps.append({
            "order": i,
            "action": e.get("type", "action"),
            "description": e.get("message", ""),
            "url": e.get("url"),
        })
    title = f"Instruction flow — {(goals or 'session')[:60]}"
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
    start_url: str, origin: str, max_pages: int, emit, *, reason: str | None = None
) -> dict:
    from app.runners.browser_discovery import crawl_application

    nav: list[dict] = []

    async def log_event(event: dict) -> None:
        event["timestamp"] = _now()
        nav.append(event)
        await emit(event)

    detail = reason or "browser automation not available"
    if "cursor-sandbox-cache" in detail or "sandbox-cache" in detail:
        detail = "stale browser path (restart backend after scripts\\install-playwright.bat)"
    await log_event({
        "type": "agent_start",
        "message": f"Playwright unavailable ({detail}) — using HTTP crawl fallback",
    })
    if reason and ("install" in reason.lower() or "sandbox" in reason.lower() or "Executable doesn't exist" in reason):
        await log_event({
            "type": "warning",
            "message": "Fix: run scripts\\install-playwright.bat, then scripts\\restart-all-auto.bat. HTTP crawl only fetches static pages — use Playwright for login and menus.",
        })
    await log_event({
        "type": "error",
        "message": (
            "Prompt instructions (login, form submit, open pages) cannot run without Playwright. "
            "HTTP crawl only lists static links — it will not follow your prompt."
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

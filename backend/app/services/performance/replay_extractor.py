"""Extract performance flows from browser replay — discovery navigation logs and test cases."""

import re
from urllib.parse import urlparse

_URL_RE = re.compile(r"https?://[^\s\"'<>]+", re.I)


def _normalize_url(url: str, base_url: str) -> str | None:
    if not url:
        return None
    url = url.strip().rstrip(".,)")
    if url.startswith("/"):
        base = base_url.rstrip("/")
        return f"{base}{url}"
    if url.startswith("http"):
        return url.split("#")[0]
    return None


def _url_from_step(step: str | dict) -> str | None:
    if isinstance(step, dict):
        if step.get("url"):
            return step["url"]
        step = step.get("description", "") or step.get("action", "")
    if not isinstance(step, str):
        return None
    m = _URL_RE.search(step)
    return m.group(0) if m else None


def extract_from_navigation_log(navigation_log: list[dict], base_url: str) -> list[dict]:
    """Build HTTP steps from QA agent navigation replay events."""
    steps: list[dict] = []
    seen: set[str] = set()

    for event in navigation_log or []:
        etype = event.get("type", "")
        url = _normalize_url(event.get("url", ""), base_url)
        if not url or url in seen:
            continue

        if etype in ("navigate", "verify", "click", "inspect", "fill", "action"):
            name = event.get("message") or event.get("title") or f"{etype} {urlparse(url).path or '/'}"
            if etype == "fill":
                method = "POST"
            elif etype == "click":
                method = "GET"
            else:
                method = "GET"
            steps.append({
                "action": method,
                "url": url,
                "name": name[:80],
                "replay_type": etype,
            })
            if etype in ("navigate", "verify"):
                seen.add(url)

    if not steps and navigation_log:
        first = next((e for e in navigation_log if e.get("url")), None)
        if first:
            url = _normalize_url(first["url"], base_url)
            if url:
                steps.append({"action": "GET", "url": url, "name": "Session entry", "replay_type": "navigate"})

    return steps


def extract_from_test_case(tc: dict, base_url: str) -> list[dict]:
    """Build HTTP steps from committed test case steps (URLs embedded in text)."""
    steps: list[dict] = []
    raw_steps = tc.get("steps") or []
    for i, step in enumerate(raw_steps):
        url = _url_from_step(step)
        desc = step if isinstance(step, str) else step.get("description", str(step))
        if url:
            steps.append({
                "action": "GET",
                "url": _normalize_url(url, base_url) or url,
                "name": desc[:80] if isinstance(desc, str) else f"Step {i + 1}",
                "replay_type": "test_case",
            })
        elif isinstance(desc, str) and desc.lower().startswith(("navigate", "open", "visit", "go to")):
            steps.append({
                "action": "GET",
                "url": base_url,
                "name": desc[:80],
                "replay_type": "test_case",
            })
    return steps


def extract_from_har_entries(har_content: dict | str, limit: int = 30) -> list[dict]:
    if isinstance(har_content, str):
        import json
        har_content = json.loads(har_content)
    steps: list[dict] = []
    seen: set[str] = set()
    for entry in (har_content.get("log", {}).get("entries") or [])[:limit]:
        req = entry.get("request", {})
        url = req.get("url", "")
        method = req.get("method", "GET").upper()
        if not url.startswith("http") or url in seen:
            continue
        seen.add(url)
        path = urlparse(url).path or "/"
        steps.append({
            "action": method,
            "url": url,
            "name": f"{method} {path[-60:]}",
            "replay_type": "har",
            "expected_status": entry.get("response", {}).get("status", 200),
        })
    return steps


def build_flows_from_replay(
    *,
    navigation_log: list[dict] | None = None,
    test_cases: list[dict] | None = None,
    har_content: dict | str | None = None,
    proposed_test_cases: list[dict] | None = None,
    base_url: str = "https://example.com",
) -> tuple[list[dict], str]:
    """
    Returns (flows, resolved_base_url).
    Each flow: {name, weight, steps: [{action, url, name, ...}]}
    """
    flows: list[dict] = []
    resolved_base = base_url

    if navigation_log:
        for event in navigation_log:
            u = event.get("url", "")
            if u.startswith("http"):
                resolved_base = f"{urlparse(u).scheme}://{urlparse(u).netloc}"
                break

    if proposed_test_cases:
        for i, ptc in enumerate(proposed_test_cases[:10]):
            psteps = ptc.get("steps") or []
            http_steps = []
            for j, ps in enumerate(psteps):
                url = _url_from_step(ps) or (ps.get("url") if isinstance(ps, dict) else None)
                desc = ps.get("description", str(ps)) if isinstance(ps, dict) else str(ps)
                action = ps.get("action", "GET").upper() if isinstance(ps, dict) else "GET"
                if url:
                    http_steps.append({
                        "action": action if action in ("GET", "POST", "PUT", "DELETE", "PATCH") else "GET",
                        "url": _normalize_url(url, resolved_base) or url,
                        "name": desc[:80],
                        "replay_type": "proposed",
                    })
                elif desc:
                    http_steps.append({
                        "action": "GET",
                        "url": resolved_base,
                        "name": desc[:80],
                        "replay_type": "proposed",
                    })
            if http_steps:
                flows.append({
                    "name": ptc.get("title", f"Flow {i + 1}"),
                    "weight": 100 // max(len(proposed_test_cases), 1),
                    "steps": http_steps,
                    "source": "browser_replay",
                })

    if not flows and test_cases:
        for i, tc in enumerate(test_cases[:10]):
            http_steps = extract_from_test_case(tc, resolved_base)
            if not http_steps:
                http_steps = [{
                    "action": "GET",
                    "url": resolved_base,
                    "name": tc.get("title", f"Flow {i + 1}"),
                    "replay_type": "test_case",
                }]
            flows.append({
                "name": tc.get("title", f"Flow {i + 1}"),
                "weight": 100 // max(len(test_cases), 1),
                "steps": http_steps,
                "source": "test_cases",
            })

    if not flows and navigation_log:
        session_steps = extract_from_navigation_log(navigation_log, resolved_base)
        if session_steps:
            flows.append({
                "name": "Browser Replay Session",
                "weight": 100,
                "steps": session_steps,
                "source": "navigation_log",
            })

    if not flows and har_content:
        har_steps = extract_from_har_entries(har_content)
        if har_steps:
            if har_steps[0].get("url"):
                u = har_steps[0]["url"]
                resolved_base = f"{urlparse(u).scheme}://{urlparse(u).netloc}"
            flows.append({
                "name": "HAR Recorded Session",
                "weight": 100,
                "steps": har_steps,
                "source": "har",
            })

    if not flows:
        flows = [{
            "name": "Default",
            "weight": 100,
            "steps": [{"action": "GET", "url": resolved_base, "name": "Homepage", "replay_type": "fallback"}],
            "source": "fallback",
        }]

    return flows, resolved_base

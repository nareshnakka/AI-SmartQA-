"""Cursor Cloud API advisor for Discovery — planning menus, popups, and stuck navigation."""

from __future__ import annotations

import json
import re
from typing import Any

import structlog

from app.config import settings
from app.integrations.cursor_api import CursorAPIError, get_cursor_client_async
from app.runners.discovery_prompt import DiscoveryIntent, extract_menu_list_targets

logger = structlog.get_logger()


def _extract_json_object(text: str) -> dict[str, Any] | None:
    if not text:
        return None
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.I)
        text = re.sub(r"\s*```$", "", text)
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        return json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return None


async def get_cursor_discovery_status() -> dict[str, Any]:
    from app.services.cursor_auth import connection_summary
    from app.services.cursor_credential_store import get_cloud_api_key, has_cursor_session

    summary = connection_summary()
    api_key = get_cloud_api_key()
    signed_in = has_cursor_session()

    if not api_key and not signed_in:
        return {
            "configured": False,
            "enabled": settings.discovery_cursor_advisor_enabled,
            "available": False,
            "connected": False,
            "signed_in": False,
            "needs_api_key": False,
            "api_keys_url": summary.get("api_keys_url"),
            "message": "Click Connect Cursor to sign in — then add your Agent API key (one-time).",
        }

    if signed_in and not api_key:
        email = summary.get("email")
        return {
            "configured": True,
            "enabled": settings.discovery_cursor_advisor_enabled,
            "available": False,
            "connected": False,
            "signed_in": True,
            "needs_api_key": True,
            "api_key_name": email,
            "api_keys_url": summary.get("api_keys_url"),
            "message": (
                f"Signed in as {email} — paste your Cursor Agent API key (crsr_…) to finish setup."
                if email
                else "Signed in — paste your Cursor Agent API key (crsr_…) to finish setup."
            ),
        }

    client = await get_cursor_client_async()
    if not client:
        return {
            "configured": False,
            "enabled": settings.discovery_cursor_advisor_enabled,
            "available": False,
            "connected": False,
            "signed_in": signed_in,
            "needs_api_key": True,
            "message": "Add your Cursor Agent API key to enable Discovery planning.",
            "api_keys_url": summary.get("api_keys_url"),
        }

    try:
        me = await client.me()
        models = await client.list_models()
        model_ids = [m.get("id") for m in models if m.get("id")]
        return {
            "configured": True,
            "enabled": settings.discovery_cursor_advisor_enabled,
            "available": True,
            "connected": True,
            "signed_in": True,
            "needs_api_key": False,
            "auth_method": summary.get("source") or "api_key",
            "api_key_name": me.get("apiKeyName") or me.get("userEmail") or summary.get("email"),
            "models": model_ids[:12],
            "default_model": settings.cursor_discovery_model,
            "api_keys_url": summary.get("api_keys_url"),
            "message": "Cursor connected — Discovery can use AI planning and stuck-click recovery.",
        }
    except CursorAPIError as exc:
        return {
            "configured": True,
            "enabled": settings.discovery_cursor_advisor_enabled,
            "available": False,
            "connected": bool(api_key),
            "signed_in": signed_in,
            "needs_api_key": not bool(api_key),
            "auth_method": summary.get("source"),
            "api_keys_url": summary.get("api_keys_url"),
            "message": str(exc),
        }


async def apply_cursor_discovery_plan(
    intent: DiscoveryIntent,
    base_url: str,
    emit,
) -> DiscoveryIntent:
    """Optional: ask Cursor to refine menu targets and navigation strategy before Playwright runs."""
    if not settings.discovery_cursor_advisor_enabled:
        return intent
    client = await get_cursor_client_async()
    if not client:
        return intent

    raw_text = (intent.raw or intent.goals or "").strip()
    user_parsed = extract_menu_list_targets(raw_text)
    if len(user_parsed) >= 2:
        await emit({
            "type": "status",
            "message": f"Cursor advisor — using your menu list ({len(user_parsed)} items); recovery enabled if a click fails",
            "url": base_url,
        })
        return intent

    await emit({
        "type": "status",
        "message": "Cursor advisor — planning navigation from your prompt…",
        "url": base_url,
    })

    requirements = intent.raw or intent.goals or ""
    prompt = f"""You are a QA discovery planner for live browser testing (Playwright).

Website base URL: {base_url}

User instructions:
{requirements}

Respond with ONLY valid JSON (no markdown, no code fences):
{{
  "menu_targets": ["exact menu labels to click in order"],
  "popup_actions": ["short popup dismiss actions if needed"],
  "navigation_strategy": "sticky_header or return_home_between_menus",
  "notes": "one sentence"
}}

Rules:
- menu_targets must be real top-navigation labels on the site, not URLs.
- If the user already listed menus, preserve their order and spelling.
- For e-commerce mega-menus (e.g. Flipkart), use navigation_strategy sticky_header when menus stay in the header on category pages.
"""

    try:
        raw = await client.run_prompt_no_repo(
            prompt,
            model=settings.cursor_discovery_model or None,
            max_wait_sec=float(settings.cursor_discovery_plan_timeout_sec),
        )
        data = _extract_json_object(raw)
        if not data:
            await emit({
                "type": "warning",
                "message": "Cursor advisor returned non-JSON — using built-in prompt parsing",
                "url": base_url,
            })
            return intent

        menu_targets = data.get("menu_targets") or []
        if isinstance(menu_targets, list):
            cleaned = [str(t).strip() for t in menu_targets if str(t).strip()]
            if len(cleaned) >= 2:
                intent.explicit_targets = cleaned
                intent.menu_list_navigation = True
                intent.strict_follow = True
                intent.broad_exploration = False

        notes = str(data.get("notes") or "").strip()
        strategy = str(data.get("navigation_strategy") or "").strip()
        summary_bits = []
        if strategy:
            summary_bits.append(f"strategy: {strategy}")
        if notes:
            summary_bits.append(notes)
        if summary_bits:
            intent.summary = f"cursor — {'; '.join(summary_bits)}"

        await emit({
            "type": "status",
            "message": (
                f"Cursor advisor — {len(intent.explicit_targets)} menu target(s) planned"
                + (f" ({strategy})" if strategy else "")
            ),
            "url": base_url,
        })
    except CursorAPIError as exc:
        logger.warning("cursor_discovery_plan_failed", error=str(exc))
        await emit({
            "type": "warning",
            "message": f"Cursor advisor unavailable — continuing with built-in agent ({exc})",
            "url": base_url,
        })
    except Exception as exc:
        logger.warning("cursor_discovery_plan_error", error=str(exc))
        await emit({
            "type": "warning",
            "message": f"Cursor advisor error — continuing with built-in agent",
            "url": base_url,
        })

    return intent


async def suggest_menu_click_aliases(
    target: str,
    visible_links: list[str],
    base_url: str,
) -> list[str]:
    """When Playwright cannot find a menu label, ask Cursor for alternate click text."""
    if not settings.discovery_cursor_advisor_enabled:
        return []
    client = await get_cursor_client_async()
    if not client or not visible_links:
        return []

    sample = visible_links[:40]
    prompt = f"""You help QA automation click the correct menu on a live website.

Base URL: {base_url}
Target menu from test plan: {target}

Visible navigation link texts on the page:
{json.dumps(sample, ensure_ascii=False)}

Respond with ONLY JSON:
{{"aliases": ["best matching label(s) to click"], "hint": "hover mega-menu or direct click"}}

Pick aliases that appear in the visible list or are obvious shortenings (e.g. "Toys, Baby & Kids" -> "Baby & Kids").
"""

    try:
        raw = await client.run_prompt_no_repo(
            prompt,
            model=settings.cursor_discovery_model or None,
            max_wait_sec=min(60.0, float(settings.cursor_discovery_plan_timeout_sec)),
        )
        data = _extract_json_object(raw) or {}
        aliases = data.get("aliases") or []
        out: list[str] = []
        seen: set[str] = set()
        for item in aliases:
            label = str(item).strip()
            key = label.lower()
            if label and key not in seen and key != target.lower():
                seen.add(key)
                out.append(label)
        return out[:4]
    except Exception as exc:
        logger.debug("cursor_menu_alias_failed", target=target, error=str(exc))
        return []


"""LLM Discovery advisor — Ollama-first open-source GPT for understanding automation steps."""

from __future__ import annotations

import json
import re
from typing import Any

import httpx

from app.config import settings
from app.runners.discovery_prompt import DiscoveryIntent, PlannedFlow, PlannedStep, extract_menu_list_targets
from app.services.test_steps import steps_for_storage

try:
    import structlog

    logger = structlog.get_logger()
except ImportError:
    import logging

    logger = logging.getLogger(__name__)

_SYSTEM = """You are a senior QA automation engineer helping Discovery build accurate Playwright test case(s).

Convert the user's instructions into precise browser automation steps.

CRITICAL RULES:
1. Product / shopping queries (e.g. "Samsung Galaxy", "iPhone 15", "Airpods") MUST be action "search" — NEVER a top-nav menu click.
2. "Click/select the second/random product in the search results" MUST be action "click" with interaction "result" and element "2" or "random" — NEVER search for the word "results".
3. "Go to Cart" MUST be action "click" with interaction "cart" — NEVER navigate to the homepage URL.
4. "Remove/Delete from cart" MUST be action "click" with interaction "cart_remove".
5. "Add to cart" / "Buy now" are normal click steps (element = button label).
6. "Change quantity to N" MUST be action "fill" with interaction "quantity", field "Quantity", value/element "N".
7. Every "Assert/Verify/…" line MUST be action "verify" with expected = that assertion text.
8. Dismiss login/location/cookie overlays as action "dismiss" with interaction "popup".
9. Keep the user's order. Do not invent extra smoke/link tests. Do not deviate from asked steps.
10. Prefer action values: navigate, dismiss, search, click, fill, verify.
11. For interaction use only when needed: popup, search, result, cart, cart_remove, menu, home, quantity.
12. If the user labeled multiple flows (Flow 1 / Scenario A / Test Case: …), return mode "multi_flow" with a "flows" array — one object per flow. Never merge distinct flows into one case.

Return ONLY valid JSON (no markdown):
{
  "mode": "as_written|multi_flow|menu_journey",
  "title": "short title (single flow)",
  "steps": [ /* used when mode is as_written */ ],
  "flows": [
    {
      "name": "Flow 1 title",
      "steps": [
        {
          "order": 1,
          "action": "navigate|dismiss|search|click|fill|verify",
          "description": "human readable step",
          "url": "optional absolute URL",
          "element": "optional click target or result index like 2",
          "field": "optional field name",
          "value": "optional search/fill value",
          "interaction": "optional popup|search|result|cart|cart_remove|menu|home|quantity",
          "expected": "optional"
        }
      ]
    }
  ],
  "menu_targets": [],
  "notes": "one sentence"
}

If the user listed only site menus (Fashion, Mobiles, …) and asked for a menu journey:
set "mode": "menu_journey", put labels in menu_targets, and leave steps empty or minimal.
"""


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


async def ollama_reachable() -> bool:
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            r = await client.get(f"{settings.ollama_base_url.rstrip('/')}/api/tags")
            return r.status_code == 200
    except Exception:
        return False


async def pick_discovery_llm() -> tuple[str, str] | None:
    """Prefer Ollama (open-source), then OpenAI, then Gemini."""
    from app.llm.router import get_llm_router

    requested = (settings.discovery_llm_provider or "").strip().lower()
    router = get_llm_router()
    available = {p["name"] for p in router.list_providers() if p.get("available")}

    order: list[str] = []
    if requested:
        order.append(requested)
    order.extend(["ollama", "openai", "gemini", "anthropic"])

    seen: set[str] = set()
    for name in order:
        if name in seen:
            continue
        seen.add(name)
        if name not in available and name != "ollama":
            continue
        if name == "ollama":
            if not await ollama_reachable():
                continue
            model = (settings.discovery_llm_model or settings.ollama_model or "llama3.2").strip()
            return "ollama", model
        if name == "openai" and name in available:
            model = (settings.discovery_llm_model or "gpt-4o-mini").strip()
            return "openai", model
        if name == "gemini" and name in available:
            model = (settings.discovery_llm_model or "gemini-2.0-flash").strip()
            return "gemini", model
        if name == "anthropic" and name in available:
            model = (settings.discovery_llm_model or "claude-3-5-haiku-20241022").strip()
            return "anthropic", model
    return None


def _row_to_planned(order: int, row: dict) -> PlannedStep:
    action = str(row.get("action") or "").strip().lower()
    desc = str(row.get("description") or "").strip()
    interaction = str(row.get("interaction") or "").strip().lower() or None
    element = row.get("element")
    element_s = str(element).strip() if element is not None else None
    field = row.get("field")
    field_s = str(field).strip() if field else None
    value = row.get("value")
    value_s = str(value).strip() if value else None
    url = row.get("url")
    url_s = str(url).strip() if url else None
    expected = row.get("expected")
    expected_s = str(expected).strip() if expected else None

    if not desc:
        if action == "search" and value_s:
            desc = f'Search for "{value_s}"'
        elif action == "click" and element_s:
            desc = f"Click {element_s}"
        else:
            desc = action or f"Step {order}"

    # Harden common mistakes from smaller models
    lower = desc.lower()
    if action == "search" and value_s and value_s.lower() in {"results", "result", "search results"}:
        action = "click"
        interaction = "result"
        element_s = element_s if element_s and element_s.isdigit() else "2"
        desc = f"Click the {'second' if element_s == '2' else element_s} product in the search results"
        value_s = None
        field_s = None
    if "search results" in lower and action == "search":
        action = "click"
        interaction = "result"
        element_s = element_s if element_s and element_s.isdigit() else "2"
        desc = f"Click the {'second' if element_s == '2' else element_s} product in the search results"
    if re.search(r"\bgo to cart\b", lower) and action == "navigate":
        action = "click"
        interaction = "cart"
        element_s = "Cart"
        desc = "Go to Cart"
        url_s = None

    if action == "search" and value_s and "search for" not in lower:
        desc = f'Search for "{value_s}"'
        interaction = interaction or "search"
        field_s = field_s or "Search"

    return PlannedStep(
        order=order,
        description=desc,
        action=action or "click",
        element=element_s,
        url=url_s,
        field=field_s,
        value=value_s,
        expected=expected_s,
        interaction=interaction,
    )


def _planned_from_llm_steps(raw_steps: list, base_url: str) -> list[PlannedStep]:
    planned: list[PlannedStep] = []
    for i, row in enumerate(raw_steps, start=1):
        if not isinstance(row, dict):
            text = str(row).strip()
            if text:
                planned.append(PlannedStep(order=i, description=text, action="click"))
            continue
        planned.append(_row_to_planned(i, row))

    # Normalize via storage pipeline (rewrites Search for "results", Go to Cart, etc.)
    stored = steps_for_storage([
        {
            "order": s.order,
            "action": s.action,
            "description": s.description,
            **({"url": s.url} if s.url else {}),
            **({"element": s.element} if s.element else {}),
            **({"field": s.field} if s.field else {}),
            **({"interaction": s.interaction} if s.interaction else {}),
            **({"expected": s.expected} if s.expected else {}),
        }
        for s in planned
    ])

    # Ensure navigate entry when base URL known
    if base_url and stored and (stored[0].get("action") or "").lower() != "navigate":
        if "http" not in (stored[0].get("description") or "").lower():
            stored = steps_for_storage([
                {
                    "order": 1,
                    "action": "navigate",
                    "description": f"Navigate to {base_url}",
                    "url": base_url,
                    "expected": "Application loads without errors",
                },
                *stored,
            ])

    out: list[PlannedStep] = []
    for i, row in enumerate(stored, start=1):
        out.append(
            PlannedStep(
                order=i,
                description=row.get("description") or f"Step {i}",
                action=row.get("action") or "",
                element=row.get("element"),
                url=row.get("url"),
                field=row.get("field"),
                expected=row.get("expected"),
                interaction=row.get("interaction"),
                value=None,
            )
        )
    return out


def _should_invoke(intent: DiscoveryIntent) -> bool:
    raw = (intent.raw or intent.goals or "").strip()
    if len(raw) < 12:
        return False
    # Always help for as-written / numbered automation, or free-form e2e instructions
    if intent.planned_steps:
        return True
    if re.search(r"(?i)\b(?:automation\s+steps?|steps?\s*:|search\s+for|add\s+to\s+cart|go\s+to\s+cart)\b", raw):
        return True
    if re.search(r"(?m)^\s*\d+[\.\)]\s+\S+", raw):
        return True
    if intent.menu_list_navigation or intent.form_fields or intent.wants_form_submit:
        return True
    # Free-form goal text — still ask LLM to structure it
    return len(raw) >= 40


async def apply_llm_discovery_plan(
    intent: DiscoveryIntent,
    base_url: str,
    emit,
) -> DiscoveryIntent:
    """
    Use open-source GPT (Ollama) or cloud LLM to understand the Discovery prompt and
    replace brittle rule-parsed steps with correct automation steps.
    """
    if not settings.discovery_llm_advisor_enabled:
        return intent
    if not _should_invoke(intent):
        return intent

    picked = await pick_discovery_llm()
    if not picked:
        await emit({
            "type": "warning",
            "message": (
                "LLM advisor unavailable — start Ollama (ollama serve + ollama pull llama3.2) "
                "or set OPENAI_API_KEY / GOOGLE_API_KEY. Continuing with built-in parser."
            ),
            "url": base_url,
        })
        return intent

    provider_name, model = picked
    await emit({
        "type": "status",
        "message": f"LLM advisor ({provider_name}/{model}) — understanding your automation steps…",
        "url": base_url,
    })

    requirements = (intent.raw or intent.goals or "").strip()
    prior = ""
    if intent.planned_steps:
        prior = "\nRule-parser draft (may be WRONG — correct it):\n" + "\n".join(
            f"{s.order}. [{s.action}/{s.interaction or '-'}] {s.description}"
            for s in intent.planned_steps
        )

    user = f"""Website base URL: {base_url}

User Discovery prompt:
{requirements}
{prior}

Produce the corrected JSON test plan now.
"""

    try:
        from app.llm.base import LLMMessage, MessageRole
        from app.llm.router import get_llm_router

        router = get_llm_router()
        resp = await router.complete(
            [
                LLMMessage(role=MessageRole.SYSTEM, content=_SYSTEM),
                LLMMessage(role=MessageRole.USER, content=user),
            ],
            provider=provider_name,
            model=model,
            temperature=0.1,
            max_tokens=2500,
        )
        data = _extract_json_object(resp.content)
        if not data:
            await emit({
                "type": "warning",
                "message": f"LLM advisor ({provider_name}) returned non-JSON — keeping built-in parse",
                "url": base_url,
            })
            return intent

        mode = str(data.get("mode") or "as_written").strip().lower()
        raw_steps = data.get("steps") or []
        raw_flows = data.get("flows") or []
        menu_targets = data.get("menu_targets") or []

        if mode in ("multi_flow", "multiflow") and isinstance(raw_flows, list) and len(raw_flows) >= 2:
            flows: list[PlannedFlow] = []
            for i, fl in enumerate(raw_flows, start=1):
                if not isinstance(fl, dict):
                    continue
                name = str(fl.get("name") or f"Flow {i}").strip()[:100]
                fl_steps = fl.get("steps") or []
                if not isinstance(fl_steps, list) or len(fl_steps) < 2:
                    continue
                flows.append(
                    PlannedFlow(
                        name=name,
                        steps=_planned_from_llm_steps(fl_steps, base_url),
                        order=i,
                    )
                )
            if len(flows) >= 2:
                intent.planned_flows = flows
                intent.planned_steps = list(flows[0].steps)
                intent.case_mode = "as_written"
                intent.strict_follow = True
                intent.broad_exploration = False
                intent.split_test_cases = True
                intent.menu_list_navigation = False
                intent.summary = (
                    f"LLM ({provider_name}) — {len(flows)} flows / "
                    f"{sum(len(f.steps) for f in flows)} steps"
                )
                await emit({
                    "type": "status",
                    "message": (
                        f"LLM advisor — built {len(flows)} flows via {provider_name}/{model}"
                    ),
                    "url": base_url,
                })
                return intent

        if isinstance(raw_steps, list) and len(raw_steps) >= 2 and mode != "menu_journey":
            intent.planned_steps = _planned_from_llm_steps(raw_steps, base_url)
            intent.planned_flows = []
            intent.case_mode = "as_written"
            intent.strict_follow = True
            intent.broad_exploration = False
            intent.split_test_cases = False
            intent.menu_list_navigation = False
            title = str(data.get("title") or "").strip()
            intent.summary = (
                f"LLM ({provider_name}) — {len(intent.planned_steps)} automation steps"
                + (f" — {title}" if title else "")
            )
            await emit({
                "type": "status",
                "message": (
                    f"LLM advisor — built {len(intent.planned_steps)} steps via {provider_name}/{model}"
                ),
                "url": base_url,
            })
            return intent

        if isinstance(menu_targets, list):
            cleaned = [str(t).strip() for t in menu_targets if str(t).strip()]
            # Prefer user-authored menu list spelling when present
            user_menus = extract_menu_list_targets(requirements)
            if len(user_menus) >= 2:
                cleaned = user_menus
            if len(cleaned) >= 2:
                intent.explicit_targets = cleaned
                intent.menu_list_navigation = True
                intent.planned_steps = []
                intent.case_mode = "single_journey"
                intent.strict_follow = True
                intent.broad_exploration = False
                intent.summary = f"LLM ({provider_name}) — menu journey ({len(cleaned)} targets)"
                await emit({
                    "type": "status",
                    "message": f"LLM advisor — menu journey with {len(cleaned)} targets via {provider_name}",
                    "url": base_url,
                })
                return intent

        await emit({
            "type": "warning",
            "message": "LLM advisor response lacked usable steps — keeping built-in parse",
            "url": base_url,
        })
    except Exception as exc:
        logger.warning("llm_discovery_plan_failed", error=str(exc), provider=provider_name)
        await emit({
            "type": "warning",
            "message": f"LLM advisor error ({provider_name}): {str(exc)[:160]} — continuing with built-in parser",
            "url": base_url,
        })

    return intent


async def suggest_click_aliases_llm(
    target: str,
    visible_links: list[str],
    base_url: str,
) -> list[str]:
    """Open-source GPT fallback when a menu/label click fails."""
    if not settings.discovery_llm_advisor_enabled:
        return []
    picked = await pick_discovery_llm()
    if not picked or not visible_links:
        return []
    provider_name, model = picked
    sample = visible_links[:40]
    prompt = f"""Pick the best matching visible link text(s) for the target "{target}" on {base_url}.

Visible labels:
{json.dumps(sample, ensure_ascii=False)}

Return ONLY JSON: {{"aliases": ["label1", "label2"]}}
Aliases must be from the visible list (or obvious shortenings).
"""
    try:
        from app.llm.base import LLMMessage, MessageRole
        from app.llm.router import get_llm_router

        router = get_llm_router()
        resp = await router.complete(
            [
                LLMMessage(role=MessageRole.SYSTEM, content="You help Playwright click the correct UI label."),
                LLMMessage(role=MessageRole.USER, content=prompt),
            ],
            provider=provider_name,
            model=model,
            temperature=0.1,
            max_tokens=400,
        )
        data = _extract_json_object(resp.content) or {}
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
        logger.warning("llm_alias_failed", error=str(exc))
        return []


async def get_llm_discovery_status() -> dict[str, Any]:
    ollama_ok = await ollama_reachable()
    picked = await pick_discovery_llm()
    return {
        "enabled": settings.discovery_llm_advisor_enabled,
        "ollama_url": settings.ollama_base_url,
        "ollama_reachable": ollama_ok,
        "ollama_model": settings.ollama_model,
        "active_provider": picked[0] if picked else None,
        "active_model": picked[1] if picked else None,
        "message": (
            f"LLM advisor ready — {picked[0]}/{picked[1]}"
            if picked
            else "Start Ollama (ollama serve && ollama pull llama3.2) or set OPENAI_API_KEY / GOOGLE_API_KEY"
        ),
    }

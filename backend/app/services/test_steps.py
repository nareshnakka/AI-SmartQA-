"""Normalize test case step ordering for discovery import and execution."""

from __future__ import annotations

import re


def _looks_like_product_query(text: str) -> bool:
    """Prefer shared Discovery classifier; keep a local fallback for import safety."""
    try:
        from app.runners.discovery_prompt import _is_search_or_product_query

        return _is_search_or_product_query(text)
    except Exception:
        t = (text or "").strip()
        if not t:
            return False
        lower = t.lower()
        if re.search(
            r"\b(?:iphone|ipad|airpods|macbook|galaxy|pixel|oneplus|laptop|headphones?)\b",
            lower,
        ):
            return True
        if re.search(r"\b\d+\s?(?:gb|tb|pro|max|plus|ultra)\b", lower):
            return True
        if re.search(r"[a-z].*\d|\d.*[a-z]", lower) and len(t.split()) <= 6:
            return True
        return False


def _rewrite_misclassified_step(item: dict) -> dict:
    """
    Fix legacy Discovery mistakes: product/search queries tagged as menu clicks.
    Example: Click 'iPhone 15' in the main navigation menu → Search for "iPhone 15"
    Also: Search for "results" (mis-parsed selection) → Click product in search results
    Also: Navigate "Go to Cart" → Cart click (not homepage navigate)
    """
    desc = (item.get("description") or "").strip()
    element = (item.get("element") or "").strip()
    interaction = (item.get("interaction") or "").lower()
    action = (item.get("action") or "").lower()
    lower = desc.lower()

    label = element
    if not label:
        m = re.search(r"['\"]([^'\"]{2,80})['\"]", desc)
        if m:
            label = m.group(1).strip()
    label = re.sub(r"\s+in the main navigation menu$", "", label, flags=re.I).strip()

    # Mis-parsed: "Click the second phone in the search results" → Search for "results"
    if (action == "search" or "search for" in lower) and label.lower() in {
        "results",
        "result",
        "search results",
        "the results",
    }:
        idx = 2  # prompts that hit this bug almost always meant the second result
        for word, n in (
            ("fifth", 5),
            ("5th", 5),
            ("fourth", 4),
            ("4th", 4),
            ("third", 3),
            ("3rd", 3),
            ("second", 2),
            ("2nd", 2),
            ("first", 1),
            ("1st", 1),
        ):
            if re.search(rf"\b{word}\b", lower):
                idx = n
                break
        ordinal = {1: "first", 2: "second", 3: "third", 4: "fourth", 5: "fifth"}.get(idx, f"{idx}th")
        return {
            "order": item.get("order", 0),
            "action": "click",
            "interaction": "result",
            "element": str(idx),
            "description": f"Click the {ordinal} product in the search results",
            **({"expected": item["expected"]} if item.get("expected") else {}),
            **({"disabled": True} if item.get("disabled") else {}),
        }

    # "Go to Cart" wrongly stored as navigate → homepage
    if re.search(r"\b(?:go\s+to|open|view)\s+(?:the\s+)?cart\b|^go to cart$", lower) or (
        action == "navigate" and re.search(r"\bcart\b", lower) and not re.search(r"\badd\s+to\s+cart\b", lower)
    ):
        return {
            "order": item.get("order", 0),
            "action": "click",
            "interaction": "cart",
            "element": "Cart",
            "description": "Go to Cart",
            **({"expected": item["expected"]} if item.get("expected") else {}),
            **({"disabled": True} if item.get("disabled") else {}),
        }

    if re.search(r"\bremove\b.+\bcart\b|\bdelete\b.+\bcart\b", lower):
        return {
            "order": item.get("order", 0),
            "action": "click",
            "interaction": "cart_remove",
            "element": label or "Remove",
            "description": desc if desc else "Remove item from cart",
            **({"expected": item["expected"]} if item.get("expected") else {}),
            **({"disabled": True} if item.get("disabled") else {}),
        }

    is_menuish = interaction == "menu" or "navigation menu" in lower or (
        action in ("click", "navigate") and "menu" in lower and bool(label)
    )
    if is_menuish and label and _looks_like_product_query(label):
        return {
            **{k: v for k, v in item.items() if k != "element"},
            "action": "search",
            "interaction": "search",
            "field": "Search",
            "description": f'Search for "{label}"',
        }

    if action == "search" or "search for" in lower:
        out = {**item, "action": "search", "interaction": item.get("interaction") or "search"}
        if label and not out.get("field"):
            out["field"] = "Search"
            out["description"] = out.get("description") or f'Search for "{label}"'
        if (out.get("interaction") or "").lower() == "menu":
            out["interaction"] = "search"
        return {k: v for k, v in out.items() if v is not None}

    return item


def _reclassify_from_description(item: dict) -> dict:
    """Re-parse step text so Discovery display matches the prompt even if action was wrong."""
    desc = (item.get("description") or "").strip()
    if not desc:
        return item
    try:
        from app.runners.discovery_prompt import _classify_planned_step
    except Exception:
        return item

    ps = _classify_planned_step(int(item.get("order") or 0), desc)
    if not ps.action:
        return item

    out = {**item}
    out["action"] = ps.action
    out["description"] = ps.description or desc
    if ps.interaction:
        out["interaction"] = ps.interaction
    if ps.element:
        out["element"] = ps.element
    if ps.field:
        out["field"] = ps.field
    if ps.value:
        out["value"] = ps.value
    if ps.url:
        out["url"] = ps.url
    elif (ps.interaction or "") in ("cart", "cart_remove", "result", "popup", "search", "quantity"):
        out.pop("url", None)
    if (ps.interaction or "") in ("cart", "cart_remove", "result"):
        out.pop("field", None)
    if ps.expected:
        out["expected"] = ps.expected
    return out


def normalize_test_steps(steps: list | None) -> list[dict]:
    """
    Sort steps by explicit order (when present) and re-number 1..n.
    Ensures discovery imports and IDE flows always run first → last.
    Also rewrites mis-tagged product menu clicks into search steps.
    """
    if not steps:
        return []

    parsed: list[dict] = []
    for i, raw in enumerate(steps):
        if isinstance(raw, dict):
            desc = (raw.get("description") or raw.get("text") or "").strip()
            if not desc:
                desc = str(raw).strip()
            order_val = raw.get("order")
            try:
                order_num = int(order_val) if order_val is not None else 0
            except (TypeError, ValueError):
                order_num = 0
            item: dict = {
                "order": order_num,
                "description": desc,
            }
            for key in ("action", "url", "element", "expected", "field", "target", "interaction"):
                if raw.get(key):
                    item[key] = raw[key]
            if raw.get("disabled"):
                item["disabled"] = True
            item = _rewrite_misclassified_step(item)
            item = _reclassify_from_description(item)
            parsed.append(item)
        else:
            text = str(raw).strip()
            if text:
                item = _rewrite_misclassified_step({"order": 0, "description": text})
                item = _reclassify_from_description(item)
                parsed.append(item)

    if not parsed:
        return []

    has_explicit_order = any(p.get("order", 0) > 0 for p in parsed)
    if has_explicit_order:
        parsed.sort(key=lambda p: (p.get("order") or 9999, p.get("description", "")))

    for i, item in enumerate(parsed):
        item["order"] = i + 1

    return parsed


def steps_for_storage(steps: list | None) -> list[dict]:
    """Structured steps persisted on test cases (order, description, action, url, field, element)."""
    stored: list[dict] = []
    for item in normalize_test_steps(steps):
        row: dict = {"order": item["order"], "description": item["description"]}
        for key in ("action", "url", "field", "element", "target", "expected", "interaction"):
            if item.get(key):
                row[key] = item[key]
        if item.get("disabled"):
            row["disabled"] = True
        stored.append(row)
    return stored

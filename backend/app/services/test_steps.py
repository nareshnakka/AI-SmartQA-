"""Normalize test case step ordering for discovery import and execution."""

from __future__ import annotations


def normalize_test_steps(steps: list | None) -> list[dict]:
    """
    Sort steps by explicit order (when present) and re-number 1..n.
    Ensures discovery imports and IDE flows always run first → last.
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
            parsed.append(item)
        else:
            text = str(raw).strip()
            if text:
                parsed.append({"order": 0, "description": text})

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

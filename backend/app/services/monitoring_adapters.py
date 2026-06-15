"""Normalize Datadog and Sentry webhook payloads into QEOS monitoring events."""

from typing import Any


def parse_datadog(payload: dict[str, Any]) -> list[dict]:
    """Parse Datadog monitor alert or event webhook."""
    events: list[dict] = []

    if "alert_type" in payload or "body" in payload:
        events.append({
            "event_type": payload.get("alert_type", "alert"),
            "title": _first_str(payload, "title", "body", "event_title") or "Datadog alert",
            "severity": _datadog_severity(payload.get("alert_type", "")),
            "source": "datadog",
            "payload": payload,
        })
        return events

    if "events" in payload and isinstance(payload["events"], list):
        for item in payload["events"]:
            events.append({
                "event_type": item.get("alert_type", "event"),
                "title": _first_str(item, "title", "text", "msg_title") or "Datadog event",
                "severity": _datadog_severity(item.get("alert_type", "")),
                "source": "datadog",
                "payload": item,
            })
        return events

    events.append({
        "event_type": "webhook",
        "title": _first_str(payload, "title", "message", "text") or "Datadog webhook",
        "severity": "warning",
        "source": "datadog",
        "payload": payload,
    })
    return events


def parse_sentry(payload: dict[str, Any]) -> list[dict]:
    """Parse Sentry issue or event webhook."""
    events: list[dict] = []

    data = payload.get("data") or payload
    issue = data.get("issue") or data.get("event") or data

    title = _first_str(issue, "title", "message", "culprit") or _first_str(payload, "message") or "Sentry issue"
    level = (issue.get("level") or payload.get("level") or "error").lower()

    events.append({
        "event_type": payload.get("action") or issue.get("type") or "issue",
        "title": title[:500],
        "severity": _sentry_severity(level),
        "source": "sentry",
        "payload": {
            "project": issue.get("project") or data.get("project"),
            "url": issue.get("permalink") or issue.get("web_url"),
            "tags": issue.get("tags"),
            "raw_action": payload.get("action"),
        },
    })
    return events


def _datadog_severity(alert_type: str) -> str:
    mapping = {
        "error": "error",
        "warning": "warning",
        "info": "info",
        "success": "info",
        "user_update": "info",
        "recommendation": "info",
    }
    return mapping.get(str(alert_type).lower(), "warning")


def _sentry_severity(level: str) -> str:
    if level in ("fatal", "error"):
        return "error"
    if level in ("warning", "warn"):
        return "warning"
    return "info"


def _first_str(data: dict, *keys: str) -> str | None:
    for key in keys:
        val = data.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
    return None

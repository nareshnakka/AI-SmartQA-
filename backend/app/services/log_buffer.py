"""In-memory ring buffer for recent application log lines (for bug reports)."""

from __future__ import annotations

import threading
from collections import deque
from datetime import datetime, timezone
from typing import Any

_LOCK = threading.Lock()
_BUFFER: deque[str] = deque(maxlen=500)


def append_log_line(line: str) -> None:
    text = (line or "").strip()
    if not text:
        return
    with _LOCK:
        _BUFFER.append(text)


def recent_logs(limit: int = 200) -> list[str]:
    with _LOCK:
        items = list(_BUFFER)
    if limit <= 0:
        return items
    return items[-limit:]


def recent_logs_text(limit: int = 200) -> str:
    lines = recent_logs(limit=limit)
    if not lines:
        return "(No recent application log lines captured yet.)\n"
    return "\n".join(lines) + "\n"


def clear_logs() -> None:
    with _LOCK:
        _BUFFER.clear()


def structlog_buffer_processor(logger: Any, method_name: str, event_dict: dict) -> dict:
    """structlog processor that mirrors JSON events into the ring buffer."""
    try:
        ts = event_dict.get("timestamp") or datetime.now(timezone.utc).isoformat()
        event = event_dict.get("event", method_name)
        parts = [f"{ts} [{method_name}] {event}"]
        for key, value in event_dict.items():
            if key in {"event", "timestamp"}:
                continue
            parts.append(f"{key}={value!r}")
        append_log_line(" ".join(parts))
    except Exception:
        pass
    return event_dict

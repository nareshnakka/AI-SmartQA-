"""Extract human-readable Playwright failure messages from runner output."""

from __future__ import annotations

import re


_ANSI = re.compile(r"\x1b\[[0-9;]*m")
_NODE_WARN = re.compile(
    r"^\(node:\d+\) Warning:.*$|^\(Use `node --trace-warnings.*$",
    re.MULTILINE,
)


def strip_ansi(text: str) -> str:
    return _ANSI.sub("", text or "").strip()


def strip_node_warnings(text: str) -> str:
    lines = []
    for line in (text or "").splitlines():
        if _NODE_WARN.match(line.strip()):
            continue
        if "NO_COLOR" in line and "FORCE_COLOR" in line:
            continue
        lines.append(line)
    return "\n".join(lines).strip()


def extract_playwright_failure(stdout: str, stderr: str, parsed: list[dict] | None = None) -> str | None:
    """Prefer structured result errors, then Playwright 'Error:' blocks in stdout."""
    if parsed:
        for item in parsed:
            err = item.get("error")
            if err and str(err).strip():
                cleaned = strip_node_warnings(strip_ansi(str(err)))
                if cleaned and not cleaned.startswith("(node:"):
                    return cleaned[:800]

    combined = strip_node_warnings(strip_ansi(stdout or ""))
    blocks: list[str] = []
    for line in combined.splitlines():
        if line.strip().startswith("Error:"):
            blocks.append(line.strip())
        elif blocks and line.strip() and not line.strip().startswith("attachment"):
            if line.startswith(" ") or line.startswith("at ") or "Call log" in line or "Expected" in line or "Received" in line:
                blocks.append(line.rstrip())
            elif len(blocks) < 12:
                blocks.append(line.rstrip())
            else:
                break
    if blocks:
        return "\n".join(blocks)[:800]

    stderr_clean = strip_node_warnings(strip_ansi(stderr or ""))
    if stderr_clean and not stderr_clean.startswith("(node:"):
        return stderr_clean[:800]

    stdout_tail = combined[-800:].strip() if combined else None
    return stdout_tail or None

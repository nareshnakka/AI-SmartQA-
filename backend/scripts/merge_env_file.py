"""Merge environment files — download new keys from repo without wiping local secrets."""

from __future__ import annotations

import argparse
import re
from pathlib import Path


_LINE_KEY = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)\s*=")


def _parse_env(text: str) -> dict[str, str]:
    """Return KEY -> raw value (no surrounding quotes stripped beyond trim)."""
    out: dict[str, str] = {}
    for line in text.splitlines():
        raw = line.strip()
        if not raw or raw.startswith("#"):
            continue
        m = _LINE_KEY.match(raw)
        if not m:
            continue
        key = m.group(1)
        val = raw.split("=", 1)[1].strip()
        if len(val) >= 2 and val[0] == val[-1] and val[0] in "\"'":
            val = val[1:-1]
        out[key] = val
    return out


def _is_empty(value: str | None) -> bool:
    return value is None or str(value).strip() == ""


def merge_env_texts(base_text: str, incoming_text: str) -> tuple[str, list[str]]:
    """
    Merge incoming (repo) keys into base (local).

    - Missing keys from incoming are appended.
    - Empty local values are filled from incoming when incoming is non-empty.
    - Non-empty local values are never overwritten (secrets / machine overrides win).
    """
    base_map = _parse_env(base_text)
    incoming_map = _parse_env(incoming_text)
    added: list[str] = []
    filled: list[str] = []

    lines = base_text.splitlines()
    # Track which keys already appear in base file
    present = set(base_map.keys())

    # Fill empty local values in-place where possible
    new_lines: list[str] = []
    for line in lines:
        stripped = line.strip()
        m = _LINE_KEY.match(stripped) if stripped and not stripped.startswith("#") else None
        if not m:
            new_lines.append(line)
            continue
        key = m.group(1)
        local_val = base_map.get(key, "")
        incoming_val = incoming_map.get(key)
        if _is_empty(local_val) and incoming_val is not None and not _is_empty(incoming_val):
            new_lines.append(f"{key}={incoming_val}")
            filled.append(key)
        else:
            new_lines.append(line)

    # Append keys that only exist on incoming
    to_append = [k for k in incoming_map.keys() if k not in present]
    if to_append:
        if new_lines and new_lines[-1].strip():
            new_lines.append("")
        new_lines.append("# --- merged from repo / .env.example update ---")
        for key in to_append:
            new_lines.append(f"{key}={incoming_map[key]}")
            added.append(key)

    result = "\n".join(new_lines)
    if result and not result.endswith("\n"):
        result += "\n"
    return result, added + [f"{k} (filled)" for k in filled]


def merge_env_files(base_path: Path, incoming_path: Path) -> dict:
    if not incoming_path.is_file():
        return {"changed": False, "message": f"incoming missing: {incoming_path}", "keys": []}
    incoming_text = incoming_path.read_text(encoding="utf-8", errors="replace")
    if not base_path.is_file():
        base_path.parent.mkdir(parents=True, exist_ok=True)
        base_path.write_text(incoming_text, encoding="utf-8")
        keys = list(_parse_env(incoming_text).keys())
        return {"changed": True, "message": "created from incoming", "keys": keys}

    base_text = base_path.read_text(encoding="utf-8", errors="replace")
    merged, keys = merge_env_texts(base_text, incoming_text)
    if merged == base_text:
        return {"changed": False, "message": "already up to date", "keys": []}
    base_path.write_text(merged, encoding="utf-8")
    return {"changed": True, "message": "merged", "keys": keys}


def main() -> int:
    parser = argparse.ArgumentParser(description="Merge env file keys from repo into local .env")
    parser.add_argument("base", help="Local .env path (destination)")
    parser.add_argument("incoming", help="Repo / example .env path (source of new keys)")
    args = parser.parse_args()
    result = merge_env_files(Path(args.base), Path(args.incoming))
    print(result["message"], end="")
    if result["keys"]:
        print(f" — {', '.join(result['keys'][:20])}")
    else:
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

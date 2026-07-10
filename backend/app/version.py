"""Single source of truth for QEOS app version (see /version.json)."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path


def _version_file() -> Path:
    try:
        from app.services.app_updates import find_repo_root

        root = find_repo_root()
        if root:
            return root / "version.json"
    except Exception:
        pass
    return Path(__file__).resolve().parent.parent.parent / "version.json"


@lru_cache(maxsize=1)
def load_version() -> dict:
    path = _version_file()
    if not path.is_file():
        return {"major": 2, "minor": 0, "build": 1, "tagline": "Quality Engineering OS"}
    return json.loads(path.read_text(encoding="utf-8"))


def feature_version() -> str:
    data = load_version()
    return f"{int(data['major'])}.{int(data['minor'])}"


def version_label() -> str:
    data = load_version()
    major = int(data["major"])
    minor = int(data["minor"])
    build = int(data["build"])
    return f"V{major}.{minor}-Build {build}"


def version_info() -> dict:
    data = load_version()
    major = int(data["major"])
    minor = int(data["minor"])
    build = int(data["build"])
    return {
        "major": major,
        "minor": minor,
        "build": build,
        "feature_version": f"{major}.{minor}",
        "label": f"V{major}.{minor}-Build {build}",
        "tagline": str(data.get("tagline") or "Quality Engineering OS"),
    }

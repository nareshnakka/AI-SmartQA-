"""Project test case naming pattern configuration."""

import re
import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ProjectModel

CATEGORIES = ("functional", "automation", "performance", "security")

TOKEN_HELP = {
    "{PROJ5}": "First 5 chars of project name",
    "{ENV5}": "First 5 chars of environment name",
    "{MOD5}": "First 5 chars of module name",
    "{SEQ5}": "Sequence number (zero-padded, width from seq_digits)",
    "{PROJ}": "Project name prefix (5 chars, alias)",
    "{ENV}": "Environment name prefix (5 chars, alias)",
    "{MOD}": "Module name prefix (5 chars, alias)",
    "{SEQ}": "Sequence number (alias of SEQ5)",
}

DEFAULT_PATTERNS: dict[str, dict[str, Any]] = {
    "functional": {"pattern": "{PROJ5}_{ENV5}_{MOD5}_FTC{SEQ5}", "seq_digits": 5},
    "automation": {"pattern": "{PROJ5}_{ENV5}_{MOD5}_AP_TC{SEQ5}", "seq_digits": 5},
    "performance": {"pattern": "{PROJ5}_{ENV5}_{MOD5}_PJ_TC{SEQ5}", "seq_digits": 5},
    "security": {"pattern": "{PROJ5}_{ENV5}_{MOD5}_SEC_TC{SEQ5}", "seq_digits": 5},
}

CASE_TYPE_TO_CATEGORY = {
    "functional": "functional",
    "playwright": "automation",
    "automation_playwright": "automation",
    "automation": "automation",
    "cypress": "automation",
    "selenium": "automation",
    "webdriverio": "automation",
    "jmeter": "performance",
    "performance_jmeter": "performance",
    "performance": "performance",
    "k6": "performance",
    "security": "security",
}

_ALLOWED_TOKEN_RE = re.compile(
    r"\{(?:PROJ5|ENV5|MOD5|SEQ5|PROJ|ENV|MOD|SEQ)\}"
)


def name_prefix(raw: str, length: int = 5) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9]", "", raw or "")
    if not cleaned:
        cleaned = "PROJ"
    prefix = cleaned[:length].upper()
    return prefix.ljust(length, "X")[:length]


def validate_pattern(pattern: str) -> None:
    if not pattern or not pattern.strip():
        raise ValueError("Pattern cannot be empty")
    if "{SEQ5}" not in pattern and "{SEQ}" not in pattern:
        raise ValueError("Pattern must include {SEQ5} or {SEQ} for the sequence number")
    remainder = _ALLOWED_TOKEN_RE.sub("", pattern)
    if re.search(r"[{}]", remainder):
        raise ValueError("Unknown token in pattern — use PROJ5, ENV5, MOD5, SEQ5 only")


def merge_patterns(stored: dict | None) -> dict[str, dict[str, Any]]:
    merged = {cat: dict(DEFAULT_PATTERNS[cat]) for cat in CATEGORIES}
    if not stored:
        return merged
    for cat in CATEGORIES:
        if cat in stored and isinstance(stored[cat], dict):
            if stored[cat].get("pattern"):
                merged[cat]["pattern"] = str(stored[cat]["pattern"])
            if stored[cat].get("seq_digits") is not None:
                merged[cat]["seq_digits"] = int(stored[cat]["seq_digits"])
    return merged


def category_for_case_type(case_type: str) -> str:
    key = (case_type or "functional").lower()
    return CASE_TYPE_TO_CATEGORY.get(key, "functional")


def _resolve_tokens(
    pattern: str,
    *,
    proj5: str,
    env5: str,
    mod5: str,
    seq: int | None,
    seq_digits: int,
) -> str:
    seq_str = f"{seq:0{seq_digits}d}" if seq is not None else ""
    mapping = {
        "{PROJ5}": proj5,
        "{PROJ}": proj5,
        "{ENV5}": env5,
        "{ENV}": env5,
        "{MOD5}": mod5,
        "{MOD}": mod5,
        "{SEQ5}": seq_str,
        "{SEQ}": seq_str,
    }
    out = pattern
    for token, value in mapping.items():
        out = out.replace(token, value)
    return out


def pattern_prefix(
    pattern: str,
    *,
    proj5: str,
    env5: str,
    mod5: str,
    seq_digits: int,
) -> str:
    """Prefix used to find existing codes (pattern with empty sequence)."""
    return _resolve_tokens(
        pattern, proj5=proj5, env5=env5, mod5=mod5, seq=None, seq_digits=seq_digits
    )


def build_case_code(
    pattern: str,
    *,
    proj5: str,
    env5: str,
    mod5: str,
    seq: int,
    seq_digits: int,
) -> str:
    return _resolve_tokens(
        pattern, proj5=proj5, env5=env5, mod5=mod5, seq=seq, seq_digits=seq_digits
    )


def preview_pattern(
    pattern: str,
    *,
    seq_digits: int = 5,
    project_name: str = "Demo Application",
    environment_name: str = "Development",
    module_name: str = "Administration",
    seq: int = 1,
) -> str:
    validate_pattern(pattern)
    return build_case_code(
        pattern,
        proj5=name_prefix(project_name),
        env5=name_prefix(environment_name),
        mod5=name_prefix(module_name),
        seq=seq,
        seq_digits=seq_digits,
    )


class NamingPatternService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_patterns(self, project_id: uuid.UUID) -> dict[str, Any]:
        project = await self.db.get(ProjectModel, project_id)
        if not project:
            raise ValueError("Project not found")
        patterns = merge_patterns(project.naming_patterns)
        return {
            "project_id": str(project_id),
            "patterns": patterns,
            "defaults": DEFAULT_PATTERNS,
            "token_help": TOKEN_HELP,
            "categories": list(CATEGORIES),
            "preview_context": {
                "project_name": project.name,
                "environment_name": "Development",
                "module_name": "Administration",
            },
        }

    async def update_patterns(
        self, project_id: uuid.UUID, updates: dict[str, dict[str, Any]]
    ) -> dict[str, Any]:
        project = await self.db.get(ProjectModel, project_id)
        if not project:
            raise ValueError("Project not found")
        current = merge_patterns(project.naming_patterns)
        for cat in CATEGORIES:
            if cat not in updates:
                continue
            patch = updates[cat] or {}
            if "pattern" in patch and patch["pattern"] is not None:
                validate_pattern(str(patch["pattern"]))
                current[cat]["pattern"] = str(patch["pattern"]).strip()
            if "seq_digits" in patch and patch["seq_digits"] is not None:
                digits = int(patch["seq_digits"])
                if digits < 1 or digits > 10:
                    raise ValueError("seq_digits must be between 1 and 10")
                current[cat]["seq_digits"] = digits
        project.naming_patterns = current
        await self.db.flush()
        return await self.get_patterns(project_id)

    async def get_pattern_for_type(
        self, project_id: uuid.UUID, case_type: str
    ) -> tuple[str, int, str]:
        """Return (pattern, seq_digits, category) for a case type."""
        data = await self.get_patterns(project_id)
        cat = category_for_case_type(case_type)
        cfg = data["patterns"][cat]
        return cfg["pattern"], int(cfg["seq_digits"]), cat

"""Report bugs from remote QEOS installs → GitHub issue + attachment files."""

from __future__ import annotations

import platform
import re
import uuid
from datetime import datetime, timezone
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.models import ExecutionRunModel, IntegrationModel
from app.services.app_updates import check_for_updates, find_repo_root
from app.services.github_repo import create_github_issue, parse_github_owner_repo, push_repo_files
from app.services.log_buffer import recent_logs_text
from app.version import version_info, version_label

logger = structlog.get_logger()


def _sanitize_filename(name: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", (name or "file").strip())
    return cleaned[:80] or "file"


def _resolve_token() -> str:
    env_token = (settings.qeos_github_bug_token or "").strip()
    if env_token:
        return env_token
    # Fallbacks used by some installs
    for attr in ("github_client_secret",):
        value = (getattr(settings, attr, "") or "").strip()
        if value.startswith(("ghp_", "github_pat_", "gho_")):
            return value
    return ""


async def _token_from_integrations(db: AsyncSession | None) -> str:
    if db is None:
        return ""
    result = await db.execute(
        select(IntegrationModel)
        .where(IntegrationModel.provider == "github", IntegrationModel.status.in_(["active", "connected"]))
        .order_by(IntegrationModel.updated_at.desc())
    )
    row = result.scalars().first()
    if not row:
        return ""
    creds = row.credentials or {}
    return str(creds.get("token") or creds.get("access_token") or "").strip()


async def resolve_bug_target(db: AsyncSession | None = None) -> dict[str, Any]:
    """Resolve owner/repo/branch/token for filing bugs against the QEOS product repo."""
    configured_repo = (settings.qeos_github_bug_repo or "").strip()
    owner = repo = None
    if configured_repo and "/" in configured_repo:
        owner, repo = configured_repo.split("/", 1)
        owner, repo = owner.strip(), repo.strip().removesuffix(".git")

    remote_url = ""
    branch = "main"
    update = await check_for_updates(fetch=False)
    if update.get("supported"):
        remote_url = str(update.get("remote_url") or "")
        branch = str(update.get("branch") or "main")
        if not owner or not repo:
            parsed = parse_github_owner_repo(remote_url)
            if parsed:
                owner, repo = parsed

    if not owner or not repo:
        # Documented default product repo
        owner, repo = "nareshnakka", "AI-SmartQA-"

    token = _resolve_token()
    if not token:
        token = await _token_from_integrations(db)

    return {
        "configured": bool(token and owner and repo),
        "owner": owner,
        "repo": repo,
        "branch": branch or "main",
        "remote_url": remote_url or f"https://github.com/{owner}/{repo}",
        "has_token": bool(token),
        "token": token,
        "message": (
            "Report Bug is ready."
            if token
            else "Set QEOS_GITHUB_BUG_TOKEN in .env (GitHub PAT with repo scope), or connect GitHub in Integrations."
        ),
    }


def _redact(text: str) -> str:
    patterns = [
        (r"(?i)(api[_-]?key|token|password|secret|authorization)\s*[:=]\s*\S+", r"\1=***"),
        (r"(?i)bearer\s+[a-z0-9\-._~+/]+=*", "Bearer ***"),
        (r"ghp_[A-Za-z0-9]+", "ghp_***"),
        (r"github_pat_[A-Za-z0-9_]+", "github_pat_***"),
        (r"crsr_[A-Za-z0-9]+", "crsr_***"),
    ]
    out = text
    for pattern, repl in patterns:
        out = re.sub(pattern, repl, out)
    return out


async def _execution_logs(db: AsyncSession | None, run_id: str | None) -> str:
    if not db or not run_id:
        return ""
    try:
        row = await db.get(ExecutionRunModel, uuid.UUID(str(run_id)))
    except (ValueError, TypeError):
        return ""
    if not row:
        return ""
    logs = row.logs
    if isinstance(logs, list):
        text = "\n".join(str(x) for x in logs[-200:])
    else:
        text = str(logs or "")[-20000:]
    return _redact(text)


async def build_diagnostics(
    db: AsyncSession | None,
    *,
    page_url: str | None = None,
    execution_run_id: str | None = None,
) -> dict[str, str]:
    info = version_info()
    update = await check_for_updates(fetch=False)
    root = find_repo_root()

    meta_lines = [
        f"QEOS version: {info['label']}",
        f"Feature version: {info['feature_version']}",
        f"App env: {settings.app_env}",
        f"Platform: {platform.platform()}",
        f"Python: {platform.python_version()}",
        f"Host: {platform.node()}",
        f"Page URL: {page_url or '(not provided)'}",
        f"Repo root: {root or '(unknown)'}",
        f"Git branch: {update.get('branch') or '(unknown)'}",
        f"Git commit: {update.get('current_commit') or '(unknown)'}",
        f"Remote: {update.get('remote_url') or '(unknown)'}",
        f"Reported at (UTC): {datetime.now(timezone.utc).isoformat()}",
    ]

    app_logs = _redact(recent_logs_text(limit=250))
    exec_logs = await _execution_logs(db, execution_run_id)

    diagnostics_md = "# QEOS Bug Diagnostics\n\n" + "\n".join(f"- {line}" for line in meta_lines) + "\n"
    if execution_run_id:
        diagnostics_md += f"\nExecution run id: `{execution_run_id}`\n"

    logs_txt = "## Application logs (recent)\n\n" + app_logs
    if exec_logs:
        logs_txt += "\n\n## Execution run logs\n\n" + exec_logs + "\n"

    return {
        "diagnostics.md": diagnostics_md,
        "logs.txt": logs_txt,
    }


async def submit_bug_report(
    db: AsyncSession | None,
    *,
    title: str,
    description: str,
    steps_to_reproduce: str = "",
    page_url: str | None = None,
    execution_run_id: str | None = None,
    include_diagnostics: bool = True,
    screenshot_bytes: bytes | None = None,
    screenshot_filename: str | None = None,
    reporter: str | None = None,
) -> dict[str, Any]:
    title = (title or "").strip()
    description = (description or "").strip()
    if len(title) < 3:
        raise ValueError("Title must be at least 3 characters.")
    if len(description) < 5:
        raise ValueError("Description must be at least 5 characters.")

    target = await resolve_bug_target(db)
    if not target["has_token"]:
        raise ValueError(target["message"])

    owner, repo, branch = target["owner"], target["repo"], target["branch"]
    token = target["token"]
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    report_id = f"{stamp}-{uuid.uuid4().hex[:8]}"
    base_path = f"bug-reports/{report_id}"

    files: list[dict[str, Any]] = []
    attachment_links: list[str] = []

    if include_diagnostics:
        docs = await build_diagnostics(db, page_url=page_url, execution_run_id=execution_run_id)
        for name, content in docs.items():
            files.append({"path": f"{base_path}/{name}", "content": content})

    report_md = (
        f"# {title}\n\n"
        f"**Reported from:** remote QEOS ({version_label()})\n"
        f"**Reporter:** {reporter or 'anonymous'}\n"
        f"**Page:** {page_url or 'n/a'}\n\n"
        f"## Description\n\n{description}\n\n"
    )
    if steps_to_reproduce.strip():
        report_md += f"## Steps to reproduce\n\n{steps_to_reproduce.strip()}\n\n"
    files.append({"path": f"{base_path}/report.md", "content": report_md})

    if screenshot_bytes:
        fname = _sanitize_filename(screenshot_filename or "screenshot.png")
        if "." not in fname:
            fname += ".png"
        files.append({"path": f"{base_path}/{fname}", "content": screenshot_bytes})

    push_result = await push_repo_files(
        token,
        owner,
        repo,
        branch,
        files,
        commit_message=f"bug-report: {title[:72]}",
    )
    if not push_result.get("success"):
        logger.warning("bug_report_push_partial", errors=push_result.get("errors"))
        if not push_result.get("pushed"):
            raise ValueError(
                "Could not push bug attachments to GitHub: "
                + "; ".join(push_result.get("errors") or ["unknown error"])
            )

    for path, url in (push_result.get("urls") or {}).items():
        attachment_links.append(f"- [`{path}`]({url})")

    raw_base = f"https://github.com/{owner}/{repo}/blob/{branch}/{base_path}"
    issue_body = (
        f"### Reported from remote QEOS\n\n"
        f"- **Version:** {version_label()}\n"
        f"- **Page:** {page_url or 'n/a'}\n"
        f"- **Reporter:** {reporter or 'anonymous'}\n"
        f"- **Attachments folder:** [{base_path}]({raw_base})\n\n"
        f"### Description\n\n{description}\n\n"
    )
    if steps_to_reproduce.strip():
        issue_body += f"### Steps to reproduce\n\n{steps_to_reproduce.strip()}\n\n"
    if attachment_links:
        issue_body += "### Attachments\n\n" + "\n".join(attachment_links) + "\n\n"
    issue_body += (
        "_Filed automatically by QEOS Report Bug. "
        "Pull latest on your local machine, fix, and push to update the remote server._\n"
    )

    labels = [label.strip() for label in (settings.qeos_github_bug_labels or "bug,qeos").split(",") if label.strip()]
    issue = await create_github_issue(
        token,
        owner,
        repo,
        title=f"[QEOS] {title}"[:240],
        body=issue_body,
        labels=labels or None,
    )

    logger.info(
        "bug_report_filed",
        issue=issue.get("number"),
        url=issue.get("html_url"),
        report_id=report_id,
    )

    return {
        "ok": True,
        "report_id": report_id,
        "issue_number": issue.get("number"),
        "html_url": issue.get("html_url"),
        "owner": owner,
        "repo": repo,
        "branch": branch,
        "attachments_path": base_path,
        "attachments_url": raw_base,
        "pushed_files": push_result.get("pushed") or [],
        "push_errors": push_result.get("errors") or [],
        "message": f"Bug #{issue.get('number')} created — open it locally to fix and push.",
    }

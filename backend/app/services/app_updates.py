"""Check for GitHub app updates and trigger non-interactive install."""

from __future__ import annotations

import asyncio
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import DiscoverySessionModel, ExecutionRunModel, PerformanceRunModel
from app.services.execution_worker import _running as active_execution_ids

logger = structlog.get_logger()

_INSTALL_LOCK = asyncio.Lock()
_install_in_progress = False


def find_repo_root() -> Path | None:
    env_root = os.environ.get("QEOS_REPO_ROOT", "").strip()
    if env_root:
        candidate = Path(env_root).resolve()
        if (candidate / ".git").is_dir():
            return candidate

    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / ".git").is_dir():
            return parent
    return None


def _run_git(args: list[str], cwd: Path, timeout_sec: int = 30) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout_sec,
        shell=False,
    )


def _short_sha(value: str) -> str:
    value = (value or "").strip()
    return value[:7] if value else ""


def _git_check_sync(repo_root: Path, fetch: bool) -> dict:
    branch_proc = _run_git(["branch", "--show-current"], repo_root)
    branch = (branch_proc.stdout or "").strip() or "main"

    if fetch:
        fetch_proc = _run_git(["fetch", "origin", branch], repo_root, timeout_sec=60)
        if fetch_proc.returncode != 0:
            return {
                "available": False,
                "error": (fetch_proc.stderr or fetch_proc.stdout or "git fetch failed").strip(),
                "branch": branch,
            }

    local_proc = _run_git(["rev-parse", "HEAD"], repo_root)
    if local_proc.returncode != 0:
        return {
            "available": False,
            "error": (local_proc.stderr or "Could not read local commit").strip(),
            "branch": branch,
        }
    local_commit = (local_proc.stdout or "").strip()

    remote_proc = _run_git(["rev-parse", f"origin/{branch}"], repo_root)
    if remote_proc.returncode != 0:
        return {
            "available": False,
            "error": (remote_proc.stderr or f"Remote branch origin/{branch} not found").strip(),
            "branch": branch,
            "current_commit": _short_sha(local_commit),
        }

    remote_commit = (remote_proc.stdout or "").strip()
    behind_proc = _run_git(["rev-list", "--count", f"HEAD..origin/{branch}"], repo_root)
    behind = 0
    if behind_proc.returncode == 0:
        try:
            behind = int((behind_proc.stdout or "0").strip())
        except ValueError:
            behind = 0

    available = local_commit != remote_commit and behind > 0
    summary = "You are on the latest version."
    if available:
        commit_word = "commit" if behind == 1 else "commits"
        summary = f"{behind} new {commit_word} available on {branch}."

    origin_proc = _run_git(["remote", "get-url", "origin"], repo_root)
    remote_url = (origin_proc.stdout or "").strip() if origin_proc.returncode == 0 else ""

    return {
        "available": available,
        "branch": branch,
        "current_commit": _short_sha(local_commit),
        "remote_commit": _short_sha(remote_commit),
        "commits_behind": behind,
        "remote_url": remote_url,
        "summary": summary,
    }


async def check_for_updates(fetch: bool = True) -> dict:
    repo_root = find_repo_root()
    checked_at = datetime.now(timezone.utc).isoformat()
    if not repo_root:
        return {
            "supported": False,
            "available": False,
            "checked_at": checked_at,
            "error": "This installation is not a Git repository.",
            "summary": "Updates are only available in a Git clone of QEOS.",
        }

    loop = asyncio.get_running_loop()
    try:
        result = await loop.run_in_executor(None, lambda: _git_check_sync(repo_root, fetch))
    except FileNotFoundError:
        return {
            "supported": False,
            "available": False,
            "checked_at": checked_at,
            "error": "Git is not installed on this machine.",
            "summary": "Install Git to enable in-app updates.",
        }
    except subprocess.TimeoutExpired:
        return {
            "supported": True,
            "available": False,
            "checked_at": checked_at,
            "error": "Timed out while checking GitHub for updates.",
            "summary": "Could not reach GitHub. Try again later.",
        }
    except Exception as exc:
        logger.warning("update_check_failed", error=str(exc))
        return {
            "supported": True,
            "available": False,
            "checked_at": checked_at,
            "error": str(exc),
            "summary": "Update check failed.",
        }

    result["supported"] = True
    result["checked_at"] = checked_at
    result["repo_root"] = str(repo_root)
    if "error" in result:
        result.setdefault("summary", "Update check failed.")
    return result


async def get_running_activity(db: AsyncSession) -> dict:
    items: list[dict] = []

    exec_rows = (
        await db.execute(
            select(ExecutionRunModel).where(ExecutionRunModel.status == "running").order_by(ExecutionRunModel.created_at.desc())
        )
    ).scalars().all()
    for row in exec_rows:
        name = row.run_name or "Test execution"
        items.append(
            {
                "type": "execution",
                "id": str(row.id),
                "name": name,
                "status": row.status,
                "project_id": str(row.project_id),
            }
        )

    discovery_rows = (
        await db.execute(
            select(DiscoverySessionModel)
            .where(DiscoverySessionModel.status == "running")
            .order_by(DiscoverySessionModel.created_at.desc())
        )
    ).scalars().all()
    for row in discovery_rows:
        items.append(
            {
                "type": "discovery",
                "id": str(row.id),
                "name": row.name or "Discovery session",
                "status": row.status,
                "project_id": str(row.project_id),
            }
        )

    perf_rows = (
        await db.execute(
            select(PerformanceRunModel)
            .where(PerformanceRunModel.status == "running")
            .order_by(PerformanceRunModel.created_at.desc())
        )
    ).scalars().all()
    for row in perf_rows:
        items.append(
            {
                "type": "performance",
                "id": str(row.id),
                "name": f"Performance run ({row.workload_profile})",
                "status": row.status,
                "project_id": str(row.project_id),
            }
        )

    for run_id in sorted(active_execution_ids, key=str):
        if any(item["type"] == "execution" and item["id"] == str(run_id) for item in items):
            continue
        items.append(
            {
                "type": "execution",
                "id": str(run_id),
                "name": "Test execution",
                "status": "running",
                "project_id": None,
            }
        )

    return {
        "has_active": len(items) > 0,
        "count": len(items),
        "items": items,
    }


def _spawn_install_process(repo_root: Path) -> None:
    script = repo_root / "update-and-install.bat"
    if not script.is_file():
        raise FileNotFoundError(f"Update script not found: {script}")

    if sys.platform == "win32":
        cmd = ["cmd", "/c", "start", "", "/MIN", str(script), "/auto", str(repo_root)]
        subprocess.Popen(
            cmd,
            cwd=str(repo_root),
            shell=False,
            creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP,
            close_fds=True,
        )
        return

    subprocess.Popen(
        ["bash", str(script), str(repo_root)],
        cwd=str(repo_root),
        start_new_session=True,
        close_fds=True,
    )


async def install_update(force: bool = False) -> dict:
    global _install_in_progress

    if _install_in_progress:
        return {
            "started": False,
            "status": "in_progress",
            "message": "An update is already in progress.",
        }

    repo_root = find_repo_root()
    if not repo_root:
        return {
            "started": False,
            "status": "unsupported",
            "message": "Updates are only available in a Git clone of QEOS.",
        }

    script = repo_root / "update-and-install.bat"
    if sys.platform != "win32":
        return {
            "started": False,
            "status": "unsupported",
            "message": "In-app updates are currently supported on Windows only.",
        }
    if not script.is_file():
        return {
            "started": False,
            "status": "error",
            "message": "Update script is missing. Run update-and-install.bat manually.",
        }

    async with _INSTALL_LOCK:
        if _install_in_progress:
            return {
                "started": False,
                "status": "in_progress",
                "message": "An update is already in progress.",
            }
        _install_in_progress = True

    try:
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, lambda: _spawn_install_process(repo_root))
        logger.info("app_update_started", repo_root=str(repo_root), force=force)
        return {
            "started": True,
            "status": "started",
            "message": "Update started. The app will restart when the download completes.",
            "force": force,
        }
    except Exception as exc:
        _install_in_progress = False
        logger.warning("app_update_start_failed", error=str(exc))
        return {
            "started": False,
            "status": "error",
            "message": str(exc),
        }

"""In-app update notifications and install."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.services.app_updates import (
    check_for_updates,
    get_running_activity,
    install_update,
    maybe_auto_install,
)

router = APIRouter(prefix="/updates", tags=["Updates"])


class InstallUpdateRequest(BaseModel):
    force: bool = False
    auto: bool = False


def _build_notifications(update: dict, auto_result: dict | None) -> list[dict]:
    notifications: list[dict] = []
    if not update.get("available"):
        return notifications

    changelog = update.get("changelog") or []
    lines = [c.get("message", "") for c in changelog[:8] if c.get("message")]
    detail = "\n".join(f"• {line}" for line in lines) if lines else ""
    version_bit = ""
    if update.get("current_version") and update.get("remote_version"):
        version_bit = f"{update['current_version']} → {update['remote_version']}. "

    message = (update.get("summary") or "A newer version is available on GitHub.") + (
        f"\n{detail}" if detail else ""
    )

    action_label = "Install & restart"
    if auto_result and auto_result.get("started"):
        action_label = "Installing…"
    elif auto_result and auto_result.get("deferred"):
        action_label = "Will install when idle"

    notifications.append(
        {
            "id": f"app-update-{update.get('remote_commit') or 'latest'}",
            "type": "update",
            "title": "QEOS update available",
            "message": f"{version_bit}{message}".strip(),
            "created_at": update.get("checked_at"),
            "read": False,
            "action": {"kind": "install_update", "label": action_label},
            "meta": {
                "branch": update.get("branch"),
                "current_commit": update.get("current_commit"),
                "remote_commit": update.get("remote_commit"),
                "commits_behind": update.get("commits_behind", 0),
                "current_version": update.get("current_version"),
                "remote_version": update.get("remote_version"),
                "changelog": changelog,
                "auto_update_enabled": update.get("auto_update_enabled"),
                "auto_status": (auto_result or {}).get("status"),
            },
        }
    )

    if auto_result and auto_result.get("started"):
        notifications.append(
            {
                "id": "app-update-installing",
                "type": "update_progress",
                "title": "Installing update",
                "message": auto_result.get("message")
                or "Downloading and installing. The app will restart automatically. Your data is preserved.",
                "created_at": update.get("checked_at"),
                "read": False,
                "meta": {
                    "data_preserved": True,
                    "backup": (auto_result or {}).get("backup"),
                },
            }
        )
    elif auto_result and auto_result.get("deferred"):
        notifications.append(
            {
                "id": "app-update-deferred",
                "type": "update_deferred",
                "title": "Update deferred",
                "message": auto_result.get("message")
                or "Waiting for Discovery / tests to finish before installing.",
                "created_at": update.get("checked_at"),
                "read": False,
            }
        )

    return notifications


@router.get("/status")
async def updates_status(
    fetch: bool = True,
    auto_install: bool = True,
    db: AsyncSession = Depends(get_db),
):
    update = await check_for_updates(fetch=fetch)
    activity = await get_running_activity(db)
    auto_result = None
    if auto_install and update.get("available"):
        auto_result = await maybe_auto_install(db, update, activity)

    notifications = _build_notifications(update, auto_result)

    return {
        "update": update,
        "running_activity": activity,
        "notifications": notifications,
        "unread_count": len(notifications),
        "auto_install": auto_result,
        "poll_interval_sec": update.get("poll_interval_sec") or 120,
        "data_preserved": True,
    }


@router.post("/install")
async def install_app_update(
    body: InstallUpdateRequest,
    db: AsyncSession = Depends(get_db),
):
    activity = await get_running_activity(db)
    if activity["has_active"] and not body.force:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "Tests or discovery are still running. Stop them or confirm restart to install the update.",
                "running_activity": activity,
            },
        )

    result = await install_update(force=body.force)
    if not result.get("started"):
        status = result.get("status", "error")
        code = 409 if status == "in_progress" else 400
        raise HTTPException(status_code=code, detail=result)
    return result

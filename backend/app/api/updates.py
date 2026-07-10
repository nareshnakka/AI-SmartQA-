"""In-app update notifications and install."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.services.app_updates import check_for_updates, get_running_activity, install_update

router = APIRouter(prefix="/updates", tags=["Updates"])


class InstallUpdateRequest(BaseModel):
    force: bool = False


@router.get("/status")
async def updates_status(
    fetch: bool = True,
    db: AsyncSession = Depends(get_db),
):
    update = await check_for_updates(fetch=fetch)
    activity = await get_running_activity(db)
    notifications = []

    if update.get("available"):
        notifications.append(
            {
                "id": "app-update",
                "type": "update",
                "title": "QEOS update available",
                "message": update.get("summary") or "A newer version is available on GitHub.",
                "created_at": update.get("checked_at"),
                "read": False,
                "action": {"kind": "install_update", "label": "Install update"},
                "meta": {
                    "branch": update.get("branch"),
                    "current_commit": update.get("current_commit"),
                    "remote_commit": update.get("remote_commit"),
                    "commits_behind": update.get("commits_behind", 0),
                },
            }
        )

    return {
        "update": update,
        "running_activity": activity,
        "notifications": notifications,
        "unread_count": len(notifications),
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

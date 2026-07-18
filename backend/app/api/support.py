"""Support APIs — Report Bug from remote installs."""

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.services.bug_report import resolve_bug_target, submit_bug_report

router = APIRouter(prefix="/support", tags=["Support"])

MAX_SCREENSHOT_BYTES = 8 * 1024 * 1024


@router.get("/bug-report/status")
async def bug_report_status(db: AsyncSession = Depends(get_db)):
    target = await resolve_bug_target(db)
    return {
        "configured": target["configured"],
        "owner": target["owner"],
        "repo": target["repo"],
        "branch": target["branch"],
        "remote_url": target["remote_url"],
        "has_token": target["has_token"],
        "message": target["message"],
    }


@router.post("/bug-report")
async def create_bug_report(
    title: str = Form(...),
    description: str = Form(...),
    steps_to_reproduce: str = Form(""),
    page_url: str = Form(""),
    execution_run_id: str = Form(""),
    include_diagnostics: bool = Form(True),
    reporter: str = Form(""),
    screenshot: UploadFile | None = File(None),
    db: AsyncSession = Depends(get_db),
):
    screenshot_bytes: bytes | None = None
    screenshot_name: str | None = None
    if screenshot is not None and screenshot.filename:
        data = await screenshot.read()
        if len(data) > MAX_SCREENSHOT_BYTES:
            raise HTTPException(400, "Screenshot must be 8 MB or smaller.")
        if data:
            screenshot_bytes = data
            screenshot_name = screenshot.filename

    try:
        result = await submit_bug_report(
            db,
            title=title,
            description=description,
            steps_to_reproduce=steps_to_reproduce,
            page_url=page_url or None,
            execution_run_id=execution_run_id or None,
            include_diagnostics=include_diagnostics,
            screenshot_bytes=screenshot_bytes,
            screenshot_filename=screenshot_name,
            reporter=reporter or None,
        )
        return result
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(502, f"Failed to file bug on GitHub: {exc}") from exc

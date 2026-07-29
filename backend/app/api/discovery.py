from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.rbac import require_project
from app.core.security import AuthUser
from app.db.session import get_db
from app.services.discovery import DiscoveryService

router = APIRouter(prefix="/projects/{project_id}/discovery", tags=["Phase 5 — Discovery"])


class DiscoverRequest(BaseModel):
    base_url: str
    name: str | None = None
    credentials_hint: str | None = None
    requirements: str | None = None
    mode: str = "agent"
    username: str | None = None
    password: str | None = None
    background: bool = True


@router.post("/run")
async def run_discovery(project_id: UUID, body: DiscoverRequest, db: AsyncSession = Depends(get_db)):
    svc = DiscoveryService(db)
    try:
        session = await svc.start_discovery(
            project_id,
            body.base_url,
            body.name,
            body.credentials_hint,
            body.requirements,
            body.mode,
            body.username,
            body.password,
            body.background,
        )
        return svc.to_dict(session)
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.get("/sessions")
async def list_sessions(project_id: UUID, db: AsyncSession = Depends(get_db)):
    svc = DiscoveryService(db)
    sessions = await svc.list_sessions(project_id)
    return [svc.to_dict(s) for s in sessions]


@router.get("/sessions/{session_id}")
async def get_session(project_id: UUID, session_id: UUID, db: AsyncSession = Depends(get_db)):
    svc = DiscoveryService(db)
    session = await svc.get_session(session_id)
    if not session or session.project_id != project_id:
        raise HTTPException(404)
    return svc.to_dict(session)


class CommitTestsRequest(BaseModel):
    test_ids: list[str]
    module_id: UUID | None = None
    environment_id: UUID | None = None


@router.post("/sessions/{session_id}/cancel")
async def cancel_discovery_session(
    project_id: UUID,
    session_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    svc = DiscoveryService(db)
    try:
        session = await svc.cancel_running_session(project_id, session_id)
        await db.commit()
        return svc.to_dict(session)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@router.post("/sessions/{session_id}/clear-navigation")
async def clear_session_navigation(
    project_id: UUID,
    session_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    svc = DiscoveryService(db)
    try:
        session = await svc.clear_navigation_log(project_id, session_id)
        await db.commit()
        return svc.to_dict(session)
    except ValueError as e:
        raise HTTPException(404, str(e)) from e


@router.delete("/sessions/{session_id}")
async def delete_discovery_session(
    project_id: UUID,
    session_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    svc = DiscoveryService(db)
    try:
        await svc.delete_session(project_id, session_id)
        await db.commit()
        return {"deleted": True, "session_id": str(session_id)}
    except ValueError as e:
        raise HTTPException(404, str(e)) from e


@router.post("/sessions/{session_id}/commit-tests")
async def commit_proposed_tests(
    project_id: UUID,
    session_id: UUID,
    body: CommitTestsRequest,
    db: AsyncSession = Depends(get_db),
    _user: AuthUser = Depends(require_project("tester")),
):
    svc = DiscoveryService(db)
    try:
        result = await svc.commit_proposed_tests(project_id, session_id, body.test_ids, body.module_id, body.environment_id)
        await db.commit()
        session = await svc.get_session(session_id)
        return {**result, "session": svc.to_dict(session) if session else None}
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.post("/sessions/{session_id}/dismiss-tests")
async def dismiss_proposed_tests(
    project_id: UUID,
    session_id: UUID,
    body: CommitTestsRequest,
    db: AsyncSession = Depends(get_db),
    _user: AuthUser = Depends(require_project("tester")),
):
    svc = DiscoveryService(db)
    try:
        result = await svc.dismiss_proposed_tests(project_id, session_id, body.test_ids)
        await db.commit()
        session = await svc.get_session(session_id)
        return {**result, "session": svc.to_dict(session) if session else None}
    except ValueError as e:
        raise HTTPException(400, str(e))


class GenerateTestsRequest(BaseModel):
    generate_automation: bool = False


@router.post("/sessions/{session_id}/generate-tests")
async def generate_tests_from_discovery(
    project_id: UUID,
    session_id: UUID,
    body: GenerateTestsRequest,
    db: AsyncSession = Depends(get_db),
    _user: AuthUser = Depends(require_project("tester")),
):
    svc = DiscoveryService(db)
    try:
        return await svc.generate_tests_from_session(
            project_id, session_id, body.generate_automation
        )
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.post("/from-video")
async def understand_from_video(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    files: list[UploadFile] = File(default=[]),
    notes: str = Form(""),
    base_url: str = Form(""),
    llm_provider: str | None = Form(None),
    persist: bool = Form(False),
    module_id: UUID | None = Form(None),
    environment_id: UUID | None = Form(None),
    _user: AuthUser = Depends(require_project("tester")),
):
    """
    Build a test case from a screen recording and/or screenshots (+ optional notes).
    Requires OpenAI or Gemini for vision, or numbered notes as a text fallback.
    """
    from app.services.video_understanding import save_uploads_and_understand

    uploads: list[tuple[str, bytes]] = []
    for f in files or []:
        raw = await f.read()
        if raw:
            uploads.append((f.filename or "upload.bin", raw))

    try:
        case = await save_uploads_and_understand(
            files=uploads,
            notes=notes,
            base_url=base_url,
            llm_provider=llm_provider,
        )
    except ValueError as e:
        raise HTTPException(400, str(e)) from e

    committed = None
    if persist:
        from app.services.test_cases import create_project_test_case, test_case_to_dict

        try:
            row = await create_project_test_case(
                db,
                project_id,
                title=case.get("title") or "From video",
                description=f"Generated from video/screenshots ({case.get('source')})",
                steps=case.get("steps") or [],
                expected_results=case.get("expected_results") or ["Flow completes successfully"],
                priority=case.get("priority") or "high",
                module_id=module_id,
                module_name=case.get("module") or "Automation",
                environment_id=environment_id,
                tags=["video", "vision", case.get("source") or "video_understanding"],
                status="approved",
                case_type="functional",
            )
            await db.commit()
            committed = test_case_to_dict(row)
        except ValueError as e:
            raise HTTPException(400, str(e)) from e

    return {
        "proposed_test_case": case,
        "committed": committed,
        "message": (
            f"Understood recording — {len(case.get('steps') or [])} steps"
            + (f" via {case.get('vision_provider')}/{case.get('vision_model')}" if case.get("vision_provider") else "")
        ),
    }

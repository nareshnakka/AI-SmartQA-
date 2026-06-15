from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.services.automation import AutomationService, FRAMEWORK_LANGUAGES
from app.services.git_push import push_files_to_github
from app.services.integration_store import IntegrationStore

router = APIRouter(prefix="/projects/{project_id}/automation", tags=["Phase 2 — Automation"])


class GenerateAutomationRequest(BaseModel):
    framework: str = "playwright"
    test_case_ids: list[str] | None = None
    name: str | None = None


class UpdateFileRequest(BaseModel):
    path: str
    content: str
    save_version: bool = True


class PushToGitRequest(BaseModel):
    integration_id: UUID
    owner: str
    repo: str
    branch: str = "main"
    commit_message: str | None = None


@router.get("/frameworks")
async def list_frameworks():
    return {
        "frameworks": [
            {"id": "playwright", "name": "Playwright", "language": "typescript"},
            {"id": "selenium", "name": "Selenium", "language": "java"},
            {"id": "cypress", "name": "Cypress", "language": "javascript"},
            {"id": "webdriverio", "name": "WebdriverIO", "language": "typescript"},
            {"id": "robot_framework", "name": "Robot Framework", "language": "python"},
            {"id": "appium", "name": "Appium", "language": "python"},
            {"id": "puppeteer", "name": "Puppeteer", "language": "javascript"},
            {"id": "testcafe", "name": "TestCafe", "language": "javascript"},
        ]
    }


@router.post("/generate")
async def generate_automation(
    project_id: UUID, body: GenerateAutomationRequest, db: AsyncSession = Depends(get_db)
):
    svc = AutomationService(db)
    try:
        asset = await svc.generate(project_id, body.framework, body.test_case_ids, body.name)
        return svc.to_dict(asset)
    except ValueError as e:
        raise HTTPException(400, str(e))


class GenerateFromSourceRequest(BaseModel):
    source_type: str
    content: dict | list | str
    framework: str = "playwright"
    name: str | None = None
    base_url: str = ""
    discovery_session_id: UUID | None = None


@router.get("/input-sources")
async def list_input_sources(db: AsyncSession = Depends(get_db)):
    from app.services.automation_ingest import AutomationIngestService
    return {"sources": AutomationIngestService(db).list_source_types()}


@router.post("/generate-from-source")
async def generate_from_source(
    project_id: UUID, body: GenerateFromSourceRequest, db: AsyncSession = Depends(get_db)
):
    from app.services.automation_ingest import AutomationIngestService
    svc = AutomationIngestService(db)
    try:
        asset = await svc.generate_from_source(
            project_id, body.source_type, body.content, body.framework,
            body.name, body.base_url, body.discovery_session_id,
        )
        from app.services.automation import AutomationService
        return AutomationService(db).to_dict(asset)
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.post("/ingest/{source_type}")
async def ingest_source_file(
    project_id: UUID,
    source_type: str,
    framework: str = "playwright",
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    import json
    from app.services.automation_ingest import AutomationIngestService
    raw = await file.read()
    try:
        content = json.loads(raw)
    except json.JSONDecodeError:
        content = raw.decode(errors="replace")
    svc = AutomationIngestService(db)
    try:
        asset = await svc.generate_from_source(
            project_id, source_type, content, framework, name=f"{source_type} — {file.filename}"
        )
        from app.services.automation import AutomationService
        return AutomationService(db).to_dict(asset)
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.get("/assets")
async def list_assets(project_id: UUID, db: AsyncSession = Depends(get_db)):
    svc = AutomationService(db)
    assets = await svc.list_assets(project_id)
    return [svc.to_dict(a) for a in assets]


@router.get("/assets/{asset_id}")
async def get_asset(project_id: UUID, asset_id: UUID, db: AsyncSession = Depends(get_db)):
    svc = AutomationService(db)
    asset = await svc.get_asset(asset_id)
    if not asset or asset.project_id != project_id:
        raise HTTPException(404, "Asset not found")
    return svc.to_dict(asset)


@router.put("/assets/{asset_id}/files")
async def update_file(
    project_id: UUID, asset_id: UUID, body: UpdateFileRequest, db: AsyncSession = Depends(get_db)
):
    svc = AutomationService(db)
    try:
        asset = await svc.update_file(asset_id, body.path, body.content, body.save_version)
        if asset.project_id != project_id:
            raise HTTPException(404)
        return svc.to_dict(asset)
    except ValueError as e:
        raise HTTPException(404, str(e))


@router.get("/assets/{asset_id}/versions")
async def list_versions(project_id: UUID, asset_id: UUID, db: AsyncSession = Depends(get_db)):
    svc = AutomationService(db)
    versions = await svc.list_versions(asset_id)
    return [svc.to_dict(v) for v in versions if v.project_id == project_id]


@router.get("/assets/{asset_id}/diff/{other_id}")
async def diff_versions(
    project_id: UUID, asset_id: UUID, other_id: UUID, db: AsyncSession = Depends(get_db)
):
    svc = AutomationService(db)
    a = await svc.get_asset(asset_id)
    b = await svc.get_asset(other_id)
    if not a or not b or a.project_id != project_id:
        raise HTTPException(404)
    return {"diffs": svc.diff_files(a.files or [], b.files or [])}


@router.post("/assets/{asset_id}/validate")
async def validate_asset(project_id: UUID, asset_id: UUID, db: AsyncSession = Depends(get_db)):
    svc = AutomationService(db)
    asset = await svc.get_asset(asset_id)
    if not asset or asset.project_id != project_id:
        raise HTTPException(404)
    return await svc.validate(asset_id)


@router.get("/assets/{asset_id}/export")
async def export_asset_zip(project_id: UUID, asset_id: UUID, db: AsyncSession = Depends(get_db)):
    svc = AutomationService(db)
    asset = await svc.get_asset(asset_id)
    if not asset or asset.project_id != project_id:
        raise HTTPException(404)
    data = svc.build_zip_bytes(asset)
    filename = f"{asset.framework}-v{asset.version}.zip"
    return Response(
        content=data,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/assets/{asset_id}/push")
async def push_asset_to_git(
    project_id: UUID, asset_id: UUID, body: PushToGitRequest, db: AsyncSession = Depends(get_db)
):
    svc = AutomationService(db)
    asset = await svc.get_asset(asset_id)
    if not asset or asset.project_id != project_id:
        raise HTTPException(404)

    store = IntegrationStore(db)
    loaded = await store.get_credentials(body.integration_id)
    if not loaded:
        raise HTTPException(404, "Integration not found")
    row, credentials = loaded
    if row.project_id != project_id:
        raise HTTPException(403, "Integration belongs to another project")

    if row.provider != "github":
        raise HTTPException(400, "Only GitHub push is supported currently")

    result = await push_files_to_github(
        credentials,
        body.owner,
        body.repo,
        body.branch,
        asset.files or [],
        body.commit_message or f"QEOS: {asset.name} v{asset.version}",
    )
    if not result["success"]:
        raise HTTPException(502, detail=result)
    return result

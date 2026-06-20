from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ProjectModel, RequirementModel, TestCaseModel, TestSuiteModel, TestScenarioModel, AgentRunModel
from app.db.session import get_db
from app.models.phase1_schemas import (
    RequirementCreate,
    RequirementResponse,
    TestCaseResponse,
    TestCaseCreate,
    TestCaseUpdate,
    TestCaseBulkAction,
    TestSuiteResponse,
    GenerateRequest,
    GenerateResponse,
    CoverageResponse,
    AgentRunResponse,
)
from app.services.generation import GenerationService
from app.services.export import ExportService
from app.services.test_cases import bulk_test_case_action, create_project_test_case, list_project_test_cases, remove_case_references, test_case_to_dict

router = APIRouter(prefix="/projects/{project_id}", tags=["Phase 1 — Test Generation"])


async def _get_project(project_id: UUID, db: AsyncSession) -> ProjectModel:
    project = await db.get(ProjectModel, project_id)
    if not project:
        raise HTTPException(404, "Project not found")
    return project


# --- Requirements ---

@router.get("/requirements", response_model=list[RequirementResponse])
async def list_requirements(project_id: UUID, db: AsyncSession = Depends(get_db)):
    await _get_project(project_id, db)
    result = await db.execute(
        select(RequirementModel)
        .where(RequirementModel.project_id == project_id)
        .order_by(RequirementModel.created_at.desc())
    )
    return result.scalars().all()


@router.post("/requirements", response_model=RequirementResponse, status_code=201)
async def create_requirement(
    project_id: UUID, body: RequirementCreate, db: AsyncSession = Depends(get_db)
):
    await _get_project(project_id, db)
    req = RequirementModel(
        project_id=project_id,
        title=body.title or body.content[:80],
        content=body.content,
        source_type=body.source_type,
        external_ref=body.external_ref,
    )
    db.add(req)
    await db.flush()
    return req


@router.post("/requirements/upload", response_model=RequirementResponse, status_code=201)
async def upload_requirement(
    project_id: UUID,
    file: UploadFile = File(...),
    source_type: str = "document",
    db: AsyncSession = Depends(get_db),
):
    await _get_project(project_id, db)
    content = (await file.read()).decode("utf-8", errors="replace")
    req = RequirementModel(
        project_id=project_id,
        title=file.filename or "Uploaded Document",
        content=content,
        source_type=source_type,
        metadata_json={"filename": file.filename, "content_type": file.content_type},
    )
    db.add(req)
    await db.flush()
    return req


@router.delete("/requirements/{requirement_id}", status_code=204)
async def delete_requirement(
    project_id: UUID, requirement_id: UUID, db: AsyncSession = Depends(get_db)
):
    req = await db.get(RequirementModel, requirement_id)
    if not req or req.project_id != project_id:
        raise HTTPException(404, "Requirement not found")
    await db.delete(req)


# --- Test Cases ---

@router.get("/test-cases", response_model=list[TestCaseResponse])
async def list_test_cases(
    project_id: UUID,
    for_automation: bool = Query(False, description="Exclude disabled test cases"),
    module_id: str | None = Query(None, description="Comma-separated module UUIDs to filter"),
    environment_id: str | None = Query(None, description="Comma-separated environment UUIDs to filter"),
    db: AsyncSession = Depends(get_db),
):
    await _get_project(project_id, db)
    module_ids = None
    if module_id and module_id.lower() != "all":
        module_ids = [UUID(x.strip()) for x in module_id.split(",") if x.strip()]
    environment_ids = None
    if environment_id and environment_id.lower() != "all":
        environment_ids = [UUID(x.strip()) for x in environment_id.split(",") if x.strip()]
    cases = await list_project_test_cases(
        db,
        project_id,
        for_automation=for_automation,
        module_ids=module_ids,
        environment_ids=environment_ids,
    )
    return [TestCaseResponse(**test_case_to_dict(c)) for c in cases]


@router.post("/test-cases", response_model=TestCaseResponse, status_code=201)
async def create_test_case(
    project_id: UUID, body: TestCaseCreate, db: AsyncSession = Depends(get_db)
):
    await _get_project(project_id, db)
    try:
        case = await create_project_test_case(
            db,
            project_id,
            title=body.title,
            description=body.description or "",
            steps=body.steps,
            expected_results=body.expected_results,
            priority=body.priority,
            module_id=body.module_id,
            module_name=body.module_name,
            environment_id=body.environment_id,
            case_type="functional",
        )
        return TestCaseResponse(**test_case_to_dict(case))
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@router.get("/test-cases/{case_id}", response_model=TestCaseResponse)
async def get_test_case(project_id: UUID, case_id: UUID, db: AsyncSession = Depends(get_db)):
    case = await db.get(TestCaseModel, case_id)
    if not case or case.project_id != project_id:
        raise HTTPException(404, "Test case not found")
    if case.module_id:
        await db.refresh(case, attribute_names=["module"])
    if case.environment_id:
        await db.refresh(case, attribute_names=["environment"])
    return TestCaseResponse(**test_case_to_dict(case))


@router.patch("/test-cases/{case_id}", response_model=TestCaseResponse)
async def update_test_case(
    project_id: UUID, case_id: UUID, body: TestCaseUpdate, db: AsyncSession = Depends(get_db)
):
    case = await db.get(TestCaseModel, case_id)
    if not case or case.project_id != project_id:
        raise HTTPException(404, "Test case not found")
    for field in ["title", "description", "steps", "expected_results", "priority", "status", "module_id", "environment_id"]:
        val = getattr(body, field, None)
        if val is not None:
            setattr(case, field, val)
    await db.flush()
    if case.module_id:
        await db.refresh(case, attribute_names=["module"])
    if case.environment_id:
        await db.refresh(case, attribute_names=["environment"])
    return TestCaseResponse(**test_case_to_dict(case))


@router.delete("/test-cases/{case_id}", status_code=204)
async def delete_test_case(project_id: UUID, case_id: UUID, db: AsyncSession = Depends(get_db)):
    case = await db.get(TestCaseModel, case_id)
    if not case or case.project_id != project_id:
        raise HTTPException(404, "Test case not found")
    await remove_case_references(db, project_id, {str(case_id)})
    await db.delete(case)


@router.post("/test-cases/bulk-action")
async def bulk_action_test_cases(
    project_id: UUID, body: TestCaseBulkAction, db: AsyncSession = Depends(get_db)
):
    await _get_project(project_id, db)
    if body.action not in {"delete", "disable", "enable"}:
        raise HTTPException(400, "action must be delete, disable, or enable")
    try:
        return await bulk_test_case_action(db, project_id, body.test_case_ids, body.action)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


# --- Test Suites ---

@router.get("/test-suites", response_model=list[TestSuiteResponse])
async def list_test_suites(project_id: UUID, db: AsyncSession = Depends(get_db)):
    await _get_project(project_id, db)
    result = await db.execute(
        select(TestSuiteModel).where(TestSuiteModel.project_id == project_id)
    )
    return result.scalars().all()


# --- Generation (Phase 1 core) ---

@router.post("/generate", response_model=GenerateResponse)
async def generate_tests(
    project_id: UUID, body: GenerateRequest, db: AsyncSession = Depends(get_db)
):
    await _get_project(project_id, db)
    service = GenerationService(db)
    result = await service.generate_from_requirement(
        project_id=project_id,
        content=body.content,
        source_type=body.source_type,
        title=body.title,
        run_test_design=body.run_test_design,
    )
    return GenerateResponse(**result)


@router.post("/generate/from-requirement/{requirement_id}", response_model=GenerateResponse)
async def generate_from_existing_requirement(
    project_id: UUID, requirement_id: UUID, db: AsyncSession = Depends(get_db)
):
    req = await db.get(RequirementModel, requirement_id)
    if not req or req.project_id != project_id:
        raise HTTPException(404, "Requirement not found")
    service = GenerationService(db)
    result = await service.generate_from_requirement(
        project_id=project_id,
        content=req.content,
        source_type=req.source_type,
        title=req.title,
    )
    return GenerateResponse(**result)


# --- Coverage ---

@router.get("/coverage", response_model=CoverageResponse)
async def get_coverage(project_id: UUID, db: AsyncSession = Depends(get_db)):
    await _get_project(project_id, db)
    coverage = await GenerationService(db).get_project_coverage(project_id)
    return CoverageResponse(**coverage)


# --- Agent Run History ---

@router.get("/runs", response_model=list[AgentRunResponse])
async def list_runs(project_id: UUID, db: AsyncSession = Depends(get_db)):
    await _get_project(project_id, db)
    result = await db.execute(
        select(AgentRunModel)
        .where(AgentRunModel.project_id == project_id)
        .order_by(AgentRunModel.created_at.desc())
    )
    return result.scalars().all()


# --- Export ---

@router.get("/export/json")
async def export_json(project_id: UUID, db: AsyncSession = Depends(get_db)):
    await _get_project(project_id, db)
    return await ExportService(db).export_json(project_id)


@router.get("/export/csv")
async def export_csv(project_id: UUID, db: AsyncSession = Depends(get_db)):
    from fastapi.responses import PlainTextResponse
    await _get_project(project_id, db)
    csv_content = await ExportService(db).export_csv(project_id)
    return PlainTextResponse(
        content=csv_content,
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=qeos-tests-{project_id}.csv"},
    )


# --- Scenarios ---

@router.get("/scenarios")
async def list_scenarios(project_id: UUID, db: AsyncSession = Depends(get_db)):
    await _get_project(project_id, db)
    result = await db.execute(
        select(TestScenarioModel)
        .where(TestScenarioModel.project_id == project_id)
        .order_by(TestScenarioModel.created_at.desc())
    )
    return [{"id": str(s.id), "description": s.description, "created_at": s.created_at.isoformat()} for s in result.scalars().all()]

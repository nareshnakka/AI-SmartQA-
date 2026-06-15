import uuid
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ProjectModel, RequirementModel, TestCaseModel
from app.db.session import get_db
from app.models.phase1_schemas import (
    ProjectCreate,
    ProjectDetailResponse,
    ProjectResponse,
    ProjectUpdate,
)

router = APIRouter(prefix="/projects", tags=["Projects"])


async def _project_counts(db: AsyncSession, project_id: uuid.UUID) -> tuple[int, int]:
    req_count = await db.scalar(
        select(func.count()).select_from(RequirementModel).where(RequirementModel.project_id == project_id)
    )
    case_count = await db.scalar(
        select(func.count()).select_from(TestCaseModel).where(TestCaseModel.project_id == project_id)
    )
    return req_count or 0, case_count or 0


def _to_response(project: ProjectModel, req_count: int, case_count: int) -> ProjectResponse:
    return ProjectResponse(
        id=project.id,
        name=project.name,
        description=project.description,
        created_at=project.created_at,
        updated_at=project.updated_at,
        requirement_count=req_count,
        test_case_count=case_count,
    )


@router.get("", response_model=list[ProjectResponse])
async def list_projects(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(ProjectModel).order_by(ProjectModel.created_at.desc()))
    projects = result.scalars().all()
    out = []
    for p in projects:
        rc, cc = await _project_counts(db, p.id)
        out.append(_to_response(p, rc, cc))
    return out


@router.post("", response_model=ProjectResponse, status_code=201)
async def create_project(body: ProjectCreate, db: AsyncSession = Depends(get_db)):
    project = ProjectModel(name=body.name, description=body.description)
    db.add(project)
    await db.flush()
    return _to_response(project, 0, 0)


@router.get("/{project_id}", response_model=ProjectDetailResponse)
async def get_project(project_id: UUID, db: AsyncSession = Depends(get_db)):
    project = await db.get(ProjectModel, project_id)
    if not project:
        raise HTTPException(404, "Project not found")
    rc, cc = await _project_counts(db, project_id)
    from app.services.generation import GenerationService
    coverage = await GenerationService(db).get_project_coverage(project_id)
    return ProjectDetailResponse(
        **_to_response(project, rc, cc).model_dump(),
        coverage_percentage=coverage.get("coverage_percentage", 0.0),
    )


@router.patch("/{project_id}", response_model=ProjectResponse)
async def update_project(project_id: UUID, body: ProjectUpdate, db: AsyncSession = Depends(get_db)):
    project = await db.get(ProjectModel, project_id)
    if not project:
        raise HTTPException(404, "Project not found")
    if body.name is not None:
        project.name = body.name
    if body.description is not None:
        project.description = body.description
    await db.flush()
    rc, cc = await _project_counts(db, project_id)
    return _to_response(project, rc, cc)


@router.delete("/{project_id}", status_code=204)
async def delete_project(project_id: UUID, db: AsyncSession = Depends(get_db)):
    project = await db.get(ProjectModel, project_id)
    if not project:
        raise HTTPException(404, "Project not found")
    await db.delete(project)

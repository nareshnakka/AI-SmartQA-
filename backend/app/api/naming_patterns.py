from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.services.naming_patterns import NamingPatternService, preview_pattern

router = APIRouter(prefix="/projects/{project_id}/naming-patterns", tags=["Naming Patterns"])


class CategoryPattern(BaseModel):
    pattern: str | None = None
    seq_digits: int | None = Field(None, ge=1, le=10)


class UpdateNamingPatternsRequest(BaseModel):
    functional: CategoryPattern | None = None
    automation: CategoryPattern | None = None
    performance: CategoryPattern | None = None
    security: CategoryPattern | None = None


class PreviewRequest(BaseModel):
    pattern: str
    seq_digits: int = Field(5, ge=1, le=10)
    project_name: str | None = None
    environment_name: str = "Development"
    module_name: str = "Administration"
    seq: int = 1


@router.get("")
async def get_naming_patterns(project_id: UUID, db: AsyncSession = Depends(get_db)):
    svc = NamingPatternService(db)
    try:
        data = await svc.get_patterns(project_id)
        previews = {}
        ctx = data["preview_context"]
        for cat, cfg in data["patterns"].items():
            previews[cat] = preview_pattern(
                cfg["pattern"],
                seq_digits=int(cfg["seq_digits"]),
                project_name=ctx["project_name"],
                environment_name=ctx["environment_name"],
                module_name=ctx["module_name"],
            )
        data["previews"] = previews
        return data
    except ValueError as e:
        raise HTTPException(404, str(e)) from e


@router.put("")
async def update_naming_patterns(
    project_id: UUID,
    body: UpdateNamingPatternsRequest,
    db: AsyncSession = Depends(get_db),
):
    svc = NamingPatternService(db)
    updates = {
        k: v.model_dump(exclude_unset=True)
        for k, v in body.model_dump(exclude_unset=True).items()
        if v is not None
    }
    try:
        return await svc.update_patterns(project_id, updates)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@router.post("/preview")
async def preview_naming_pattern(
    project_id: UUID,
    body: PreviewRequest,
    db: AsyncSession = Depends(get_db),
):
    svc = NamingPatternService(db)
    try:
        data = await svc.get_patterns(project_id)
        project_name = body.project_name or data["preview_context"]["project_name"]
        code = preview_pattern(
            body.pattern,
            seq_digits=body.seq_digits,
            project_name=project_name,
            environment_name=body.environment_name,
            module_name=body.module_name,
            seq=body.seq,
        )
        return {"preview": code}
    except ValueError as e:
        raise HTTPException(400, str(e)) from e

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.services.reports import ReportsService

router = APIRouter(prefix="/reports", tags=["Phase 5 — Reports"])


@router.get("/overview")
async def platform_overview(db: AsyncSession = Depends(get_db)):
    svc = ReportsService(db)
    return await svc.platform_overview()


@router.get("/projects/{project_id}")
async def project_report(project_id: UUID, db: AsyncSession = Depends(get_db)):
    svc = ReportsService(db)
    try:
        return await svc.project_report(project_id)
    except ValueError as e:
        raise HTTPException(404, str(e))

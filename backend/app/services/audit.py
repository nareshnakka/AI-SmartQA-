"""Audit logging for governance and compliance."""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AuditLogModel


class AuditService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def log(
        self,
        action: str,
        user_id: uuid.UUID | None = None,
        project_id: uuid.UUID | None = None,
        resource_type: str = "",
        resource_id: str | None = None,
        details: dict | None = None,
    ) -> AuditLogModel:
        entry = AuditLogModel(
            user_id=user_id,
            project_id=project_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            details=details,
        )
        self.db.add(entry)
        await self.db.flush()
        return entry

    async def list_logs(
        self,
        project_id: uuid.UUID | None = None,
        limit: int = 100,
    ) -> list[AuditLogModel]:
        query = select(AuditLogModel).order_by(AuditLogModel.created_at.desc()).limit(limit)
        if project_id:
            query = query.where(AuditLogModel.project_id == project_id)
        result = await self.db.execute(query)
        return list(result.scalars().all())

    def to_dict(self, entry: AuditLogModel) -> dict:
        return {
            "id": str(entry.id),
            "user_id": str(entry.user_id) if entry.user_id else None,
            "project_id": str(entry.project_id) if entry.project_id else None,
            "action": entry.action,
            "resource_type": entry.resource_type,
            "resource_id": entry.resource_id,
            "details": entry.details,
            "created_at": entry.created_at.isoformat(),
        }

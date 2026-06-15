"""Production monitoring event ingestion."""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import MonitoringEventModel


class MonitoringService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def ingest(
        self,
        event_type: str,
        title: str,
        severity: str = "info",
        source: str = "custom",
        project_id: uuid.UUID | None = None,
        payload: dict | None = None,
    ) -> MonitoringEventModel:
        event = MonitoringEventModel(
            project_id=project_id,
            source=source,
            event_type=event_type,
            severity=severity,
            title=title,
            payload=payload or {},
        )
        self.db.add(event)
        await self.db.flush()
        return event

    async def list_events(
        self, project_id: uuid.UUID | None = None, limit: int = 50
    ) -> list[MonitoringEventModel]:
        query = select(MonitoringEventModel).order_by(MonitoringEventModel.created_at.desc()).limit(limit)
        if project_id:
            query = query.where(MonitoringEventModel.project_id == project_id)
        result = await self.db.execute(query)
        return list(result.scalars().all())

    def to_dict(self, event: MonitoringEventModel) -> dict:
        return {
            "id": str(event.id),
            "project_id": str(event.project_id) if event.project_id else None,
            "source": event.source,
            "event_type": event.event_type,
            "severity": event.severity,
            "title": event.title,
            "payload": event.payload,
            "created_at": event.created_at.isoformat(),
        }

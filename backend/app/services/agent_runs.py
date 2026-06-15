"""Persist agent runs to database."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AgentRunModel
from app.models.schemas import AgentRunResponse, AgentStatus, AgentType


class AgentRunService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def save_from_response(self, run: AgentRunResponse) -> AgentRunModel:
        existing = await self.db.get(AgentRunModel, run.id)
        if existing:
            existing.status = run.status.value if hasattr(run.status, "value") else str(run.status)
            existing.output_data = run.output
            existing.error = run.error
            existing.completed_at = run.completed_at
            await self.db.flush()
            return existing

        model = AgentRunModel(
            id=run.id,
            project_id=run.project_id,
            agent_type=run.agent_type.value if isinstance(run.agent_type, AgentType) else str(run.agent_type),
            status=run.status.value if hasattr(run.status, "value") else str(run.status),
            input_data=run.input_data if hasattr(run, "input_data") else None,
            output_data=run.output,
            error=run.error,
            llm_provider=getattr(run, "llm_provider", None),
            llm_model=getattr(run, "llm_model", None),
            created_at=run.created_at or datetime.now(timezone.utc),
            completed_at=run.completed_at,
        )
        self.db.add(model)
        await self.db.flush()
        return model

    async def list_runs(self, project_id: uuid.UUID | None = None, limit: int = 50) -> list[AgentRunModel]:
        query = select(AgentRunModel).order_by(AgentRunModel.created_at.desc()).limit(limit)
        if project_id:
            query = query.where(AgentRunModel.project_id == project_id)
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def get_run(self, run_id: uuid.UUID) -> AgentRunModel | None:
        return await self.db.get(AgentRunModel, run_id)

    def to_response(self, model: AgentRunModel) -> AgentRunResponse:
        try:
            agent_type = AgentType(model.agent_type)
        except ValueError:
            agent_type = model.agent_type
        try:
            status = AgentStatus(model.status)
        except ValueError:
            status = AgentStatus.COMPLETED
        return AgentRunResponse(
            id=model.id,
            agent_type=agent_type,
            status=status,
            project_id=model.project_id,
            output=model.output_data,
            error=model.error,
            created_at=model.created_at,
            completed_at=model.completed_at,
        )

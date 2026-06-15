from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from app.models.schemas import AgentStatus, AgentType


@dataclass
class AgentContext:
    run_id: UUID
    project_id: UUID
    agent_type: AgentType
    input_data: dict[str, Any]
    llm_provider: str | None = None
    llm_model: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class AgentResult:
    run_id: UUID
    status: AgentStatus
    output: dict[str, Any] | None = None
    error: str | None = None
    artifacts: list[dict[str, Any]] = field(default_factory=list)
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: datetime | None = None


class BaseAgent(ABC):
    """Base class for all QEOS AI agents."""

    agent_type: AgentType
    name: str
    description: str

    @abstractmethod
    async def execute(self, context: AgentContext) -> AgentResult:
        pass

    def create_result(
        self,
        context: AgentContext,
        output: dict[str, Any] | None = None,
        error: str | None = None,
        artifacts: list[dict[str, Any]] | None = None,
    ) -> AgentResult:
        status = AgentStatus.COMPLETED if error is None else AgentStatus.FAILED
        return AgentResult(
            run_id=context.run_id,
            status=status,
            output=output,
            error=error,
            artifacts=artifacts or [],
            completed_at=datetime.now(timezone.utc),
        )

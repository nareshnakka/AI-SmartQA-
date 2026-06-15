import structlog
from datetime import datetime, timezone
from uuid import UUID, uuid4

from app.agents.base import AgentContext, AgentResult
from app.agents.registry import get_agent_registry
from app.config import settings
from app.intelligence.training_collector import get_training_collector
from app.models.schemas import AgentRunResponse, AgentStatus, AgentType

logger = structlog.get_logger()


class AgentOrchestrator:
    """
    Orchestrates multi-agent workflows.
    Phase 4+ will extend this with LangGraph-style state machines
    and human-in-the-loop approval gates.
    """

    def __init__(self) -> None:
        self._runs: dict[UUID, AgentRunResponse] = {}
        self._registry = get_agent_registry()

    def list_agents(self) -> list[dict]:
        return self._registry.list_agents()

    async def run_agent(
        self,
        agent_type: AgentType,
        project_id: UUID,
        input_data: dict,
        llm_provider: str | None = None,
        llm_model: str | None = None,
    ) -> AgentRunResponse:
        run_id = uuid4()
        now = datetime.now(timezone.utc)

        run = AgentRunResponse(
            id=run_id,
            agent_type=agent_type,
            status=AgentStatus.RUNNING,
            project_id=project_id,
            created_at=now,
        )
        self._runs[run_id] = run

        context = AgentContext(
            run_id=run_id,
            project_id=project_id,
            agent_type=agent_type,
            input_data=input_data,
            llm_provider=llm_provider,
            llm_model=llm_model,
        )

        try:
            agent = self._registry.get(agent_type)
            logger.info("agent_started", run_id=str(run_id), agent=agent_type.value)
            result: AgentResult = await agent.execute(context)

            run.status = result.status
            run.output = result.output
            run.error = result.error
            run.completed_at = result.completed_at

            if result.status == AgentStatus.COMPLETED and result.output:
                get_training_collector().record(
                    agent_type=agent_type,
                    input_data=input_data,
                    output=result.output,
                    provider=llm_provider or settings.default_llm_provider,
                    model=llm_model or settings.default_llm_model,
                    run_id=str(run_id),
                )

            logger.info("agent_completed", run_id=str(run_id), status=result.status.value)
        except Exception as e:
            run.status = AgentStatus.FAILED
            run.error = str(e)
            run.completed_at = datetime.now(timezone.utc)
            logger.error("agent_failed", run_id=str(run_id), error=str(e))

        self._runs[run_id] = run
        await self._persist_run(run, input_data, llm_provider, llm_model)
        return run

    async def _persist_run(
        self,
        run: AgentRunResponse,
        input_data: dict,
        llm_provider: str | None,
        llm_model: str | None,
    ) -> None:
        from app.db.session import AsyncSessionLocal
        from app.db.models import AgentRunModel

        try:
            async with AsyncSessionLocal() as db:
                existing = await db.get(AgentRunModel, run.id)
                if existing:
                    existing.status = run.status.value
                    existing.output_data = run.output
                    existing.error = run.error
                    existing.completed_at = run.completed_at
                else:
                    db.add(AgentRunModel(
                        id=run.id,
                        project_id=run.project_id,
                        agent_type=run.agent_type.value,
                        status=run.status.value,
                        input_data=input_data,
                        output_data=run.output,
                        error=run.error,
                        llm_provider=llm_provider,
                        llm_model=llm_model,
                        created_at=run.created_at,
                        completed_at=run.completed_at,
                    ))
                await db.commit()
        except Exception as e:
            logger.warning("agent_run_persist_failed", run_id=str(run.id), error=str(e))

    async def run_pipeline(
        self,
        project_id: UUID,
        pipeline: list[AgentType],
        initial_input: dict,
        llm_provider: str | None = None,
        llm_model: str | None = None,
    ) -> list[AgentRunResponse]:
        """Run a sequence of agents, passing output forward."""
        results: list[AgentRunResponse] = []
        current_input = initial_input

        for agent_type in pipeline:
            run = await self.run_agent(
                agent_type=agent_type,
                project_id=project_id,
                input_data=current_input,
                llm_provider=llm_provider,
                llm_model=llm_model,
            )
            results.append(run)

            if run.status == AgentStatus.FAILED:
                break

            if run.output:
                current_input = {**current_input, **run.output}

        return results

    def get_run(self, run_id: UUID) -> AgentRunResponse | None:
        return self._runs.get(run_id)

    def list_runs(self, project_id: UUID | None = None) -> list[AgentRunResponse]:
        runs = list(self._runs.values())
        if project_id:
            runs = [r for r in runs if r.project_id == project_id]
        return sorted(runs, key=lambda r: r.created_at, reverse=True)


_orchestrator: AgentOrchestrator | None = None


def get_orchestrator() -> AgentOrchestrator:
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = AgentOrchestrator()
    return _orchestrator

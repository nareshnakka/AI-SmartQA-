"""Phase 4 — Multi-agent pipeline orchestration."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.orchestrator import get_orchestrator
from app.db.models import PipelineRunModel
from app.models.schemas import AgentStatus, AgentType
from app.services.automation import AutomationService
from app.services.generation import GenerationService
from app.services.performance import PerformanceService


DEFAULT_PIPELINES = {
    "full_quality": {
        "name": "Full Quality Pipeline",
        "steps": ["requirements", "test_design", "automation", "performance"],
        "description": "Requirements → Test Design → Automation → Performance",
    },
    "test_to_automation": {
        "name": "Test to Automation",
        "steps": ["requirements", "automation"],
        "description": "Generate test cases then automation scripts",
    },
    "regression_ready": {
        "name": "Regression Ready",
        "steps": ["requirements", "test_design"],
        "description": "Test cases with regression/smoke packs",
    },
}


class PipelineService:
    def __init__(self, db: AsyncSession):
        self.db = db

    @staticmethod
    def list_templates() -> dict:
        return DEFAULT_PIPELINES

    async def run_pipeline(
        self,
        project_id: uuid.UUID,
        pipeline_key: str,
        input_data: dict,
    ) -> PipelineRunModel:
        template = DEFAULT_PIPELINES.get(pipeline_key)
        if not template:
            raise ValueError(f"Unknown pipeline: {pipeline_key}")

        pipeline_run = PipelineRunModel(
            project_id=project_id,
            name=template["name"],
            pipeline=template["steps"],
            steps=[],
            status="running",
            input_data=input_data,
        )
        self.db.add(pipeline_run)
        await self.db.flush()

        steps_result = []
        content = input_data.get("content", "")

        try:
            for step in template["steps"]:
                step_record = {"agent": step, "status": "running", "output": None, "error": None}

                if step == "requirements":
                    gen = GenerationService(self.db)
                    out = await gen.generate_from_requirement(
                        project_id, content,
                        input_data.get("source_type", "user_story"),
                        run_test_design=False,
                    )
                    step_record["status"] = "completed"
                    step_record["output"] = {"test_cases": len(out.get("test_cases", []))}

                elif step == "test_design":
                    from app.intelligence.engine import TaskType, get_intelligence_engine
                    engine = get_intelligence_engine()
                    gen_svc = GenerationService(self.db)
                    cov = await gen_svc.get_project_coverage(project_id)
                    out = engine.generate(TaskType.TEST_DESIGN, {"test_cases": []})
                    step_record["status"] = "completed"
                    step_record["output"] = {"packs_created": True}

                elif step == "automation":
                    auto = AutomationService(self.db)
                    asset = await auto.generate(project_id, framework=input_data.get("framework", "playwright"))
                    step_record["status"] = "completed"
                    step_record["output"] = {"asset_id": str(asset.id), "files": len(asset.files or [])}

                elif step == "performance":
                    perf = PerformanceService(self.db)
                    asset = await perf.generate(project_id, tool=input_data.get("tool", "k6"))
                    step_record["status"] = "completed"
                    step_record["output"] = {"asset_id": str(asset.id)}

                else:
                    orchestrator = get_orchestrator()
                    run = await orchestrator.run_agent(
                        AgentType(step),
                        project_id,
                        input_data,
                    )
                    step_record["status"] = run.status.value
                    step_record["output"] = run.output
                    if run.error:
                        step_record["error"] = run.error

                steps_result.append(step_record)
                if step_record["status"] == "failed":
                    break

            pipeline_run.steps = steps_result
            pipeline_run.status = "completed" if all(s["status"] == "completed" for s in steps_result) else "failed"
            pipeline_run.completed_at = datetime.now(timezone.utc)

        except Exception as e:
            pipeline_run.status = "failed"
            pipeline_run.steps = steps_result + [{"agent": "system", "status": "failed", "error": str(e)}]
            pipeline_run.completed_at = datetime.now(timezone.utc)

        await self.db.flush()
        return pipeline_run

    async def list_runs(self, project_id: uuid.UUID) -> list[PipelineRunModel]:
        result = await self.db.execute(
            select(PipelineRunModel)
            .where(PipelineRunModel.project_id == project_id)
            .order_by(PipelineRunModel.created_at.desc())
        )
        return list(result.scalars().all())

    async def get_run(self, run_id: uuid.UUID) -> PipelineRunModel | None:
        return await self.db.get(PipelineRunModel, run_id)

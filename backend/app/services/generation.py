"""Phase 1 generation service — orchestrates agents and persists results."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.orchestrator import get_orchestrator
from app.db.models import (
    AgentRunModel,
    CoverageSnapshotModel,
    RequirementModel,
    TestCaseModel,
    TestScenarioModel,
    TestSuiteModel,
)
from app.intelligence.engine import TaskType, get_intelligence_engine
from app.models.schemas import AgentStatus, AgentType
from app.services.studio_inputs import StudioInputParser


class GenerationService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.engine = get_intelligence_engine()
        self.orchestrator = get_orchestrator()

    async def generate_from_requirement(
        self,
        project_id: uuid.UUID,
        content: str,
        source_type: str = "user_story",
        title: str | None = None,
        run_test_design: bool = True,
        llm_provider: str | None = None,
        llm_model: str | None = None,
    ) -> dict:
        """Full Phase 1 pipeline: parse → generate test cases → test design → persist."""

        # Save requirement
        req = RequirementModel(
            project_id=project_id,
            title=title or content[:80].strip(),
            content=content,
            source_type=source_type,
        )
        self.db.add(req)
        await self.db.flush()

        # Run requirements intelligence (QEOS Native default; external LLM when configured)
        provider = llm_provider or "qeos-native"
        if provider not in ("qeos-native", "qeos-hybrid"):
            parser = StudioInputParser(provider)
            cases_data = await parser.to_test_cases(source_type, content)
            req_output = {
                "test_scenarios": [c.get("title", "") for c in cases_data],
                "test_cases": cases_data,
                "coverage_matrix": {
                    "total_requirements": 1,
                    "covered_requirements": 1 if cases_data else 0,
                    "coverage_percentage": 100.0 if cases_data else 0.0,
                    "gaps": [],
                },
                "risk_analysis": {"level": "medium", "notes": f"Generated via {provider}"},
            }
        else:
            req_output = self.engine.generate(
                TaskType.REQUIREMENTS,
                {"content": content, "source_type": source_type},
            )

        run = AgentRunModel(
            project_id=project_id,
            agent_type=AgentType.REQUIREMENTS.value,
            status=AgentStatus.COMPLETED.value,
            input_data={"content": content, "source_type": source_type, "requirement_id": str(req.id)},
            output_data=req_output,
            llm_provider=provider,
            llm_model=llm_model or "qeos-intelligence-v1",
            completed_at=datetime.now(timezone.utc),
        )
        self.db.add(run)
        await self.db.flush()

        # Persist scenarios
        scenarios_saved = []
        for scenario_text in req_output.get("test_scenarios", []):
            sc = TestScenarioModel(
                project_id=project_id,
                description=scenario_text,
                agent_run_id=run.id,
            )
            self.db.add(sc)
            scenarios_saved.append(scenario_text)

        # Persist test cases
        cases_saved = []
        for tc in req_output.get("test_cases", []):
            case = TestCaseModel(
                project_id=project_id,
                title=tc.get("title", "Untitled"),
                description=tc.get("description", ""),
                steps=tc.get("steps", []),
                expected_results=tc.get("expected_results", []),
                priority=tc.get("priority", "medium"),
                tags=tc.get("tags", []),
                requirement_refs=tc.get("requirement_refs", [str(req.id)]),
                agent_run_id=run.id,
                status="generated",
            )
            self.db.add(case)
            cases_saved.append(case)

        await self.db.flush()

        # Coverage snapshot
        cm = req_output.get("coverage_matrix", {})
        coverage = CoverageSnapshotModel(
            project_id=project_id,
            total_requirements=cm.get("total_requirements", 1),
            covered_requirements=cm.get("covered_requirements", 1),
            coverage_percentage=cm.get("coverage_percentage", 100.0),
            gaps=cm.get("gaps", []),
            risk_analysis=req_output.get("risk_analysis"),
            agent_run_id=run.id,
        )
        self.db.add(coverage)

        # Test design phase
        design_output = None
        design_run = None
        if run_test_design:
            design_output = self.engine.generate(TaskType.TEST_DESIGN, req_output)
            design_run = AgentRunModel(
                project_id=project_id,
                agent_type=AgentType.TEST_DESIGN.value,
                status=AgentStatus.COMPLETED.value,
                input_data=req_output,
                output_data=design_output,
                llm_provider=llm_provider or "qeos-native",
                completed_at=datetime.now(timezone.utc),
            )
            self.db.add(design_run)
            await self.db.flush()

            # Create test suites from design
            for pack_key, suite_type in [("regression_pack", "regression"), ("smoke_pack", "smoke")]:
                pack = design_output.get(pack_key, {})
                if pack.get("test_ids"):
                    suite = TestSuiteModel(
                        project_id=project_id,
                        name=pack.get("name", suite_type.title()),
                        suite_type=suite_type,
                        test_case_ids=[str(c.id) for c in cases_saved],
                    )
                    self.db.add(suite)

        await self.db.flush()

        return {
            "requirement_id": str(req.id),
            "agent_run_id": str(run.id),
            "test_design_run_id": str(design_run.id) if design_run else None,
            "test_scenarios": scenarios_saved,
            "test_cases": [self._case_dict(c) for c in cases_saved],
            "coverage_matrix": cm,
            "risk_analysis": req_output.get("risk_analysis"),
            "test_design": design_output,
        }

    async def get_project_coverage(self, project_id: uuid.UUID) -> dict:
        result = await self.db.execute(
            select(CoverageSnapshotModel)
            .where(CoverageSnapshotModel.project_id == project_id)
            .order_by(CoverageSnapshotModel.created_at.desc())
            .limit(1)
        )
        snapshot = result.scalar_one_or_none()

        req_count = await self.db.scalar(
            select(func.count()).select_from(RequirementModel).where(RequirementModel.project_id == project_id)
        )
        case_count = await self.db.scalar(
            select(func.count()).select_from(TestCaseModel).where(TestCaseModel.project_id == project_id)
        )

        if snapshot:
            return {
                "total_requirements": snapshot.total_requirements,
                "covered_requirements": snapshot.covered_requirements,
                "coverage_percentage": snapshot.coverage_percentage,
                "gaps": snapshot.gaps,
                "risk_analysis": snapshot.risk_analysis,
                "requirement_count": req_count or 0,
                "test_case_count": case_count or 0,
                "updated_at": snapshot.created_at.isoformat(),
            }

        return {
            "total_requirements": req_count or 0,
            "covered_requirements": 0,
            "coverage_percentage": 0.0,
            "gaps": [],
            "requirement_count": req_count or 0,
            "test_case_count": case_count or 0,
        }

    def _case_dict(self, case: TestCaseModel) -> dict:
        return {
            "id": str(case.id),
            "title": case.title,
            "description": case.description,
            "steps": case.steps,
            "expected_results": case.expected_results,
            "priority": case.priority,
            "tags": case.tags,
            "requirement_refs": case.requirement_refs,
            "status": case.status,
        }

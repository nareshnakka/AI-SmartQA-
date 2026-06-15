"""Phase 5 — Live quality reports from persisted data."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    AutomationAssetModel,
    CoverageSnapshotModel,
    ExecutionRunModel,
    MonitoringEventModel,
    PerformanceAssetModel,
    PipelineRunModel,
    ProjectModel,
    RequirementModel,
    TestCaseModel,
)


class ReportsService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def platform_overview(self) -> dict:
        projects = await self._count(ProjectModel)
        requirements = await self._count(RequirementModel)
        test_cases = await self._count(TestCaseModel)
        automation = await self._count(AutomationAssetModel)
        performance = await self._count(PerformanceAssetModel)
        pipelines = await self._count(PipelineRunModel)
        executions = await self._count(ExecutionRunModel)
        monitoring_events = await self._count(MonitoringEventModel)

        coverage_avg = await self._avg_coverage()
        exec_stats = await self._execution_stats()
        pipeline_stats = await self._pipeline_stats()

        quality_score = self._quality_score(coverage_avg, automation, test_cases, exec_stats)
        automation_roi = round(test_cases / max(automation, 1) * 100) if test_cases else 0

        return {
            "quality_score": quality_score,
            "release_risk": self._release_risk(coverage_avg),
            "automation_roi_percent": min(automation_roi, 999),
            "avg_cycle_hours": await self._avg_cycle_hours(),
            "totals": {
                "projects": projects,
                "requirements": requirements,
                "test_cases": test_cases,
                "automation_assets": automation,
                "performance_assets": performance,
                "pipeline_runs": pipelines,
                "executions": executions,
                "monitoring_events": monitoring_events,
            },
            "coverage_average": coverage_avg,
            "execution_stats": exec_stats,
            "pipeline_stats": pipeline_stats,
            "tester_dashboard": {
                "pass_rate": exec_stats.get("pass_rate", 0),
                "tests_generated": test_cases,
                "executions_run": executions,
            },
            "engineering_dashboard": {
                "automation_coverage": round(automation / max(projects, 1), 1),
                "pipeline_success_rate": pipeline_stats.get("success_rate", 0),
                "failed_executions": exec_stats.get("failed", 0),
            },
            "executive_dashboard": {
                "quality_score": quality_score,
                "estimated_manual_hours_saved": test_cases * 2 + automation * 8,
                "automation_assets": automation,
                "production_events": monitoring_events,
            },
        }

    async def project_report(self, project_id: uuid.UUID) -> dict:
        project = await self.db.get(ProjectModel, project_id)
        if not project:
            raise ValueError("Project not found")

        req_count = await self._count_where(RequirementModel, RequirementModel.project_id == project_id)
        case_count = await self._count_where(TestCaseModel, TestCaseModel.project_id == project_id)
        auto_count = await self._count_where(AutomationAssetModel, AutomationAssetModel.project_id == project_id)

        cov_result = await self.db.execute(
            select(CoverageSnapshotModel)
            .where(CoverageSnapshotModel.project_id == project_id)
            .order_by(CoverageSnapshotModel.created_at.desc())
            .limit(1)
        )
        latest_cov = cov_result.scalar_one_or_none()

        exec_result = await self.db.execute(
            select(ExecutionRunModel)
            .where(ExecutionRunModel.project_id == project_id)
            .order_by(ExecutionRunModel.created_at.desc())
            .limit(10)
        )
        recent_execs = list(exec_result.scalars().all())

        coverage_pct = latest_cov.coverage_percentage if latest_cov else 0
        risk = (latest_cov.risk_analysis or {}).get("overall_risk_score", "unknown") if latest_cov else "unknown"

        return {
            "project_id": str(project_id),
            "project_name": project.name,
            "quality_score": self._quality_score(
                coverage_pct,
                auto_count,
                case_count,
                self._exec_stats_from_runs(recent_execs),
            ),
            "coverage_percentage": coverage_pct,
            "release_risk": risk,
            "requirements": req_count,
            "test_cases": case_count,
            "automation_assets": auto_count,
            "recent_executions": [
                {
                    "id": str(e.id),
                    "status": e.status,
                    "summary": e.summary,
                    "created_at": e.created_at.isoformat(),
                }
                for e in recent_execs
            ],
            "gaps": latest_cov.gaps if latest_cov else [],
        }

    async def _count(self, model) -> int:
        return await self.db.scalar(select(func.count()).select_from(model)) or 0

    async def _count_where(self, model, condition) -> int:
        return await self.db.scalar(select(func.count()).select_from(model).where(condition)) or 0

    async def _avg_coverage(self) -> float:
        result = await self.db.execute(
            select(func.avg(CoverageSnapshotModel.coverage_percentage))
        )
        return round(float(result.scalar() or 0), 1)

    async def _execution_stats(self) -> dict:
        result = await self.db.execute(select(ExecutionRunModel))
        runs = list(result.scalars().all())
        return self._exec_stats_from_runs(runs)

    def _exec_stats_from_runs(self, runs: list) -> dict:
        if not runs:
            return {"total": 0, "completed": 0, "failed": 0, "pass_rate": 0}
        completed = sum(1 for r in runs if r.status == "completed")
        failed = sum(1 for r in runs if r.status == "failed")
        return {
            "total": len(runs),
            "completed": completed,
            "failed": failed,
            "pass_rate": round(completed / len(runs) * 100, 1),
        }

    async def _pipeline_stats(self) -> dict:
        result = await self.db.execute(select(PipelineRunModel))
        runs = list(result.scalars().all())
        if not runs:
            return {"total": 0, "success_rate": 0}
        completed = sum(1 for r in runs if r.status == "completed")
        return {"total": len(runs), "success_rate": round(completed / len(runs) * 100, 1)}

    async def _avg_cycle_hours(self) -> float:
        result = await self.db.execute(
            select(ProjectModel.created_at, AutomationAssetModel.created_at)
            .join(AutomationAssetModel, AutomationAssetModel.project_id == ProjectModel.id)
            .limit(50)
        )
        rows = result.all()
        if not rows:
            return 0
        deltas = [(auto - proj).total_seconds() / 3600 for proj, auto in rows if auto and proj]
        return round(sum(deltas) / len(deltas), 1) if deltas else 0

    def _quality_score(self, coverage: float, automation: int, test_cases: int, exec_stats: dict) -> int:
        score = coverage * 0.4
        score += min(automation * 5, 25)
        score += min(test_cases * 0.5, 20)
        score += exec_stats.get("pass_rate", 0) * 0.15
        return min(int(score), 100)

    def _release_risk(self, coverage: float) -> str:
        if coverage >= 90:
            return "low"
        if coverage >= 70:
            return "medium"
        return "high"

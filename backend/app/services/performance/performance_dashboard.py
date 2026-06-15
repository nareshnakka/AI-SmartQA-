"""Performance test dashboard analytics and run detail (360° view)."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import PerformanceAssetModel, PerformanceRunModel, TestCaseModel


class PerformanceDashboardService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def overview(self, project_id) -> dict:
        runs = await self._list_runs(project_id)
        assets = await self._count_assets(project_id)
        test_cases = await self._count_test_cases(project_id)

        completed = [r for r in runs if r.status == "completed"]
        failed = [r for r in runs if r.status == "failed"]
        running = [r for r in runs if r.status == "running"]
        dry_run = [r for r in runs if r.status == "dry_run"]

        total_txn = 0
        avg_p95 = []
        total_rps = 0
        for r in completed + failed:
            dash = r.metrics if isinstance(r.metrics, dict) else {}
            summary = dash.get("summary", dash) if isinstance(dash, dict) else {}
            if summary.get("http_req_duration_p95"):
                avg_p95.append(summary["http_req_duration_p95"])
            total_rps += summary.get("http_reqs_rate", 0) or 0
            total_txn += (r.summary or {}).get("transactions", 0) or len(dash.get("transactions", []))

        pass_rate = round(len(completed) / max(len(runs), 1) * 100, 1)

        return {
            "totals": {
                "performance_assets": assets,
                "test_cases": test_cases,
                "total_runs": len(runs),
                "passed": len(completed),
                "failed": len(failed),
                "running": len(running),
                "dry_run": len(dry_run),
                "pass_rate": pass_rate,
                "avg_p95_ms": round(sum(avg_p95) / len(avg_p95), 1) if avg_p95 else 0,
                "total_throughput_rps": round(total_rps, 2),
                "transactions_tested": total_txn,
            },
            "pie_chart": {
                "passed": len(completed),
                "failed": len(failed),
                "running": len(running),
            },
            "timeline": [
                {
                    "id": str(r.id),
                    "name": await self._run_label(r),
                    "status": r.status,
                    "workload_profile": r.workload_profile,
                    "p95_ms": self._run_p95(r),
                    "throughput_rps": self._run_rps(r),
                    "transactions": (r.summary or {}).get("transactions", 0),
                    "started_at": r.created_at.isoformat(),
                    "ended_at": r.completed_at.isoformat() if r.completed_at else None,
                    "agent": (r.summary or {}).get("agent", "localhost"),
                }
                for r in runs[:50]
            ],
            "recent_runs": [self._run_card(r) for r in runs[:10]],
        }

    async def run_detail(self, project_id, run_id) -> dict | None:
        run = await self.db.get(PerformanceRunModel, run_id)
        if not run or run.project_id != project_id:
            return None

        asset = await self.db.get(PerformanceAssetModel, run.asset_id)
        dash = run.metrics if isinstance(run.metrics, dict) else {}

        return {
            "run": {
                "id": str(run.id),
                "project_id": str(run.project_id),
                "asset_id": str(run.asset_id),
                "asset_name": asset.name if asset else "Unknown",
                "tool": asset.tool if asset else "k6",
                "workload_profile": run.workload_profile,
                "status": run.status,
                "summary": run.summary,
                "created_at": run.created_at.isoformat(),
                "completed_at": run.completed_at.isoformat() if run.completed_at else None,
                "agent": (run.summary or {}).get("agent", "QEOS Localhost Agent"),
                "logs_preview": (run.logs or "")[:2000],
            },
            "dashboard": dash,
            "summary": dash.get("summary", {}),
            "transactions": dash.get("transactions", []),
            "timeline": dash.get("timeline", []),
            "percentiles": dash.get("percentiles", {}),
            "sla": dash.get("sla", {}),
            "errors": dash.get("errors", []),
            "scenarios": asset.scenarios if asset else [],
        }

    def _run_p95(self, run: PerformanceRunModel) -> float:
        dash = run.metrics if isinstance(run.metrics, dict) else {}
        return dash.get("summary", {}).get("http_req_duration_p95", 0) or 0

    def _run_rps(self, run: PerformanceRunModel) -> float:
        dash = run.metrics if isinstance(run.metrics, dict) else {}
        return dash.get("summary", {}).get("http_reqs_rate", 0) or 0

    def _run_card(self, run: PerformanceRunModel) -> dict:
        return {
            "id": str(run.id),
            "status": run.status,
            "workload_profile": run.workload_profile,
            "p95_ms": self._run_p95(run),
            "created_at": run.created_at.isoformat(),
        }

    async def _run_label(self, run: PerformanceRunModel) -> str:
        asset = await self.db.get(PerformanceAssetModel, run.asset_id)
        return f"{asset.name if asset else 'Run'} — {run.workload_profile}"

    async def _list_runs(self, project_id) -> list[PerformanceRunModel]:
        result = await self.db.execute(
            select(PerformanceRunModel)
            .where(PerformanceRunModel.project_id == project_id)
            .order_by(PerformanceRunModel.created_at.desc())
        )
        return list(result.scalars().all())

    async def _count_assets(self, project_id) -> int:
        result = await self.db.execute(
            select(PerformanceAssetModel).where(PerformanceAssetModel.project_id == project_id)
        )
        return len(list(result.scalars().all()))

    async def _count_test_cases(self, project_id) -> int:
        result = await self.db.execute(
            select(TestCaseModel).where(TestCaseModel.project_id == project_id)
        )
        return len(list(result.scalars().all()))

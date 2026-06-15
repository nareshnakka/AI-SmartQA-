"""Execution dashboard analytics and export."""

import csv
import io
import json
import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ExecutionRunModel, PerformanceRunModel, TestCaseModel


class ExecutionDashboardService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def dashboard(
        self,
        project_id: uuid.UUID,
        sprint: str | None = None,
        release: str | None = None,
    ) -> dict:
        runs = await self._filter_runs(project_id, sprint, release)
        perf_runs = await self._filter_perf_runs(project_id, sprint, release)

        passed = failed = running = 0
        total_steps_passed = total_steps_failed = 0
        by_sprint: dict[str, dict] = {}
        by_release: dict[str, dict] = {}
        timeline = []

        for run in runs:
            s = run.summary or {}
            p = s.get("passed", 0)
            f = s.get("failed", 0)
            if run.status == "running":
                running += 1
            else:
                passed += p
                failed += f
            for r in run.results or []:
                for step in r.get("steps") or []:
                    if step.get("status") == "passed":
                        total_steps_passed += 1
                    elif step.get("status") == "failed":
                        total_steps_failed += 1

            sp = run.sprint or "Unassigned"
            rel = run.release or "Unassigned"
            by_sprint.setdefault(sp, {"passed": 0, "failed": 0, "runs": 0})
            by_release.setdefault(rel, {"passed": 0, "failed": 0, "runs": 0})
            by_sprint[sp]["passed"] += p
            by_sprint[sp]["failed"] += f
            by_sprint[sp]["runs"] += 1
            by_release[rel]["passed"] += p
            by_release[rel]["failed"] += f
            by_release[rel]["runs"] += 1

            timeline.append({
                "id": str(run.id),
                "name": run.run_name or run.mode,
                "status": run.status,
                "passed": p,
                "failed": f,
                "started_at": run.created_at.isoformat(),
                "ended_at": run.completed_at.isoformat() if run.completed_at else None,
                "sprint": run.sprint,
                "release": run.release,
                "type": run.asset_type,
            })

        tc_count = await self.db.scalar(
            select(func.count()).select_from(TestCaseModel).where(TestCaseModel.project_id == project_id)
        ) or 0

        total = passed + failed
        pass_rate = round(passed / total * 100, 1) if total else 0

        return {
            "totals": {
                "test_cases": tc_count,
                "execution_runs": len(runs),
                "performance_runs": len(perf_runs),
                "passed": passed,
                "failed": failed,
                "running": running,
                "pass_rate": pass_rate,
                "steps_passed": total_steps_passed,
                "steps_failed": total_steps_failed,
            },
            "pie_chart": {
                "passed": passed,
                "failed": failed,
                "running": running,
            },
            "by_sprint": [{"sprint": k, **v} for k, v in sorted(by_sprint.items())],
            "by_release": [{"release": k, **v} for k, v in sorted(by_release.items())],
            "timeline": timeline[:50],
            "recent_runs": [self._run_summary(r) for r in runs[:10]],
        }

    async def _filter_runs(
        self, project_id: uuid.UUID, sprint: str | None, release: str | None
    ) -> list[ExecutionRunModel]:
        q = select(ExecutionRunModel).where(ExecutionRunModel.project_id == project_id)
        if sprint:
            q = q.where(ExecutionRunModel.sprint == sprint)
        if release:
            q = q.where(ExecutionRunModel.release == release)
        q = q.order_by(ExecutionRunModel.created_at.desc())
        result = await self.db.execute(q)
        return list(result.scalars().all())

    async def _filter_perf_runs(
        self, project_id: uuid.UUID, sprint: str | None, release: str | None
    ) -> list[PerformanceRunModel]:
        q = select(PerformanceRunModel).where(PerformanceRunModel.project_id == project_id)
        result = await self.db.execute(q.order_by(PerformanceRunModel.created_at.desc()))
        return list(result.scalars().all())

    def _run_summary(self, run: ExecutionRunModel) -> dict:
        return {
            "id": str(run.id),
            "run_name": run.run_name,
            "status": run.status,
            "summary": run.summary,
            "sprint": run.sprint,
            "release": run.release,
            "started_at": run.created_at.isoformat(),
            "ended_at": run.completed_at.isoformat() if run.completed_at else None,
            "test_count": len(run.test_case_ids or []),
        }


def export_run_report(run: dict, fmt: str = "json") -> tuple[str, str, str]:
    """Return (content, media_type, filename)."""
    run_id = run.get("id", "report")[:8]
    if fmt == "json":
        return json.dumps(run, indent=2), "application/json", f"execution-{run_id}.json"
    if fmt == "csv":
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(["Test Case", "Status", "Step", "Step Status", "Expected", "Has Video"])
        for r in run.get("results") or []:
            title = r.get("title") or r.get("file", "")
            for step in r.get("steps") or []:
                w.writerow([
                    title,
                    r.get("status", ""),
                    step.get("description", ""),
                    step.get("status", ""),
                    step.get("expected", ""),
                    r.get("has_video", False),
                ])
        return buf.getvalue(), "text/csv", f"execution-{run_id}.csv"
    # html
    rows = ""
    for r in run.get("results") or []:
        steps_html = "".join(
            f"<li class='{s.get('status')}'>{s.get('order')}. {s.get('description')} — <strong>{s.get('status')}</strong></li>"
            for s in (r.get("steps") or [])
        )
        video = ""
        if r.get("has_video") and r.get("video_url"):
            video = f"<video controls width='480' src='{r['video_url']}'></video>"
        rows += f"""<div class='tc'><h3>{r.get('title','')} — {r.get('status')}</h3><ol>{steps_html}</ol>{video}</div>"""
    summary = run.get("summary") or {}
    html = f"""<!DOCTYPE html><html><head><meta charset='utf-8'><title>Execution Report</title>
<style>body{{font-family:system-ui;margin:2rem}} .passed{{color:green}} .failed{{color:red}} .tc{{border:1px solid #ddd;padding:1rem;margin:1rem 0;border-radius:8px}}</style></head>
<body><h1>QEOS Execution Report</h1>
<p>Status: {run.get('status')} | Passed: {summary.get('passed',0)} | Failed: {summary.get('failed',0)}</p>
<p>Started: {run.get('created_at')} | Ended: {run.get('completed_at') or '—'}</p>
{rows}</body></html>"""
    return html, "text/html", f"execution-{run_id}.html"

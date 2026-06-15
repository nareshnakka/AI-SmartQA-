"""Background performance test worker."""

import asyncio
import uuid

import structlog

from app.db.session import AsyncSessionLocal

logger = structlog.get_logger()
_running: set[uuid.UUID] = set()


def is_perf_run_active(run_id: uuid.UUID) -> bool:
    return run_id in _running


def enqueue_performance_run(run_id: uuid.UUID) -> None:
    if run_id in _running:
        return
    _running.add(run_id)
    asyncio.create_task(_execute(run_id), name=f"qeos-perf-{run_id}")


async def _execute(run_id: uuid.UUID) -> None:
    from datetime import datetime, timezone

    from app.db.models import PerformanceRunModel
    from app.services.performance.execution import run_k6
    from app.services.performance.service import PerformanceService

    try:
        async with AsyncSessionLocal() as db:
            run = await db.get(PerformanceRunModel, run_id)
            if not run:
                return

            svc = PerformanceService(db)
            asset = await svc.get_asset(run.asset_id)
            if not asset:
                run.status = "failed"
                run.logs = "Asset not found"
                run.completed_at = datetime.now(timezone.utc)
                await db.commit()
                return

            main_script = next(
                (s for s in (asset.scripts or []) if s.get("type") in ("k6", "script") or s["path"].endswith(".js")),
                (asset.scripts or [{}])[0],
            )
            data_files = [s for s in (asset.scripts or []) if s.get("type") == "data" or "data/" in s.get("path", "")]

            async def progress(p: dict):
                run.summary = {**(run.summary or {}), "progress": p}
                await db.flush()

            duration = "30s" if run.workload_profile == "smoke" else "60s"
            outcome = await run_k6(main_script.get("content", ""), data_files, duration_override=duration, on_progress=progress)

            dashboard = outcome.get("dashboard", {})
            run.status = outcome.get("status", "completed")
            run.metrics = dashboard
            run.summary = {
                **(run.summary or {}),
                "exit_code": outcome.get("exit_code"),
                "available": outcome.get("available", True),
                "agent": (run.summary or {}).get("agent", "localhost"),
                "progress": {"percent": 100, "phase": "Complete"},
                "passed": run.status == "completed",
                "transactions": len(dashboard.get("transactions", [])),
            }
            run.logs = (outcome.get("stdout", "") + outcome.get("stderr", ""))[:50000]
            run.completed_at = datetime.now(timezone.utc)
            await db.commit()
    except Exception as e:
        logger.exception("performance_run_failed", run_id=str(run_id), error=str(e))
        try:
            async with AsyncSessionLocal() as db:
                run = await db.get(PerformanceRunModel, run_id)
                if run and run.status == "running":
                    run.status = "failed"
                    run.logs = (run.logs or "") + f"\nError: {e}"
                    run.completed_at = datetime.now(timezone.utc)
                    await db.commit()
        except Exception:
            pass
    finally:
        _running.discard(run_id)

"""Background execution worker — runs automation outside the HTTP request."""

import asyncio
import uuid

import structlog

from app.db.session import AsyncSessionLocal

logger = structlog.get_logger()

_running: set[uuid.UUID] = set()
_execution_lock = asyncio.Lock()


def is_run_active(run_id: uuid.UUID) -> bool:
    return run_id in _running


def enqueue_execution(
    run_id: uuid.UUID,
    project_id: uuid.UUID,
    asset_id: uuid.UUID,
    mode: str,
    apply_healing: bool,
) -> None:
    _running.add(run_id)
    asyncio.create_task(
        _execute(run_id, project_id, asset_id, mode, apply_healing),
        name=f"qeos-exec-{run_id}",
    )


def enqueue_batch_execution(
    run_id: uuid.UUID,
    project_id: uuid.UUID,
    test_case_ids: list[uuid.UUID],
    asset_id: uuid.UUID | None,
    mode: str,
    apply_healing: bool,
    base_url: str,
    run_type: str,
    performance_asset_id: uuid.UUID | None,
    framework: str = "playwright",
) -> None:
    _running.add(run_id)
    asyncio.create_task(
        _execute_batch(
            run_id, project_id, test_case_ids, asset_id, mode, apply_healing,
            base_url, run_type, performance_asset_id, framework,
        ),
        name=f"qeos-batch-{run_id}",
    )


async def _execute(
    run_id: uuid.UUID,
    project_id: uuid.UUID,
    asset_id: uuid.UUID,
    mode: str,
    apply_healing: bool,
) -> None:
    from app.services.execution import ExecutionService

    try:
        async with _execution_lock:
            async with AsyncSessionLocal() as db:
                svc = ExecutionService(db)
                await svc.execute_run(run_id, project_id, asset_id, mode, apply_healing)
                await db.commit()
    except Exception as e:
        logger.exception("execution_background_failed", run_id=str(run_id), error=str(e))
        await _fail_run(run_id, e)
    finally:
        _running.discard(run_id)


async def _execute_batch(
    run_id: uuid.UUID,
    project_id: uuid.UUID,
    test_case_ids: list[uuid.UUID],
    asset_id: uuid.UUID | None,
    mode: str,
    apply_healing: bool,
    base_url: str,
    run_type: str,
    performance_asset_id: uuid.UUID | None,
    framework: str = "playwright",
) -> None:
    from app.services.execution import ExecutionService

    try:
        async with _execution_lock:
            async with AsyncSessionLocal() as db:
                svc = ExecutionService(db)
                await svc.execute_batch_run(
                    run_id, project_id, test_case_ids, asset_id, mode, apply_healing,
                    base_url, run_type, performance_asset_id, framework,
                )
                await db.commit()
    except Exception as e:
        logger.exception("batch_execution_failed", run_id=str(run_id), error=str(e))
        await _fail_run(run_id, e)
    finally:
        _running.discard(run_id)


async def _fail_run(run_id: uuid.UUID, error: Exception) -> None:
    try:
        async with AsyncSessionLocal() as db:
            from app.db.models import ExecutionRunModel
            from datetime import datetime, timezone

            run = await db.get(ExecutionRunModel, run_id)
            if run and run.status == "running":
                run.status = "failed"
                run.logs = (run.logs or "") + f"\nBackground execution error: {error}"
                run.completed_at = datetime.now(timezone.utc)
                await db.commit()
            elif run and run.status in ("completed", "failed") and not run.results:
                # Preserve completed run but append diagnostic if results missing
                run.logs = (run.logs or "") + f"\nNote: {error}"
                await db.commit()
    except Exception:
        pass

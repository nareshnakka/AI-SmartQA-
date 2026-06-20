"""Background discovery worker."""

import uuid

import structlog

from app.db.session import AsyncSessionLocal

logger = structlog.get_logger()

_running: set[uuid.UUID] = set()
_cancel_requested: set[uuid.UUID] = set()
_nav_clear_requested: set[uuid.UUID] = set()


def is_discovery_cancel_requested(session_id: uuid.UUID) -> bool:
    return session_id in _cancel_requested


def request_cancel_discovery(session_id: uuid.UUID) -> None:
    _cancel_requested.add(session_id)


def clear_cancel_discovery(session_id: uuid.UUID) -> None:
    _cancel_requested.discard(session_id)


def is_nav_clear_requested(session_id: uuid.UUID) -> bool:
    return session_id in _nav_clear_requested


def request_nav_clear(session_id: uuid.UUID) -> None:
    _nav_clear_requested.add(session_id)


def clear_nav_clear_request(session_id: uuid.UUID) -> None:
    _nav_clear_requested.discard(session_id)


def enqueue_discovery(
    session_id: uuid.UUID,
    project_id: uuid.UUID,
    base_url: str,
    mode: str,
    requirements: str | None,
    username: str | None,
    password: str | None,
    name: str | None,
    credentials_hint: str | None,
) -> None:
    if session_id in _running:
        return
    _running.add(session_id)
    import asyncio

    asyncio.create_task(
        _run(session_id, project_id, base_url, mode, requirements, username, password, name, credentials_hint),
        name=f"qeos-discovery-{session_id}",
    )


async def _run(
    session_id: uuid.UUID,
    project_id: uuid.UUID,
    base_url: str,
    mode: str,
    requirements: str | None,
    username: str | None,
    password: str | None,
    name: str | None,
    credentials_hint: str | None,
) -> None:
    from app.services.discovery import DiscoveryService

    try:
        async with AsyncSessionLocal() as db:
            svc = DiscoveryService(db)
            await svc.execute_discovery(
                session_id, project_id, base_url, mode, requirements,
                username, password, name, credentials_hint,
            )
            await db.commit()
    except Exception as e:
        err = str(e) or type(e).__name__
        logger.exception("discovery_background_failed", session_id=str(session_id), error=err)
        try:
            async with AsyncSessionLocal() as db:
                from app.db.models import DiscoverySessionModel
                from datetime import datetime, timezone

                session = await db.get(DiscoverySessionModel, session_id)
                if session and session.status == "running":
                    session.status = "failed"
                    session.navigation_log = (session.navigation_log or []) + [{
                        "type": "error",
                        "message": f"Discovery failed: {err}",
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    }]
                    session.completed_at = datetime.now(timezone.utc)
                    await db.commit()
        except Exception:
            pass
    finally:
        _running.discard(session_id)
        clear_cancel_discovery(session_id)
        clear_nav_clear_request(session_id)

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.session import get_db
from app.services.monitoring import MonitoringService
from app.services.monitoring_adapters import parse_datadog, parse_sentry

router = APIRouter(prefix="/monitoring", tags=["Monitoring"])


class IngestEventRequest(BaseModel):
    event_type: str
    title: str
    severity: str = "info"
    source: str = "custom"
    project_id: UUID | None = None
    payload: dict | None = None


@router.get("/connectors")
async def connector_status():
    return {
        "connectors": [
            {
                "id": "datadog",
                "name": "Datadog",
                "webhook_path": "/api/v1/monitoring/webhooks/datadog",
                "configured": bool(settings.datadog_webhook_secret),
            },
            {
                "id": "sentry",
                "name": "Sentry",
                "webhook_path": "/api/v1/monitoring/webhooks/sentry",
                "configured": bool(settings.sentry_webhook_secret),
            },
            {
                "id": "custom",
                "name": "Custom",
                "webhook_path": "/api/v1/monitoring/events",
                "configured": True,
            },
        ]
    }


@router.post("/events")
async def ingest_event(body: IngestEventRequest, db: AsyncSession = Depends(get_db)):
    svc = MonitoringService(db)
    event = await svc.ingest(
        body.event_type,
        body.title,
        body.severity,
        body.source,
        body.project_id,
        body.payload,
    )
    return svc.to_dict(event)


@router.get("/events")
async def list_events(project_id: UUID | None = None, db: AsyncSession = Depends(get_db)):
    svc = MonitoringService(db)
    events = await svc.list_events(project_id)
    return [svc.to_dict(e) for e in events]


def _verify_secret(header: str | None, expected: str) -> None:
    if not expected:
        return
    if header != expected:
        raise HTTPException(401, "Invalid webhook secret")


@router.post("/webhooks/datadog")
async def datadog_webhook(request: Request, db: AsyncSession = Depends(get_db)):
    _verify_secret(request.headers.get("X-Datadog-Webhook-Secret"), settings.datadog_webhook_secret)
    payload = await request.json()
    svc = MonitoringService(db)
    ingested = []
    for item in parse_datadog(payload):
        event = await svc.ingest(
            item["event_type"],
            item["title"],
            item["severity"],
            "datadog",
            None,
            item["payload"],
        )
        ingested.append(svc.to_dict(event))
    return {"ingested": len(ingested), "events": ingested}


@router.post("/webhooks/sentry")
async def sentry_webhook(request: Request, db: AsyncSession = Depends(get_db)):
    secret = request.headers.get("X-Sentry-Token") or request.headers.get("Sentry-Hook-Signature")
    _verify_secret(secret, settings.sentry_webhook_secret)

    payload = await request.json()
    svc = MonitoringService(db)
    ingested = []
    for item in parse_sentry(payload):
        event = await svc.ingest(
            item["event_type"],
            item["title"],
            item["severity"],
            "sentry",
            None,
            item["payload"],
        )
        ingested.append(svc.to_dict(event))
    return {"ingested": len(ingested), "events": ingested}

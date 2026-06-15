"""QEOS Global Copilot API."""

import json
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.services.copilot.agent import CopilotAgent, get_or_create_session
from app.services.copilot.tools import TOOL_DEFINITIONS

router = APIRouter(prefix="/copilot", tags=["QEOS Copilot"])


class CopilotChatRequest(BaseModel):
    message: str
    session_id: str | None = None
    project_id: UUID | None = None
    page_context: str | None = None


@router.get("/status")
async def copilot_status():
    from app.services.copilot.agent import _select_copilot_provider
    from app.llm.router import get_llm_router

    provider, model = _select_copilot_provider()
    return {
        "name": "QEOS Copilot",
        "description": "Global AI assistant — run, view, suggest, and drive the entire platform",
        "provider": provider,
        "model": model,
        "tools_count": len(TOOL_DEFINITIONS),
        "providers_available": get_llm_router().list_providers(),
        "streaming": provider == "openai",
    }


@router.get("/tools")
async def list_copilot_tools():
    return {"tools": [{"name": t["name"], "description": t["description"]} for t in TOOL_DEFINITIONS]}


@router.post("/chat")
async def copilot_chat(body: CopilotChatRequest, db: AsyncSession = Depends(get_db)):
    agent = CopilotAgent(db)
    pid = str(body.project_id) if body.project_id else None
    return await agent.chat(body.message, body.session_id, pid, body.page_context)


@router.post("/chat/stream")
async def copilot_chat_stream(body: CopilotChatRequest, db: AsyncSession = Depends(get_db)):
    agent = CopilotAgent(db)
    pid = str(body.project_id) if body.project_id else None

    async def event_stream():
        async for event in agent.stream_chat(body.message, body.session_id, pid, body.page_context):
            yield f"data: {json.dumps(event, default=str)}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )


@router.get("/sessions/{session_id}")
async def get_session(session_id: str):
    session = get_or_create_session(session_id, None)
    return {
        "id": session.id,
        "project_id": session.project_id,
        "messages": [{"role": m.role, "content": m.content, "tool_calls": m.tool_calls} for m in session.messages],
    }

from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app.config import settings
from app.intelligence.engine import TaskType, get_intelligence_engine
from app.intelligence.hybrid import QEOSHybridProvider
from app.intelligence.knowledge_base import TEST_PATTERNS
from app.intelligence.training_collector import get_training_collector
from app.llm.router import get_llm_router

router = APIRouter(prefix="/intelligence", tags=["QEOS Intelligence"])


class GenerateRequirementsRequest(BaseModel):
    content: str
    source_type: str = "user_story"


class HybridGenerateRequest(BaseModel):
    content: str
    source_type: str = "user_story"


@router.get("/status")
async def intelligence_status():
    engine = get_intelligence_engine()
    llm_router = get_llm_router()
    collector = get_training_collector()
    hybrid = QEOSHybridProvider()

    return {
        "engine": "QEOS Native Intelligence Engine (QNIE)",
        "version": engine.VERSION,
        "mode": settings.default_llm_provider,
        "external_llm_required": False,
        "pattern_count": len(TEST_PATTERNS),
        "hybrid_available": hybrid._ollama_available_sync(),
        "neural_model": settings.ollama_model if hybrid._ollama_available_sync() else None,
        "training_collection": collector.get_stats(),
        "capabilities": [
            "Requirement parsing (user stories, BDD, BRD)",
            "Test scenario and test case generation",
            f"{len(TEST_PATTERNS)} domain testing patterns",
            "Risk analysis and coverage matrix",
            "Hybrid mode (native + Ollama neural enhancement)",
            "Automatic training data collection",
            "Test design, automation, performance, self-healing, defect analysis",
        ],
        "available_providers": llm_router.list_providers(),
    }


@router.post("/generate/requirements")
async def generate_requirements(body: GenerateRequirementsRequest):
    engine = get_intelligence_engine()
    return engine.generate(
        TaskType.REQUIREMENTS,
        {"content": body.content, "source_type": body.source_type},
    )


@router.post("/generate/hybrid")
async def generate_hybrid(body: HybridGenerateRequest):
    """Generate using hybrid mode — native engine + optional neural enhancement."""
    from app.llm.base import LLMMessage, MessageRole

    hybrid = QEOSHybridProvider()
    messages = [
        LLMMessage(
            role=MessageRole.SYSTEM,
            content="You are the QEOS Requirements Agent. Generate test scenarios and test cases.",
        ),
        LLMMessage(
            role=MessageRole.USER,
            content=f"Source type: {body.source_type}\n\nRequirements:\n{body.content}",
        ),
    ]
    response = await hybrid.complete(messages, model="qeos-hybrid-v1", temperature=0.3)
    import json
    return json.loads(response.content)


@router.get("/patterns")
async def list_patterns():
    return {
        "total": len(TEST_PATTERNS),
        "patterns": [
            {
                "name": p.name,
                "category": p.category,
                "priority": p.priority,
                "tags": p.tags,
                "keywords": p.trigger_keywords[:5],
            }
            for p in TEST_PATTERNS
        ],
    }


# --- Training Data ---

@router.get("/training/stats")
async def training_stats():
    return get_training_collector().get_stats()


@router.get("/training/records")
async def training_records(limit: int = 50):
    records = get_training_collector().load_all()
    return {"total": len(records), "records": records[-limit:]}


@router.post("/training/export")
async def training_export():
    path = get_training_collector().export_jsonl()
    return {"exported_to": str(path), "records": get_training_collector().get_stats()["total_records"]}


@router.get("/training/download")
async def training_download():
    export_path = get_training_collector().export_jsonl()
    if not export_path.exists():
        return {"error": "No training data collected yet"}
    return FileResponse(
        path=export_path,
        filename="qeos_training_data.jsonl",
        media_type="application/jsonl",
    )


@router.delete("/training/clear")
async def training_clear():
    count = get_training_collector().clear()
    return {"cleared": count}

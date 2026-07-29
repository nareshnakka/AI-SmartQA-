from fastapi import APIRouter

from app.llm.router import get_llm_router

router = APIRouter(prefix="/llm", tags=["LLM"])


@router.get("/providers")
async def list_llm_providers():
    router_instance = get_llm_router()
    return {"providers": router_instance.list_providers()}


@router.get("/discovery-advisor-status")
async def discovery_advisor_status():
    from app.services.llm_discovery_advisor import get_llm_discovery_status

    return await get_llm_discovery_status()

from fastapi import APIRouter

from app.llm.router import get_llm_router

router = APIRouter(prefix="/llm", tags=["LLM"])


@router.get("/providers")
async def list_llm_providers():
    router_instance = get_llm_router()
    return {"providers": router_instance.list_providers()}

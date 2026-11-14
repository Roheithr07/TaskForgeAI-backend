from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional
from app.core.config import settings
from app.agents.llm import get_llm

router = APIRouter()


class LLMTestRequest(BaseModel):
    prompt: Optional[str] = "Hello TaskForge, test LLM inference and response latency."


@router.post("/llm/test")
async def test_llm_connection(req: LLMTestRequest):
    if not settings.is_groq_configured:
        return {
            "status": "heuristic_fallback_ready",
            "message": "Groq API key not set or placeholder. Operating in autonomous heuristic and deterministic fallback mode.",
            "provider": "Mock/Heuristic",
            "configured": False
        }

    llm = get_llm()
    if not llm:
        return {
            "status": "error",
            "message": "Groq LLM client could not be initialized.",
            "configured": False
        }

    try:
        response = await llm.ainvoke([{"role": "user", "content": req.prompt}])
        return {
            "status": "connected",
            "provider": "Groq",
            "model": settings.GROQ_MODEL,
            "response": response.content,
            "configured": True
        }
    except Exception as e:
        return {
            "status": "failed",
            "error": str(e),
            "provider": "Groq",
            "configured": True
        }


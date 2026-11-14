import os
import json
from typing import Optional, Any
from app.core.config import settings


def get_llm():
    """
    Returns configured ChatGroq instance if GROQ_API_KEY is available,
    otherwise returns None for structured heuristic planning.
    """
    if settings.is_groq_configured:
        try:
            from langchain_groq import ChatGroq
            return ChatGroq(
                groq_api_key=settings.GROQ_API_KEY,
                model_name=settings.GROQ_MODEL,
                temperature=0.2,
            )
        except Exception as e:
            print(f"[Warning] Failed to initialize ChatGroq: {e}. Falling back to heuristic engine.")
            return None
    return None


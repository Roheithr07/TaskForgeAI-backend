import os
import asyncio
import aiosqlite
from typing import Optional, List, Dict, Any
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

CHECKPOINT_DB_PATH = os.getenv(
    "CHECKPOINT_DB_PATH",
    os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "taskforge_checkpoints.sqlite")
)
os.makedirs(os.path.dirname(os.path.abspath(CHECKPOINT_DB_PATH)), exist_ok=True)

_loop_savers: Dict[asyncio.AbstractEventLoop, AsyncSqliteSaver] = {}


async def get_async_checkpointer() -> AsyncSqliteSaver:
    """
    Returns an AsyncSqliteSaver instance tied to the active asyncio event loop.
    Ensures safe reuse across FastAPI requests, worker loops, and test scopes.
    """
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = asyncio.get_event_loop()

    saver = _loop_savers.get(loop)
    if saver is None:
        conn = await aiosqlite.connect(CHECKPOINT_DB_PATH)
        saver = AsyncSqliteSaver(conn)
        await saver.setup()
        _loop_savers[loop] = saver

    return saver


async def list_thread_checkpoints(thread_id: str, limit: int = 20) -> List[Dict[str, Any]]:
    """
    Safely retrieves metadata for checkpoints associated with thread_id.
    Never exposes internal sensitive secrets.
    """
    saver = await get_async_checkpointer()
    config = {"configurable": {"thread_id": thread_id}}
    checkpoints = []

    try:
        async for cp in saver.alist(config, limit=limit):
            metadata = getattr(cp, "metadata", {}) or {}
            cp_dict = getattr(cp, "checkpoint", {}) or {}
            checkpoints.append({
                "checkpoint_id": cp_dict.get("id") if isinstance(cp_dict, dict) else str(getattr(cp, "checkpoint_id", "")),
                "parent_checkpoint_id": str(getattr(cp, "parent_checkpoint_id", "")),
                "step": metadata.get("step", 0),
                "source": metadata.get("source", "loop"),
                "timestamp": cp_dict.get("ts", None) if isinstance(cp_dict, dict) else None
            })
    except Exception as e:
        print(f"[Checkpointer] Error listing checkpoints for {thread_id}: {e}")

    return checkpoints


# Alias for compatibility
get_checkpointer = get_async_checkpointer

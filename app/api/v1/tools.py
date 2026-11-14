from typing import List, Dict, Any
from fastapi import APIRouter, HTTPException
from app.tools.registry import registry
from app.schemas.tool import ToolInfoResponse

router = APIRouter(prefix="/tools", tags=["Tools"])


@router.get("", response_model=List[ToolInfoResponse])
def list_available_tools():
    return registry.list_tools()


@router.get("/{name}", response_model=ToolInfoResponse)
def get_tool_info(name: str):
    tool = registry.get_tool(name)
    if not tool:
        raise HTTPException(status_code=404, detail=f"Tool '{name}' not found.")
    return tool.get_info()


@router.post("/{name}/execute")
async def execute_tool_directly(name: str, payload: Dict[str, Any]):
    """Direct sandboxed tool execution endpoint."""
    tool = registry.get_tool(name)
    if not tool:
        raise HTTPException(status_code=404, detail=f"Tool '{name}' not found.")
    if tool.is_sensitive:
        raise HTTPException(
            status_code=403, 
            detail=f"Tool '{name}' is marked sensitive and requires workflow graph supervisor authorization."
        )
    try:
        return await registry.execute_tool(name, payload)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

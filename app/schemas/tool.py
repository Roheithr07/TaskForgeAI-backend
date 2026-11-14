from typing import Dict, Any, Optional
from pydantic import BaseModel, ConfigDict


class ToolInfoResponse(BaseModel):
    name: str
    description: str
    provider: str = "internal"
    connection_status: str = "ready"
    permission_level: str = "PUBLIC"
    is_sensitive: bool
    requires_approval: bool
    timeout_seconds: float = 15.0
    max_retries: int = 3
    input_schema: Dict[str, Any]
    output_schema: Dict[str, Any]
    stats: Optional[Dict[str, Any]] = None

    model_config = ConfigDict(from_attributes=True)

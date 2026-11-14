from typing import Optional, Dict, Any
from pydantic import BaseModel, ConfigDict
from datetime import datetime


class ExecutionLogResponse(BaseModel):
    id: str
    workflow_id: str
    step_id: Optional[str] = None
    actor: Optional[str] = "system"
    level: str
    event: str
    message: str
    outcome: Optional[str] = "SUCCESS"
    details: Optional[Dict[str, Any]] = None
    timestamp: datetime

    model_config = ConfigDict(from_attributes=True)


class ExecutionSessionResponse(BaseModel):
    workflow_id: str
    workflow_title: str
    status: str
    total_steps: int
    completed_steps: int
    logs_count: int

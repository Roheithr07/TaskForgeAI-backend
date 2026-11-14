from typing import Optional, Dict, Any
from pydantic import BaseModel, ConfigDict
from datetime import datetime


class ApprovalResponse(BaseModel):
    id: str
    workflow_id: str
    step_id: str
    requesting_user: str = "operator@taskforge.ai"
    assigned_reviewer: Optional[str] = "REVIEWER"
    tool_name: str
    action_description: str
    payload_preview: Optional[Dict[str, Any]] = None
    payload_hash: Optional[str] = None
    risk_level: str = "HIGH"
    status: str
    expires_at: Optional[datetime] = None
    reviewed_at: Optional[datetime] = None
    reviewed_by: Optional[str] = None
    comment: Optional[str] = None
    execution_status: str = "pending"
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ApprovalActionRequest(BaseModel):
    comment: Optional[str] = None
    reviewed_by: Optional[str] = None

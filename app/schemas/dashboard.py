from typing import List, Optional, Dict, Any
from pydantic import BaseModel, ConfigDict
from datetime import datetime


class RecentWorkflowItem(BaseModel):
    id: str
    title: str
    status: str
    total_steps: int
    completed_steps: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class RecentActivityItem(BaseModel):
    id: str
    workflow_id: str
    workflow_title: Optional[str] = None
    step_id: Optional[str] = None
    actor: str
    level: str
    event: str
    message: str
    outcome: str
    timestamp: datetime

    model_config = ConfigDict(from_attributes=True)


class DashboardMetricsResponse(BaseModel):
    total_workflows: int
    active_workflows: int
    completed_workflows: int
    failed_workflows: int
    awaiting_approval_workflows: int
    pending_approvals: int
    total_tool_executions: int
    total_steps_executed: int
    success_rate_percent: Optional[float] = None
    has_execution_data: bool = False
    system_status: str
    groq_configured: bool
    recent_workflows: List[RecentWorkflowItem] = []
    recent_activity: List[RecentActivityItem] = []


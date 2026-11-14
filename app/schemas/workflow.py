from typing import List, Optional, Any, Dict
from pydantic import BaseModel, Field, ConfigDict
from datetime import datetime


class StepCreate(BaseModel):
    step_number: int
    title: str
    description: Optional[str] = None
    tool_name: str
    tool_input: Optional[Dict[str, Any]] = None
    dependencies: List[int] = Field(default_factory=list)
    is_sensitive: bool = False


class StepResponse(BaseModel):
    id: str
    step_number: int
    title: str
    description: Optional[str] = None
    tool_name: str
    tool_input: Optional[Dict[str, Any]] = None
    tool_output: Optional[Dict[str, Any]] = None
    dependencies: List[int] = Field(default_factory=list)
    retry_count: int = 0
    max_retries: int = 3
    error_message: Optional[str] = None
    is_sensitive: bool
    status: str
    verified: bool
    verification_notes: Optional[str] = None
    created_at: datetime
    completed_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class WorkflowCreateRequest(BaseModel):
    title: Optional[str] = None
    prompt: str = Field(..., min_length=3, description="Natural-language task or goal description")


class WorkflowResponse(BaseModel):
    id: str
    title: str
    original_prompt: str
    status: str
    plan_summary: Optional[str] = None
    template_id: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    steps: List[StepResponse] = []

    model_config = ConfigDict(from_attributes=True)


class WorkflowStatusResponse(BaseModel):
    id: str
    status: str
    steps_total: int
    steps_completed: int
    current_step: Optional[StepResponse] = None
    has_pending_approval: bool = False
    pending_approval_id: Optional[str] = None


class PlanAnalysis(BaseModel):
    intent: str
    goal: str
    assumptions: List[str] = []
    required_capabilities: List[str] = []
    risk_level: str = "low"  # low, medium, high


class DecomposedStep(BaseModel):
    step_number: int
    title: str
    description: str
    tool_name: str
    tool_input: Dict[str, Any]
    dependencies: List[int] = Field(default_factory=list)
    is_sensitive: bool = False


class StructuredPlan(BaseModel):
    title: str
    summary: str
    analysis: PlanAnalysis
    steps: List[DecomposedStep]


class StepPlanItem(BaseModel):
    step_number: int
    title: str
    description: Optional[str] = None
    tool_name: str
    tool_input: Optional[Dict[str, Any]] = None
    dependencies: List[int] = Field(default_factory=list)
    is_sensitive: Optional[bool] = None
    enabled: bool = True


class WorkflowPlanUpdateRequest(BaseModel):
    title: Optional[str] = None
    steps: List[StepPlanItem]


class WorkflowPlanValidationResult(BaseModel):
    valid: bool
    errors: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    dependency_levels: List[List[int]] = Field(default_factory=list)


class WorkflowHistoryResponse(BaseModel):
    workflow_id: str
    title: str
    status: str
    created_at: datetime
    updated_at: datetime
    total_steps: int
    completed_steps: int
    checkpoints_count: int
    total_logs_count: int

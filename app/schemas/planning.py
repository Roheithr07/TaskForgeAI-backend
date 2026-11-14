from enum import Enum
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field, ConfigDict


class TaskCategory(str, Enum):
    RESEARCH = "RESEARCH"
    DOCUMENT_GENERATION = "DOCUMENT_GENERATION"
    SUMMARIZATION = "SUMMARIZATION"
    DATA_PROCESSING = "DATA_PROCESSING"
    EMAIL = "EMAIL"
    BUSINESS_AUTOMATION = "BUSINESS_AUTOMATION"
    DEVELOPER_WORKFLOW = "DEVELOPER_WORKFLOW"
    MULTI_STEP_AUTOMATION = "MULTI_STEP_AUTOMATION"
    GENERAL = "GENERAL"


class ComplexityLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class RiskLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class TaskAnalysisRequest(BaseModel):
    prompt: str = Field(..., min_length=3, max_length=5000, description="Natural-language task or goal description")


class TaskAnalysis(BaseModel):
    objective: str
    intent: str
    category: TaskCategory
    complexity: ComplexityLevel
    required_capabilities: List[str]
    required_tools: List[str]
    constraints: List[str] = Field(default_factory=list)
    clarifications_needed: List[str] = Field(default_factory=list)
    assumptions: List[str] = Field(default_factory=list)
    risk_level: RiskLevel
    requires_approval: bool
    expected_result: str
    provider_mode: str = Field(default="deterministic_fallback", description="'groq' or 'deterministic_fallback'")

    model_config = ConfigDict(from_attributes=True)


class PlanStep(BaseModel):
    step_id: int = Field(..., ge=1, description="Sequential step ID")
    name: str = Field(..., min_length=2, max_length=200)
    description: str = Field(default="")
    tool_name: str
    input_parameters: Dict[str, Any] = Field(default_factory=dict)
    expected_output: str = Field(default="")
    dependencies: List[int] = Field(default_factory=list)
    success_criteria: str = Field(default="")
    risk_level: RiskLevel = RiskLevel.LOW
    is_sensitive: bool = False
    requires_approval: bool = False
    is_optional: bool = False
    enabled: bool = True
    status: str = Field(default="pending")

    model_config = ConfigDict(from_attributes=True)


class PlanGenerationRequest(BaseModel):
    prompt: str = Field(..., min_length=3, max_length=5000)
    title: Optional[str] = Field(default=None, max_length=200)


class ExecutionPlan(BaseModel):
    workflow_name: str
    objective: str
    summary: str
    complexity: ComplexityLevel
    total_steps: int
    estimated_duration: str
    steps: List[PlanStep]
    execution_strategy: str
    approval_summary: str
    clarifications_needed: List[str] = Field(default_factory=list)
    assumptions: List[str] = Field(default_factory=list)
    provider_mode: str = Field(default="deterministic_fallback")

    model_config = ConfigDict(from_attributes=True)


class PlanValidationResult(BaseModel):
    valid: bool
    errors: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    validated_steps_count: int = 0
    has_sensitive_steps: bool = False
    dependency_graph: Dict[str, List[int]] = Field(default_factory=dict)

    model_config = ConfigDict(from_attributes=True)

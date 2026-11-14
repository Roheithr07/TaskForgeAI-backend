from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field, ConfigDict


class TemplateInputParam(BaseModel):
    name: str
    label: str
    type: str = Field(default="string", description="'string', 'select', 'boolean', 'number', 'text'")
    required: bool = True
    default: Optional[Any] = None
    options: Optional[List[str]] = None
    description: Optional[str] = None


class TemplateStepDefinition(BaseModel):
    step_number: int
    title: str
    description: str
    tool_name: str
    dependencies: List[int] = Field(default_factory=list)
    is_sensitive: bool = False
    is_optional: bool = False
    default_input: Dict[str, Any] = Field(default_factory=dict)


class WorkflowTemplateResponse(BaseModel):
    id: str
    name: str
    category: str
    description: str
    version: str = "1.0.0"
    icon: str = "Sparkles"
    estimated_duration: str = "45s"
    complexity: str = "MEDIUM"
    is_sensitive: bool = False
    inputs: List[TemplateInputParam] = Field(default_factory=list)
    steps: List[TemplateStepDefinition] = Field(default_factory=list)
    execution_count: int = 0

    model_config = ConfigDict(from_attributes=True)


class TemplatePreviewRequest(BaseModel):
    inputs: Dict[str, Any] = Field(default_factory=dict)


class TemplateExecuteRequest(BaseModel):
    inputs: Dict[str, Any] = Field(default_factory=dict)
    custom_title: Optional[str] = None


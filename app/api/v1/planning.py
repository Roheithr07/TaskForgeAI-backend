from fastapi import APIRouter, HTTPException
from app.schemas.planning import (
    TaskAnalysisRequest,
    TaskAnalysis,
    PlanGenerationRequest,
    ExecutionPlan,
    PlanValidationResult
)
from app.agents.analyzer import TaskAnalyzer
from app.agents.planner import AIPlanner
from app.agents.plan_validator import PlanValidator

router = APIRouter(prefix="/planning", tags=["Planning Engine"])


@router.post("/analyze", response_model=TaskAnalysis)
async def analyze_task(req: TaskAnalysisRequest):
    """
    Analyzes natural-language input, detects intent, category, complexity,
    required tools, risk level, and constraints.
    """
    try:
        return await TaskAnalyzer.analyze(req.prompt)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Task analysis failed: {str(e)}")


@router.post("/generate", response_model=ExecutionPlan)
async def generate_plan(req: PlanGenerationRequest):
    """
    Generates a validated multi-step DAG execution plan from a natural-language goal.
    """
    try:
        return await AIPlanner.generate_plan(req.prompt, req.title)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Plan generation failed: {str(e)}")


@router.post("/validate", response_model=PlanValidationResult)
def validate_plan(plan: ExecutionPlan):
    """
    Validates an execution plan for:
    - Registered tool names only.
    - Valid step dependencies and circular dependency detection.
    - Server-side policy checks.
    """
    try:
        return PlanValidator.validate_plan(plan)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Plan validation failed: {str(e)}")


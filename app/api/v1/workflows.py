from typing import List, Dict, Any, Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.schemas.workflow import (
    WorkflowCreateRequest, 
    WorkflowResponse, 
    WorkflowStatusResponse,
    WorkflowPlanUpdateRequest,
    WorkflowPlanValidationResult,
    WorkflowHistoryResponse,
    StepPlanItem
)
from app.services.workflow_service import WorkflowService
from app.core.auth import User, require_permission

router = APIRouter(prefix="/workflows", tags=["Workflows"])


@router.post("", response_model=WorkflowResponse)
async def create_workflow(
    req: WorkflowCreateRequest, 
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("create_workflow"))
):
    try:
        return await WorkflowService.create_and_plan_workflow(db, req)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Planning failed: {str(e)}")


@router.get("", response_model=List[WorkflowResponse])
def list_workflows(db: Session = Depends(get_db)):
    return WorkflowService.get_all_workflows(db)


@router.get("/{workflow_id}", response_model=WorkflowResponse)
def get_workflow(workflow_id: str, db: Session = Depends(get_db)):
    wf = WorkflowService.get_workflow_by_id(db, workflow_id)
    if not wf:
        raise HTTPException(status_code=404, detail="Workflow not found")
    return wf


@router.post("/{workflow_id}/execute", response_model=WorkflowResponse)
async def execute_workflow(
    workflow_id: str, 
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("execute_workflow"))
):
    try:
        return await WorkflowService.execute_workflow(db, workflow_id)
    except ValueError as ve:
        raise HTTPException(status_code=404, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Execution error: {str(e)}")


@router.get("/{workflow_id}/status", response_model=WorkflowStatusResponse)
def get_workflow_status(workflow_id: str, db: Session = Depends(get_db)):
    status = WorkflowService.get_status(db, workflow_id)
    if not status:
        raise HTTPException(status_code=404, detail="Workflow not found")
    return status


@router.get("/{workflow_id}/graph")
def get_workflow_graph(workflow_id: str, db: Session = Depends(get_db)):
    """
    Returns topological DAG structure, dependencies, and parallel execution branches.
    """
    try:
        return WorkflowService.get_dag_graph(db, workflow_id)
    except ValueError as ve:
        raise HTTPException(status_code=404, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"DAG retrieval failed: {str(e)}")


@router.get("/{workflow_id}/checkpoints")
async def get_workflow_checkpoints(workflow_id: str, db: Session = Depends(get_db)):
    """
    Returns historical persistent LangGraph checkpoints for the workflow thread.
    """
    try:
        return await WorkflowService.get_checkpoints(db, workflow_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Checkpoint retrieval failed: {str(e)}")


@router.post("/{workflow_id}/validate", response_model=WorkflowPlanValidationResult)
def validate_workflow_plan(
    workflow_id: str,
    req: Optional[List[StepPlanItem]] = None,
    db: Session = Depends(get_db)
):
    """
    Validates current or proposed workflow step sequence, tool existence,
    dependencies, and circular dependency checks.
    """
    try:
        return WorkflowService.validate_workflow_plan(db, workflow_id, req)
    except ValueError as ve:
        raise HTTPException(status_code=404, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Validation failed: {str(e)}")


@router.put("/{workflow_id}/plan", response_model=WorkflowResponse)
def update_workflow_plan(
    workflow_id: str,
    req: WorkflowPlanUpdateRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("create_workflow"))
):
    """
    Updates workflow steps, parameters, and dependencies with strict validation.
    Invalidates any prior pending approval bound to old step definitions.
    """
    try:
        return WorkflowService.update_workflow_plan(db, workflow_id, req)
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update workflow plan: {str(e)}")


@router.get("/{workflow_id}/history", response_model=WorkflowHistoryResponse)
def get_workflow_history(workflow_id: str, db: Session = Depends(get_db)):
    """
    Returns historical execution summary, step completion stats, and checkpoint counts.
    """
    try:
        return WorkflowService.get_workflow_history(db, workflow_id)
    except ValueError as ve:
        raise HTTPException(status_code=404, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"History retrieval failed: {str(e)}")


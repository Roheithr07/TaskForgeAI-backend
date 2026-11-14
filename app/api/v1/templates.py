from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.templates.schemas import (
    WorkflowTemplateResponse,
    TemplatePreviewRequest,
    TemplateExecuteRequest
)
from app.templates.repository import TemplateRepository
from app.schemas.planning import ExecutionPlan
from app.schemas.workflow import WorkflowResponse
from app.core.auth import User, require_permission
from app.services.workflow_service import WorkflowService

router = APIRouter(prefix="/templates", tags=["Templates"])


@router.get("", response_model=List[WorkflowTemplateResponse])
def list_templates(db: Session = Depends(get_db)):
    """List all available workflow templates with live database usage counts."""
    return TemplateRepository.list_templates(db=db)


@router.get("/{template_id}", response_model=WorkflowTemplateResponse)
def get_template(template_id: str, db: Session = Depends(get_db)):
    """Get single workflow template definition and input specification."""
    tmpl = TemplateRepository.get_template(template_id, db=db)
    if not tmpl:
        raise HTTPException(status_code=404, detail=f"Template '{template_id}' not found.")
    return tmpl


@router.post("/{template_id}/preview", response_model=ExecutionPlan)
def preview_template(template_id: str, req: TemplatePreviewRequest):
    """
    Generate preview DAG execution plan with user-interpolated inputs
    without creating database records.
    """
    try:
        return TemplateRepository.build_preview_plan(template_id, req.inputs)
    except ValueError as ve:
        raise HTTPException(status_code=404, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate template preview: {str(e)}")


@router.post("/{template_id}/execute", response_model=WorkflowResponse)
async def execute_template(
    template_id: str,
    req: TemplateExecuteRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("create_workflow"))
):
    """
    Instantiate a new workflow from a template with customized inputs
    and launch autonomous execution on the LangGraph engine.
    """
    try:
        wf = TemplateRepository.instantiate_workflow(
            db=db,
            template_id=template_id,
            user_inputs=req.inputs,
            custom_title=req.custom_title
        )
        # Launch workflow execution
        executed_wf = await WorkflowService.execute_workflow(db, wf.id)
        return executed_wf
    except ValueError as ve:
        raise HTTPException(status_code=404, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to execute template workflow: {str(e)}")


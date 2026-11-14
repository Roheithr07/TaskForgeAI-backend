from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.database.models import Workflow, WorkflowStep, ExecutionLog
from app.schemas.execution import ExecutionLogResponse, ExecutionSessionResponse

router = APIRouter(prefix="/executions", tags=["Executions"])


@router.get("", response_model=List[ExecutionSessionResponse])
def list_execution_sessions(db: Session = Depends(get_db)):
    workflows = db.query(Workflow).order_by(Workflow.updated_at.desc()).all()
    sessions = []
    for wf in workflows:
        total_steps = len(wf.steps)
        completed_steps = sum(1 for s in wf.steps if s.status == "completed")
        logs_count = len(wf.executions)
        sessions.append(ExecutionSessionResponse(
            workflow_id=wf.id,
            workflow_title=wf.title,
            status=wf.status,
            total_steps=total_steps,
            completed_steps=completed_steps,
            logs_count=logs_count
        ))
    return sessions


@router.get("/{workflow_id}", response_model=List[ExecutionLogResponse])
def get_execution_logs(workflow_id: str, db: Session = Depends(get_db)):
    logs = db.query(ExecutionLog).filter(
        ExecutionLog.workflow_id == workflow_id
    ).order_by(ExecutionLog.timestamp.asc()).all()
    return [ExecutionLogResponse.model_validate(log) for log in logs]


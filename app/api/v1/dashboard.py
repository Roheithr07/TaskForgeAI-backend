from typing import List
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func, desc

from app.database.session import get_db
from app.database.models import Workflow, WorkflowStep, ApprovalRequest, ExecutionLog
from app.schemas.dashboard import DashboardMetricsResponse, RecentWorkflowItem, RecentActivityItem
from app.core.config import settings

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])


@router.get("/metrics", response_model=DashboardMetricsResponse)
def get_dashboard_metrics(db: Session = Depends(get_db)):
    """
    Returns live aggregated system metrics from the actual database.
    No simulated or hardcoded statistics.
    """
    # 1. Workflow counts
    total_workflows = db.query(func.count(Workflow.id)).scalar() or 0
    completed_workflows = db.query(func.count(Workflow.id)).filter(Workflow.status == "completed").scalar() or 0
    failed_workflows = db.query(func.count(Workflow.id)).filter(Workflow.status == "failed").scalar() or 0
    awaiting_approval_workflows = db.query(func.count(Workflow.id)).filter(Workflow.status == "awaiting_approval").scalar() or 0
    
    # Active workflows are those in created, planned, executing, running, or awaiting_approval states
    active_workflows = db.query(func.count(Workflow.id)).filter(
        Workflow.status.in_(["created", "planned", "executing", "running", "awaiting_approval"])
    ).scalar() or 0

    # 2. Approvals
    pending_approvals = db.query(func.count(ApprovalRequest.id)).filter(
        ApprovalRequest.status == "pending"
    ).scalar() or 0

    # 3. Execution metrics
    total_tool_executions = db.query(func.count(ExecutionLog.id)).filter(
        ExecutionLog.event == "TOOL_EXECUTION_COMPLETED"
    ).scalar() or 0

    total_steps_executed = db.query(func.count(WorkflowStep.id)).filter(
        WorkflowStep.status == "completed"
    ).scalar() or 0

    # Success rate: None if no terminal workflows executed yet (do not fabricate 100%)
    terminal_workflows = completed_workflows + failed_workflows
    if terminal_workflows > 0:
        success_rate = round((completed_workflows / terminal_workflows) * 100.0, 1)
        has_execution_data = True
    else:
        success_rate = None
        has_execution_data = False

    # 4. Recent Workflows
    recent_wfs_raw = db.query(Workflow).order_by(Workflow.updated_at.desc()).limit(5).all()
    recent_workflows: List[RecentWorkflowItem] = []
    wf_title_map = {}
    for wf in recent_wfs_raw:
        wf_title_map[wf.id] = wf.title
        total_s = len(wf.steps)
        comp_s = sum(1 for s in wf.steps if s.status == "completed")
        recent_workflows.append(RecentWorkflowItem(
            id=wf.id,
            title=wf.title,
            status=wf.status,
            total_steps=total_s,
            completed_steps=comp_s,
            created_at=wf.created_at,
            updated_at=wf.updated_at
        ))

    # 5. Recent Activity Logs (top 10)
    recent_logs_raw = db.query(ExecutionLog).order_by(ExecutionLog.timestamp.desc()).limit(10).all()
    recent_activity: List[RecentActivityItem] = []
    
    # Preload workflow titles for workflows in recent logs that weren't in top 5
    missing_wf_ids = [l.workflow_id for l in recent_logs_raw if l.workflow_id not in wf_title_map]
    if missing_wf_ids:
        extra_wfs = db.query(Workflow.id, Workflow.title).filter(Workflow.id.in_(missing_wf_ids)).all()
        for w_id, w_title in extra_wfs:
            wf_title_map[w_id] = w_title

    for log in recent_logs_raw:
        recent_activity.append(RecentActivityItem(
            id=log.id,
            workflow_id=log.workflow_id,
            workflow_title=wf_title_map.get(log.workflow_id, "Workflow"),
            step_id=log.step_id,
            actor=log.actor or "system",
            level=log.level or "INFO",
            event=log.event,
            message=log.message,
            outcome=log.outcome or "SUCCESS",
            timestamp=log.timestamp
        ))

    groq_ready = bool(settings.GROQ_API_KEY and len(settings.GROQ_API_KEY.strip()) > 0)

    return DashboardMetricsResponse(
        total_workflows=total_workflows,
        active_workflows=active_workflows,
        completed_workflows=completed_workflows,
        failed_workflows=failed_workflows,
        awaiting_approval_workflows=awaiting_approval_workflows,
        pending_approvals=pending_approvals,
        total_tool_executions=total_tool_executions,
        total_steps_executed=total_steps_executed,
        success_rate_percent=success_rate,
        has_execution_data=has_execution_data,
        system_status="OPERATIONAL",
        groq_configured=groq_ready,
        recent_workflows=recent_workflows,
        recent_activity=recent_activity
    )


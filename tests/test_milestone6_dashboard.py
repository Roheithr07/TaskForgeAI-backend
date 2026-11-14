import pytest
import uuid
from datetime import datetime, timedelta
from fastapi.testclient import TestClient
from app.main import app
from app.database.session import SessionLocal
from app.database.models import Workflow, WorkflowStep, ApprovalRequest, ExecutionLog

client = TestClient(app)


def test_dashboard_metrics_empty_state():
    """Verify metrics calculation when database is queried."""
    response = client.get("/api/v1/dashboard/metrics")
    assert response.status_code == 200
    data = response.json()

    assert "total_workflows" in data
    assert "active_workflows" in data
    assert "completed_workflows" in data
    assert "failed_workflows" in data
    assert "awaiting_approval_workflows" in data
    assert "pending_approvals" in data
    assert "total_tool_executions" in data
    assert "success_rate_percent" in data
    assert data["system_status"] == "OPERATIONAL"
    assert isinstance(data["recent_workflows"], list)
    assert isinstance(data["recent_activity"], list)


def test_dashboard_metrics_aggregation():
    """Verify live calculation of workflows, steps, tool executions, and success rate."""
    db = SessionLocal()
    try:
        unique_suffix = str(uuid.uuid4())[:8]
        
        # 1. Create a completed workflow
        wf1 = Workflow(
            id=str(uuid.uuid4()),
            title=f"Completed WF {unique_suffix}",
            original_prompt="Run completed test task",
            status="completed"
        )
        db.add(wf1)
        db.commit()

        step1 = WorkflowStep(
            workflow_id=wf1.id,
            step_number=1,
            title="Web Research",
            tool_name="web_research",
            status="completed"
        )
        db.add(step1)
        
        log1 = ExecutionLog(
            workflow_id=wf1.id,
            step_id=step1.id,
            actor="system",
            level="SUCCESS",
            event="TOOL_EXECUTION_COMPLETED",
            message="Web research completed successfully",
            outcome="SUCCESS"
        )
        db.add(log1)

        # 2. Create an awaiting_approval workflow with an approval request
        wf2 = Workflow(
            id=str(uuid.uuid4()),
            title=f"Awaiting Approval WF {unique_suffix}",
            original_prompt="Run email task requiring approval",
            status="awaiting_approval"
        )
        db.add(wf2)
        db.commit()

        step2 = WorkflowStep(
            workflow_id=wf2.id,
            step_number=1,
            title="Send Stakeholder Email",
            tool_name="email_drafting",
            is_sensitive=True,
            status="awaiting_approval"
        )
        db.add(step2)
        db.commit()

        approval = ApprovalRequest(
            workflow_id=wf2.id,
            step_id=step2.id,
            tool_name="email_drafting",
            action_description="Outbound email to executive team",
            risk_level="HIGH",
            status="pending"
        )
        db.add(approval)

        log2 = ExecutionLog(
            workflow_id=wf2.id,
            step_id=step2.id,
            actor="policy_engine",
            level="WARNING",
            event="POLICY_INTERRUPT_TRIGGERED",
            message="Held for supervisor authorization",
            outcome="HALTED"
        )
        db.add(log2)
        db.commit()

        # Call dashboard metrics
        response = client.get("/api/v1/dashboard/metrics")
        assert response.status_code == 200
        metrics = response.json()

        assert metrics["total_workflows"] >= 2
        assert metrics["completed_workflows"] >= 1
        assert metrics["awaiting_approval_workflows"] >= 1
        assert metrics["pending_approvals"] >= 1
        assert metrics["total_tool_executions"] >= 1

        # Check recent workflows contains wf1 or wf2
        recent_ids = [w["id"] for w in metrics["recent_workflows"]]
        assert wf2.id in recent_ids or wf1.id in recent_ids

        # Check recent activity logs contains log2 or log1
        events = [a["event"] for a in metrics["recent_activity"]]
        assert "POLICY_INTERRUPT_TRIGGERED" in events or "TOOL_EXECUTION_COMPLETED" in events
    finally:
        db.close()


def test_execution_logs_and_timeline_stream():
    """Test retrieving execution logs with actor, outcome, and chronological ordering."""
    db = SessionLocal()
    try:
        wf_id = str(uuid.uuid4())
        wf = Workflow(
            id=wf_id,
            title="Timeline Test Workflow",
            original_prompt="Test timeline ordering",
            status="running"
        )
        db.add(wf)
        db.commit()

        now = datetime.utcnow()
        log1 = ExecutionLog(
            workflow_id=wf_id,
            actor="graph_orchestrator",
            level="INFO",
            event="WORKFLOW_GRAPH_INITIALIZED",
            message="Initialized DAG state graph",
            outcome="SUCCESS",
            timestamp=now - timedelta(seconds=10)
        )
        log2 = ExecutionLog(
            workflow_id=wf_id,
            actor="tool_runner",
            level="SUCCESS",
            event="TOOL_EXECUTION_COMPLETED",
            message="Tool execution verified",
            outcome="SUCCESS",
            timestamp=now
        )
        db.add_all([log1, log2])
        db.commit()

        response = client.get(f"/api/v1/executions/{wf_id}")
        assert response.status_code == 200
        logs = response.json()
        assert len(logs) >= 2
        assert logs[0]["event"] == "WORKFLOW_GRAPH_INITIALIZED"
        assert logs[0]["actor"] == "graph_orchestrator"
        assert logs[0]["outcome"] == "SUCCESS"
        assert logs[1]["event"] == "TOOL_EXECUTION_COMPLETED"
    finally:
        db.close()


def test_execution_sessions_list():
    """Verify execution sessions summary endpoint returns completed step metrics."""
    response = client.get("/api/v1/executions")
    assert response.status_code == 200
    sessions = response.json()
    assert isinstance(sessions, list)
    if len(sessions) > 0:
        session = sessions[0]
        assert "workflow_id" in session
        assert "workflow_title" in session
        assert "total_steps" in session
        assert "completed_steps" in session
        assert "logs_count" in session

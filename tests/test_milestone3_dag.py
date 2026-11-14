import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.graph.dag_scheduler import DAGScheduler
from app.graph.checkpointer import get_async_checkpointer, list_thread_checkpoints
from app.services.approval_service import ApprovalService
from app.schemas.approval import ApprovalActionRequest
from app.database.session import SessionLocal
from app.database.models import ApprovalRequest, WorkflowStep

client = TestClient(app)


def test_dag_scheduler_linear_ready_steps():
    steps = {
        1: {"status": "pending", "dependencies": []},
        2: {"status": "pending", "dependencies": [1]},
        3: {"status": "pending", "dependencies": [2]},
    }
    # Initially, only Step 1 should be ready
    ready = DAGScheduler.get_ready_steps(steps)
    assert ready == [1]

    # After Step 1 completes, Step 2 should be ready
    steps[1]["status"] = "completed"
    ready = DAGScheduler.get_ready_steps(steps)
    assert ready == [2]

    # After Step 2 completes, Step 3 should be ready
    steps[2]["status"] = "completed"
    ready = DAGScheduler.get_ready_steps(steps)
    assert ready == [3]


def test_dag_scheduler_parallel_branches():
    # Step 1 -> [2, 3, 4] -> 5
    steps = {
        1: {"status": "completed", "dependencies": []},
        2: {"status": "pending", "dependencies": [1]},
        3: {"status": "pending", "dependencies": [1]},
        4: {"status": "pending", "dependencies": [1]},
        5: {"status": "pending", "dependencies": [2, 3, 4]},
    }
    # Steps 2, 3, 4 should all be ready concurrently!
    ready = DAGScheduler.get_ready_steps(steps, concurrency_limit=10)
    assert set(ready) == {2, 3, 4}

    # Complete 2 and 3; Step 5 is NOT ready yet because 4 is still pending
    steps[2]["status"] = "completed"
    steps[3]["status"] = "completed"
    ready = DAGScheduler.get_ready_steps(steps)
    assert ready == [4]

    # Complete 4; now Step 5 is ready!
    steps[4]["status"] = "completed"
    ready = DAGScheduler.get_ready_steps(steps)
    assert ready == [5]


def test_dag_scheduler_blocked_on_failure():
    steps = {
        1: {"status": "completed", "dependencies": []},
        2: {"status": "failed", "dependencies": [1]},
        3: {"status": "pending", "dependencies": [2]},  # depends on 2 which failed
    }
    newly_blocked = DAGScheduler.update_blocked_steps(steps)
    assert 3 in newly_blocked
    assert steps[3]["status"] == "blocked"


def test_dag_scheduler_topological_levels():
    steps = {
        1: {"dependencies": []},
        2: {"dependencies": [1]},
        3: {"dependencies": [1]},
        4: {"dependencies": [2, 3]},
    }
    levels = DAGScheduler.compute_dag_levels(steps)
    assert levels == [[1], [2, 3], [4]]


@pytest.mark.asyncio
async def test_checkpointer_integration():
    saver = await get_async_checkpointer()
    assert saver is not None
    # Check listing checkpoints for arbitrary thread
    cps = await list_thread_checkpoints("test_thread_123")
    assert isinstance(cps, list)


def test_dag_workflow_full_lifecycle():
    # 1. Create a workflow with research and email
    res = client.post("/api/v1/workflows", json={
        "title": "DAG Test Workflow",
        "prompt": "Research AI platforms, summarize findings, and draft an email."
    })
    assert res.status_code == 200
    wf_id = res.json()["id"]

    # 2. Get DAG graph endpoint
    graph_res = client.get(f"/api/v1/workflows/{wf_id}/graph")
    assert graph_res.status_code == 200
    graph_data = graph_res.json()
    assert "levels" in graph_data
    assert "steps" in graph_data
    assert len(graph_data["levels"]) >= 2

    # 3. Execute workflow -> it should run automated steps and halt at approval step
    exec_res = client.post(f"/api/v1/workflows/{wf_id}/execute")
    assert exec_res.status_code == 200
    exec_data = exec_res.json()
    assert exec_data["status"] == "awaiting_approval"

    # 4. Check checkpoints endpoint
    cp_res = client.get(f"/api/v1/workflows/{wf_id}/checkpoints")
    assert cp_res.status_code == 200

    # 5. Fetch pending approval
    approvals_res = client.get("/api/v1/approvals?status=pending")
    assert approvals_res.status_code == 200
    apps = approvals_res.json()
    matching = [a for a in apps if a["workflow_id"] == wf_id]
    assert len(matching) > 0
    app_id = matching[0]["id"]

    # 6. Approve action
    approve_res = client.post(f"/api/v1/approvals/{app_id}/approve", json={
        "comment": "Supervisor authorized email draft."
    })
    assert approve_res.status_code == 200
    assert approve_res.json()["status"] == "approved"

    # 7. Resume workflow from checkpoint on same thread
    resume_res = client.post(f"/api/v1/workflows/{wf_id}/execute")
    assert resume_res.status_code == 200
    final_data = resume_res.json()
    assert final_data["status"] == "completed"


import uuid


def test_payload_tamper_rejection():
    db = SessionLocal()
    try:
        wf_id = str(uuid.uuid4())
        step_id = str(uuid.uuid4())
        req = ApprovalRequest(
            workflow_id=wf_id,
            step_id=step_id,
            tool_name="email_drafting",
            action_description="Test",
            payload_preview={"subject": "Original"},
            payload_hash="original_hash_123",
            status="pending"
        )
        step = WorkflowStep(
            id=step_id,
            workflow_id=wf_id,
            step_number=1,
            title="Email",
            tool_name="email_drafting",
            tool_input={"subject": "Modified after approval generated"},
            status="awaiting_approval"
        )
        db.add(step)
        db.add(req)
        db.commit()

        # Approval should fail due to tamper detection
        with pytest.raises(ValueError, match="Payload has been modified"):
            ApprovalService.approve_action(db, req.id, ApprovalActionRequest(comment="test"))
    finally:
        db.close()

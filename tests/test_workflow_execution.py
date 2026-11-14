import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_workflow_lifecycle():
    # 1. Create and plan workflow
    create_res = client.post("/api/v1/workflows", json={
        "title": "Autonomous Market Research",
        "prompt": "Research AI agents, draft an executive summary, and prepare an email briefing for stakeholders."
    })
    assert create_res.status_code == 200
    wf_data = create_res.json()
    wf_id = wf_data["id"]
    assert len(wf_data["steps"]) >= 2

    # 2. Inspect status
    status_res = client.get(f"/api/v1/workflows/{wf_id}/status")
    assert status_res.status_code == 200
    status_data = status_res.json()
    assert status_data["steps_total"] >= 2

    # 3. Execute workflow
    exec_res = client.post(f"/api/v1/workflows/{wf_id}/execute")
    assert exec_res.status_code == 200
    exec_data = exec_res.json()
    assert exec_data["status"] in ["completed", "awaiting_approval", "executing"]

    # 4. Check approvals endpoint
    approvals_res = client.get("/api/v1/approvals")
    assert approvals_res.status_code == 200
    approvals_list = approvals_res.json()

    # If sensitive step was encountered, verify approval item was created
    if exec_data["status"] == "awaiting_approval":
        matching = [a for a in approvals_list if a["workflow_id"] == wf_id]
        assert len(matching) > 0
        approval_id = matching[0]["id"]
        # Approve action
        action_res = client.post(f"/api/v1/approvals/{approval_id}/approve", json={"comment": "Approved by testing suite"})
        assert action_res.status_code == 200
        assert action_res.json()["status"] == "approved"

        # Resume execution
        resume_res = client.post(f"/api/v1/workflows/{wf_id}/execute")
        assert resume_res.status_code == 200


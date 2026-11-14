import pytest
import uuid
from fastapi.testclient import TestClient

from app.main import app
from app.database.session import SessionLocal
from app.database.models import Workflow, WorkflowStep
from app.templates.repository import TemplateRepository
from app.agents.verifier import ResultVerifier
from app.schemas.workflow import StepPlanItem, WorkflowPlanUpdateRequest

client = TestClient(app)


def test_list_templates():
    """Verify all 5 production templates are registered with schemas, categories, and inputs."""
    response = client.get("/api/v1/templates")
    assert response.status_code == 200
    templates = response.json()
    assert len(templates) >= 5

    template_ids = [t["id"] for t in templates]
    assert "research-assistant" in template_ids
    assert "document-automation" in template_ids
    assert "email-assistant" in template_ids
    assert "data-analysis" in template_ids
    assert "business-research" in template_ids

    # Check template structure
    ra = next(t for t in templates if t["id"] == "research-assistant")
    assert ra["category"] == "RESEARCH"
    assert len(ra["inputs"]) >= 2
    assert len(ra["steps"]) == 3
    assert ra["steps"][0]["tool_name"] == "web_research"


def test_get_single_template():
    """Verify getting detail of a single template."""
    response = client.get("/api/v1/templates/email-assistant")
    assert response.status_code == 200
    tmpl = response.json()
    assert tmpl["id"] == "email-assistant"
    assert tmpl["is_sensitive"] is True
    assert any(s["tool_name"] == "email_sending" for s in tmpl["steps"])


def test_template_preview_plan_interpolation():
    """Verify previewing a template interpolates user parameters into steps without DB writes."""
    payload = {
        "inputs": {
            "topic": "Neuromorphic Computing Chips",
            "depth": "Technical Deep Dive",
            "report_title": "Neuromorphic AI Architecture Brief"
        }
    }
    response = client.post("/api/v1/templates/research-assistant/preview", json=payload)
    assert response.status_code == 200
    plan = response.json()

    assert "Neuromorphic" in plan["workflow_name"]
    assert len(plan["steps"]) == 3
    # Step 1 input should be interpolated
    step1_query = plan["steps"][0]["input_parameters"]["query"]
    assert "Neuromorphic Computing Chips" in step1_query
    # Step 3 input should be interpolated
    step3_title = plan["steps"][2]["input_parameters"]["title"]
    assert "Neuromorphic AI Architecture Brief" in step3_title


def test_template_execution_real_workflow():
    """Verify instantiating and executing a real workflow from a template."""
    payload = {
        "inputs": {
            "topic": "Edge AI Inference Acceleration",
            "depth": "In-Depth Synthesis",
            "report_title": "Edge AI Executive Summary"
        },
        "custom_title": "Custom Edge AI Workflow"
    }
    response = client.post(
        "/api/v1/templates/research-assistant/execute",
        json=payload,
        headers={"X-User-Role": "WORKSPACE_OWNER"}
    )
    assert response.status_code == 200
    wf = response.json()

    assert wf["title"] == "Custom Edge AI Workflow"
    assert wf["template_id"] == "research-assistant"
    assert len(wf["steps"]) == 3
    assert wf["status"] in ["planned", "executing", "completed", "completed_with_errors"]

    # Verify execution count incremented in template listing
    list_res = client.get("/api/v1/templates")
    ra = next(t for t in list_res.json() if t["id"] == "research-assistant")
    assert ra["execution_count"] >= 1


def test_workflow_plan_validation_cycle_detection():
    """Verify dependency validator flags circular dependencies in customized plans."""
    db = SessionLocal()
    try:
        wf = Workflow(
            id=str(uuid.uuid4()),
            title="Cycle Test Workflow",
            original_prompt="Test cycle detection",
            status="planned"
        )
        db.add(wf)
        db.commit()

        # Step 1 depends on Step 2, and Step 2 depends on Step 1
        proposed_steps = [
            {
                "step_number": 1,
                "title": "Step 1",
                "tool_name": "web_research",
                "tool_input": {"query": "test"},
                "dependencies": [2],
                "enabled": True
            },
            {
                "step_number": 2,
                "title": "Step 2",
                "tool_name": "text_summarization",
                "tool_input": {"text": "test"},
                "dependencies": [1],
                "enabled": True
            }
        ]

        response = client.post(f"/api/v1/workflows/{wf.id}/validate", json=proposed_steps)
        assert response.status_code == 200
        result = response.json()
        assert result["valid"] is False
        assert any("Circular dependency" in err for err in result["errors"])
    finally:
        db.close()


def test_workflow_plan_customization_and_history():
    """Verify updating workflow plan reorders steps and records history."""
    db = SessionLocal()
    try:
        wf = Workflow(
            id=str(uuid.uuid4()),
            title="Customizable Workflow",
            original_prompt="Original plan prompt",
            status="planned"
        )
        db.add(wf)
        db.commit()

        # Add initial steps
        s1 = WorkflowStep(workflow_id=wf.id, step_number=1, title="Initial S1", tool_name="web_research", status="pending")
        s2 = WorkflowStep(workflow_id=wf.id, step_number=2, title="Initial S2", tool_name="document_generation", status="pending")
        db.add_all([s1, s2])
        db.commit()

        # Update plan: customize title, change tool parameters
        update_payload = {
            "title": "Customized AI Plan",
            "steps": [
                {
                    "step_number": 1,
                    "title": "Custom Research Step",
                    "description": "Deep search with verified sources",
                    "tool_name": "web_research",
                    "tool_input": {"query": "custom query", "num_results": 4},
                    "dependencies": [],
                    "enabled": True
                },
                {
                    "step_number": 2,
                    "title": "Custom Summary Step",
                    "description": "Synthesize results",
                    "tool_name": "text_summarization",
                    "tool_input": {"raw_text": "sample", "tone": "executive"},
                    "dependencies": [1],
                    "enabled": True
                }
            ]
        }

        put_res = client.put(
            f"/api/v1/workflows/{wf.id}/plan",
            json=update_payload,
            headers={"X-User-Role": "WORKSPACE_OWNER"}
        )
        assert put_res.status_code == 200
        updated = put_res.json()
        assert updated["title"] == "Customized AI Plan"
        assert len(updated["steps"]) == 2
        assert updated["steps"][0]["title"] == "Custom Research Step"

        # Check history endpoint
        hist_res = client.get(f"/api/v1/workflows/{wf.id}/history")
        assert hist_res.status_code == 200
        hist = hist_res.json()
        assert hist["workflow_id"] == wf.id
        assert hist["total_steps"] == 2
    finally:
        db.close()


def test_result_verifier_diagnostics():
    """Verify result verifier provides structured failure diagnostics and recovery recommendations."""
    # 1. Success case
    verified, note = ResultVerifier.verify("web_research", {"findings": ["Point 1", "Point 2"], "citations": [{"url": "https://example.com"}]})
    assert verified is True
    assert "Verified" in note

    # 2. Failure case with diagnosis
    verified_fail, note_fail = ResultVerifier.verify("web_research", {})
    assert verified_fail is False

    diag = ResultVerifier.diagnose_failure("web_research", {})
    assert diag["category"] == "EMPTY_PAYLOAD"
    assert "recovery_recommendation" in diag
    assert diag["is_retryable"] is True

    # 3. Timeout diagnostic
    diag_timeout = ResultVerifier.diagnose_failure("web_research", {"error": "Connection timed out after 30s"})
    assert diag_timeout["category"] == "TIMEOUT_FAILURE"
    assert diag_timeout["is_retryable"] is True

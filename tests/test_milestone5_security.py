import uuid
from datetime import datetime, timedelta
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.database.session import SessionLocal
from app.database.models import ApprovalRequest, WorkflowStep, Workflow, ExecutionLog
from app.schemas.approval import ApprovalActionRequest
from app.services.approval_service import ApprovalService
from app.agents.policy import PolicyChecker
from app.core.security import redact_secrets
from app.core.auth import User, UserRole

client = TestClient(app)


# -------------------------------------------------------------
# 1. RBAC AUTHORIZATION ENFORCEMENT TESTS
# -------------------------------------------------------------

def test_rbac_viewer_cannot_create_or_execute_workflow():
    # 1. VIEWER cannot create workflow
    res = client.post("/api/v1/workflows", 
        json={"title": "Test WF", "prompt": "Research AI platforms."},
        headers={"X-User-Role": "VIEWER"}
    )
    assert res.status_code == 403
    assert "Access Denied" in res.json()["detail"]

    # 2. OPERATOR can create workflow
    op_res = client.post("/api/v1/workflows", 
        json={"title": "Operator WF", "prompt": "Research AI platforms and summarize."},
        headers={"X-User-Role": "OPERATOR"}
    )
    assert op_res.status_code == 200
    wf_id = op_res.json()["id"]

    # 3. VIEWER cannot execute workflow
    exec_viewer = client.post(f"/api/v1/workflows/{wf_id}/execute", headers={"X-User-Role": "VIEWER"})
    assert exec_viewer.status_code == 403
    assert "Access Denied" in exec_viewer.json()["detail"]


def test_rbac_operator_cannot_approve_actions():
    # Create workflow needing approval
    wf_res = client.post("/api/v1/workflows", json={
        "title": "Email Send WF",
        "prompt": "Draft an executive email to stakeholders and request approval."
    }, headers={"X-User-Role": "OPERATOR"})
    assert wf_res.status_code == 200
    wf_id = wf_res.json()["id"]

    # Execute up to approval halt
    client.post(f"/api/v1/workflows/{wf_id}/execute", headers={"X-User-Role": "OPERATOR"})

    # Fetch pending approvals
    apps = client.get("/api/v1/approvals?status=pending").json()
    matching = [a for a in apps if a["workflow_id"] == wf_id]
    assert len(matching) > 0
    app_id = matching[0]["id"]

    # OPERATOR attempt to approve must be REJECTED with 403 Forbidden
    op_approve = client.post(f"/api/v1/approvals/{app_id}/approve", 
        json={"comment": "Operator attempting self-approval"},
        headers={"X-User-Role": "OPERATOR"}
    )
    assert op_approve.status_code == 403
    assert "Access Denied" in op_approve.json()["detail"]

    # REVIEWER can approve successfully
    rev_approve = client.post(f"/api/v1/approvals/{app_id}/approve",
        json={"comment": "Compliance Officer authorization granted."},
        headers={"X-User-Role": "REVIEWER"}
    )
    assert rev_approve.status_code == 200
    assert rev_approve.json()["status"] == "approved"


def test_rbac_security_settings_permissions():
    # OPERATOR cannot update security settings
    patch_op = client.patch("/api/v1/security/settings", 
        json={"approval_expiration_hours": 48},
        headers={"X-User-Role": "OPERATOR"}
    )
    assert patch_op.status_code == 403

    # SUPER_ADMIN can update security settings
    patch_admin = client.patch("/api/v1/security/settings", 
        json={"approval_expiration_hours": 48},
        headers={"X-User-Role": "SUPER_ADMIN"}
    )
    assert patch_admin.status_code == 200
    assert patch_admin.json()["approval_expiration_hours"] == 48


# -------------------------------------------------------------
# 2. APPROVAL LIFECYCLE, EXPIRATION & IDEMPOTENCY
# -------------------------------------------------------------

def test_approval_expiration_enforcement():
    db = SessionLocal()
    try:
        wf_id = str(uuid.uuid4())
        step_id = str(uuid.uuid4())
        # Create an approval that expired 2 hours ago
        expired_req = ApprovalRequest(
            workflow_id=wf_id,
            step_id=step_id,
            tool_name="email_sending",
            action_description="Expired action",
            payload_preview={"recipient": "test@domain.com"},
            payload_hash="somehash",
            risk_level="HIGH",
            status="pending",
            expires_at=datetime.utcnow() - timedelta(hours=2)
        )
        db.add(expired_req)
        db.commit()

        # Fetching approval should automatically detect and update status to expired
        fetched = ApprovalService.get_approval(db, expired_req.id)
        assert fetched.status == "expired"

        # Attempting to approve expired request must fail with ValueError
        reviewer_user = User(id="usr_rev", email="rev@ai.com", name="Reviewer", role=UserRole.REVIEWER)
        with pytest.raises(ValueError, match="EXPIRED"):
            ApprovalService.approve_action(db, expired_req.id, ApprovalActionRequest(comment="Late approve"), actor=reviewer_user)
    finally:
        db.close()


def test_duplicate_approval_idempotency():
    db = SessionLocal()
    try:
        wf_id = str(uuid.uuid4())
        step_id = str(uuid.uuid4())
        req = ApprovalRequest(
            workflow_id=wf_id,
            step_id=step_id,
            tool_name="email_sending",
            action_description="Idempotent test",
            payload_preview={"to": "test@domain.com"},
            payload_hash="dummyhash",
            risk_level="HIGH",
            status="pending"
        )
        db.add(req)
        db.commit()

        reviewer = User(id="usr_rev", email="rev@ai.com", name="Reviewer", role=UserRole.REVIEWER)
        # First approve
        res1 = ApprovalService.approve_action(db, req.id, ApprovalActionRequest(comment="First"), actor=reviewer)
        assert res1.status == "approved"

        # Duplicate second approve call must be idempotent (return without error)
        res2 = ApprovalService.approve_action(db, req.id, ApprovalActionRequest(comment="Second duplicate"), actor=reviewer)
        assert res2.status == "approved"
        assert res2.id == res1.id
    finally:
        db.close()


# -------------------------------------------------------------
# 3. RISK-BASED ACTION CLASSIFICATION POLICIES
# -------------------------------------------------------------

def test_risk_classification_policies():
    # 1. LOW: read-only research
    risk_web = PolicyChecker.classify_risk("web_research", {"query": "AI Agents"})
    assert risk_web == "LOW"

    # 2. MEDIUM: local document creation
    risk_doc = PolicyChecker.classify_risk("document_generation", {"title": "Report"})
    assert risk_doc == "MEDIUM"

    # 3. HIGH: external communication
    risk_email = PolicyChecker.classify_risk("email_sending", {"recipient_email": "ceo@corp.com"})
    assert risk_email == "HIGH"

    # 4. CRITICAL: financial or destructive operations
    risk_payment = PolicyChecker.classify_risk("payment_processing", {"amount": 5000})
    assert risk_payment == "CRITICAL"

    risk_delete = PolicyChecker.classify_risk("file_processing", {"operation": "delete_records"})
    assert risk_delete == "CRITICAL"


# -------------------------------------------------------------
# 4. SECRET REDACTION & CREDENTIAL PROTECTION
# -------------------------------------------------------------

def test_secret_redaction_comprehensive():
    raw_payload = {
        "groq_api_key": "gsk_12345678901234567890abcdef",
        "smtp_password": "SuperSecretPassword123!",
        "safe_title": "Public Quarterly Report",
        "nested": {
            "token": "Bearer abcdef123456789",
            "message": "Connecting with key gsk_abcdef1234567890123456 to cluster"
        }
    }

    scrubbed = redact_secrets(raw_payload)

    # Sensitive keys must be fully masked
    assert scrubbed["groq_api_key"] == "***REDACTED***"
    assert scrubbed["smtp_password"] == "***REDACTED***"
    assert scrubbed["nested"]["token"] == "***REDACTED***"

    # Inline regex secret pattern in string must be scrubbed
    assert "gsk_abcdef" not in scrubbed["nested"]["message"]
    assert "***REDACTED***" in scrubbed["nested"]["message"]

    # Safe fields must be preserved
    assert scrubbed["safe_title"] == "Public Quarterly Report"


# -------------------------------------------------------------
# 5. AUDIT AND ACTIVITY LOGGING
# -------------------------------------------------------------

def test_audit_logs_endpoint():
    res = client.get("/api/v1/security/audit-logs", headers={"X-User-Role": "OPERATOR"})
    assert res.status_code == 200
    logs = res.json()
    assert isinstance(logs, list)
    if logs:
        first = logs[0]
        assert "actor" in first
        assert "event" in first
        assert "level" in first
        assert "outcome" in first
        assert "details" in first


# -------------------------------------------------------------
# 6. AUTH PROFILE AND DYNAMIC ROLE SWITCHING
# -------------------------------------------------------------

def test_auth_me_and_role_switching():
    # 1. Inspect current profile
    me_res = client.get("/api/v1/security/me", headers={"X-User-Role": "REVIEWER"})
    assert me_res.status_code == 200
    data = me_res.json()
    assert data["role"] == "REVIEWER"
    assert "approve_action" in data["permissions"]

    # 2. Dynamic role switch
    switch_res = client.post("/api/v1/security/switch-role", json={"role": "SUPER_ADMIN"})
    assert switch_res.status_code == 200
    assert switch_res.json()["active_role"] == "SUPER_ADMIN"


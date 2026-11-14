from datetime import datetime, timedelta
from typing import List, Optional
from sqlalchemy.orm import Session
from fastapi import HTTPException

from app.database.models import ApprovalRequest, Workflow, WorkflowStep, ExecutionLog
from app.schemas.approval import ApprovalResponse, ApprovalActionRequest
from app.graph.workflow_graph import compute_payload_hash
from app.core.auth import User, UserRole
from app.core.security import redact_secrets

DEFAULT_EXPIRATION_HOURS = 24
AUTHORIZED_REVIEWER_ROLES = {UserRole.SUPER_ADMIN, UserRole.WORKSPACE_OWNER, UserRole.REVIEWER}


class ApprovalService:
    @staticmethod
    def _check_and_update_expiration(approval: ApprovalRequest, db: Session):
        """Automatically marks expired pending requests as EXPIRED."""
        if approval.status == "pending" and approval.expires_at:
            if datetime.utcnow() > approval.expires_at:
                approval.status = "expired"
                db.commit()

    @staticmethod
    def get_all_approvals(db: Session, status: Optional[str] = None) -> List[ApprovalResponse]:
        query = db.query(ApprovalRequest)
        if status:
            query = query.filter(ApprovalRequest.status == status)
        records = query.order_by(ApprovalRequest.created_at.desc()).all()

        # Update any expired records
        for r in records:
            ApprovalService._check_and_update_expiration(r, db)

        return [ApprovalResponse.model_validate(r) for r in records]

    @staticmethod
    def get_approval(db: Session, approval_id: str) -> Optional[ApprovalResponse]:
        approval = db.query(ApprovalRequest).filter(ApprovalRequest.id == approval_id).first()
        if not approval:
            return None
        ApprovalService._check_and_update_expiration(approval, db)
        return ApprovalResponse.model_validate(approval)

    @staticmethod
    def approve_action(
        db: Session, 
        approval_id: str, 
        payload: ApprovalActionRequest,
        actor: Optional[User] = None
    ) -> Optional[ApprovalResponse]:
        approval = db.query(ApprovalRequest).filter(ApprovalRequest.id == approval_id).first()
        if not approval:
            return None

        # 1. Enforce RBAC on approval action
        if actor and actor.role not in AUTHORIZED_REVIEWER_ROLES:
            raise HTTPException(
                status_code=403,
                detail=f"Access Denied: Role '{actor.role.value}' cannot authorize approvals. Authorized roles: {[r.value for r in AUTHORIZED_REVIEWER_ROLES]}."
            )

        # 2. Check for expiration
        ApprovalService._check_and_update_expiration(approval, db)
        if approval.status == "expired":
            raise ValueError("Approval request has EXPIRED and cannot be authorized.")

        # 3. Idempotency protection: already approved requests are safely returned
        if approval.status == "approved":
            return ApprovalResponse.model_validate(approval)

        if approval.status == "rejected":
            raise ValueError("Approval request was previously REJECTED and cannot be approved.")

        # 4. Verify step and cryptographic payload integrity
        step = db.query(WorkflowStep).filter(WorkflowStep.id == approval.step_id).first()
        if step and approval.payload_hash:
            current_hash = compute_payload_hash(step.tool_input or {})
            if current_hash != approval.payload_hash:
                raise ValueError("Payload has been modified after approval request was generated. Approval rejected for safety.")

        # 5. Transition state
        approval.status = "approved"
        approval.reviewed_at = datetime.utcnow()
        approval.reviewed_by = payload.reviewed_by or (actor.email if actor else "Compliance Reviewer")
        approval.comment = payload.comment

        if step:
            step.status = "approved"

        # 6. Audit logging with secret redaction
        log = ExecutionLog(
            workflow_id=approval.workflow_id,
            step_id=approval.step_id,
            actor=approval.reviewed_by,
            level="SUCCESS",
            event="HUMAN_APPROVAL_GRANTED",
            message=f"Action '{approval.tool_name}' ({approval.risk_level} risk) authorized by {approval.reviewed_by}.",
            details=redact_secrets({
                "approval_id": approval.id,
                "payload_hash": approval.payload_hash,
                "risk_level": approval.risk_level,
                "comment": approval.comment
            }),
            outcome="SUCCESS"
        )
        db.add(log)
        db.commit()
        db.refresh(approval)
        return ApprovalResponse.model_validate(approval)

    @staticmethod
    def reject_action(
        db: Session, 
        approval_id: str, 
        payload: ApprovalActionRequest,
        actor: Optional[User] = None
    ) -> Optional[ApprovalResponse]:
        approval = db.query(ApprovalRequest).filter(ApprovalRequest.id == approval_id).first()
        if not approval:
            return None

        # 1. Enforce RBAC
        if actor and actor.role not in AUTHORIZED_REVIEWER_ROLES:
            raise HTTPException(
                status_code=403,
                detail=f"Access Denied: Role '{actor.role.value}' cannot reject approvals. Authorized roles: {[r.value for r in AUTHORIZED_REVIEWER_ROLES]}."
            )

        ApprovalService._check_and_update_expiration(approval, db)
        if approval.status in {"expired", "rejected"}:
            return ApprovalResponse.model_validate(approval)

        approval.status = "rejected"
        approval.reviewed_at = datetime.utcnow()
        approval.reviewed_by = payload.reviewed_by or (actor.email if actor else "Compliance Reviewer")
        approval.comment = payload.comment

        step = db.query(WorkflowStep).filter(WorkflowStep.id == approval.step_id).first()
        if step:
            step.status = "rejected"

        # Update workflow status to failed
        wf = db.query(Workflow).filter(Workflow.id == approval.workflow_id).first()
        if wf:
            wf.status = "failed"

        log = ExecutionLog(
            workflow_id=approval.workflow_id,
            step_id=approval.step_id,
            actor=approval.reviewed_by,
            level="WARNING",
            event="HUMAN_APPROVAL_REJECTED",
            message=f"Action '{approval.tool_name}' rejected by {approval.reviewed_by}. Reason: {approval.comment or 'None specified'}",
            details=redact_secrets({
                "approval_id": approval.id,
                "risk_level": approval.risk_level,
                "comment": approval.comment
            }),
            outcome="FAILURE"
        )
        db.add(log)
        db.commit()
        db.refresh(approval)
        return ApprovalResponse.model_validate(approval)

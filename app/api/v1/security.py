from typing import Dict, Any, List, Optional
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.database.models import ExecutionLog
from app.core.auth import (
    User, 
    UserRole, 
    get_current_user, 
    require_roles, 
    require_permission,
    set_active_session_role,
    get_active_session_role,
    ROLE_PERMISSIONS
)
from app.core.security import redact_secrets

router = APIRouter(prefix="/security", tags=["Security & RBAC"])


class SecuritySettings(BaseModel):
    approval_expiration_hours: int = 24
    approval_risk_threshold: str = "HIGH"
    max_retries: int = 3
    concurrency_limit: int = 4
    secret_masking_enabled: bool = True
    rbac_enforced: bool = True
    active_session_role: str = "OPERATOR"
    available_roles: List[str] = [r.value for r in UserRole]

    model_config = ConfigDict(from_attributes=True)


class UpdateSecuritySettingsRequest(BaseModel):
    approval_expiration_hours: Optional[int] = None
    approval_risk_threshold: Optional[str] = None
    max_retries: Optional[int] = None
    concurrency_limit: Optional[int] = None


class SwitchRoleRequest(BaseModel):
    role: UserRole


_security_config = {
    "approval_expiration_hours": 24,
    "approval_risk_threshold": "HIGH",
    "max_retries": 3,
    "concurrency_limit": 4,
    "secret_masking_enabled": True,
    "rbac_enforced": True
}


@router.get("/settings", response_model=SecuritySettings)
def get_security_settings():
    """Returns current enterprise security configuration and RBAC status."""
    return SecuritySettings(
        approval_expiration_hours=_security_config["approval_expiration_hours"],
        approval_risk_threshold=_security_config["approval_risk_threshold"],
        max_retries=_security_config["max_retries"],
        concurrency_limit=_security_config["concurrency_limit"],
        secret_masking_enabled=_security_config["secret_masking_enabled"],
        rbac_enforced=_security_config["rbac_enforced"],
        active_session_role=get_active_session_role().value
    )


@router.patch("/settings", response_model=SecuritySettings)
def update_security_settings(
    req: UpdateSecuritySettingsRequest,
    user: User = Depends(require_permission("manage_policies"))
):
    """Updates security parameters. Restricted strictly to SUPER_ADMIN and WORKSPACE_OWNER."""
    if req.approval_expiration_hours is not None:
        _security_config["approval_expiration_hours"] = max(1, req.approval_expiration_hours)
    if req.approval_risk_threshold is not None:
        if req.approval_risk_threshold.upper() in {"LOW", "MEDIUM", "HIGH", "CRITICAL"}:
            _security_config["approval_risk_threshold"] = req.approval_risk_threshold.upper()
    if req.max_retries is not None:
        _security_config["max_retries"] = max(1, min(10, req.max_retries))
    if req.concurrency_limit is not None:
        _security_config["concurrency_limit"] = max(1, min(16, req.concurrency_limit))

    return get_security_settings()


@router.get("/me")
def get_current_user_profile(user: User = Depends(get_current_user)):
    """Returns authenticated user profile, assigned role, and effective permissions."""
    return {
        "id": user.id,
        "email": user.email,
        "name": user.name,
        "role": user.role.value,
        "workspace_id": user.workspace_id,
        "permissions": list(ROLE_PERMISSIONS.get(user.role, set()))
    }


@router.post("/switch-role")
def switch_active_role(req: SwitchRoleRequest):
    """Allows UI and integration testing to switch the active role context dynamically."""
    set_active_session_role(req.role)
    return {
        "status": "success",
        "active_role": req.role.value,
        "message": f"Session role switched to '{req.role.value}'."
    }


@router.get("/audit-logs")
def list_audit_logs(
    workflow_id: Optional[str] = Query(None),
    level: Optional[str] = Query(None),
    event: Optional[str] = Query(None),
    limit: int = Query(50, le=200),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user)
) -> List[Dict[str, Any]]:
    """
    Retrieves immutable audit and activity logs with secret redaction applied.
    Accessible to all authorized roles.
    """
    query = db.query(ExecutionLog)
    if workflow_id:
        query = query.filter(ExecutionLog.workflow_id == workflow_id)
    if level:
        query = query.filter(ExecutionLog.level == level)
    if event:
        query = query.filter(ExecutionLog.event.ilike(f"%{event}%"))

    records = query.order_by(ExecutionLog.timestamp.desc()).limit(limit).all()

    return [
        {
            "id": r.id,
            "workflow_id": r.workflow_id,
            "step_id": r.step_id,
            "actor": getattr(r, "actor", "system") or "system",
            "level": r.level,
            "event": r.event,
            "message": redact_secrets(r.message),
            "details": redact_secrets(r.details or {}),
            "outcome": getattr(r, "outcome", "SUCCESS") or "SUCCESS",
            "timestamp": r.timestamp.isoformat() if r.timestamp else None
        }
        for r in records
    ]


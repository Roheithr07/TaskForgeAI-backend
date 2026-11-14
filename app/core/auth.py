from enum import Enum
from typing import Optional, List, Dict, Set
from fastapi import Header, HTTPException, Depends, Query, Request
from pydantic import BaseModel, ConfigDict


class UserRole(str, Enum):
    SUPER_ADMIN = "SUPER_ADMIN"
    WORKSPACE_OWNER = "WORKSPACE_OWNER"
    OPERATOR = "OPERATOR"
    REVIEWER = "REVIEWER"
    VIEWER = "VIEWER"


class User(BaseModel):
    id: str
    email: str
    name: str
    role: UserRole
    workspace_id: str = "default_workspace"

    model_config = ConfigDict(from_attributes=True)


ROLE_PERMISSIONS: Dict[UserRole, Set[str]] = {
    UserRole.SUPER_ADMIN: {
        "manage_workspace",
        "manage_policies",
        "manage_users",
        "manage_integrations",
        "create_workflow",
        "execute_workflow",
        "approve_action",
        "reject_action",
        "view_workflow",
        "view_reports",
        "execute_tool"
    },
    UserRole.WORKSPACE_OWNER: {
        "manage_workspace",
        "manage_integrations",
        "create_workflow",
        "execute_workflow",
        "approve_action",
        "reject_action",
        "view_workflow",
        "view_reports",
        "execute_tool"
    },
    UserRole.OPERATOR: {
        "create_workflow",
        "execute_workflow",
        "request_approval",
        "view_workflow",
        "view_reports",
        "execute_tool"
    },
    UserRole.REVIEWER: {
        "approve_action",
        "reject_action",
        "view_workflow",
        "view_reports"
    },
    UserRole.VIEWER: {
        "view_workflow",
        "view_reports"
    }
}

# Pre-provisioned system accounts
DEMO_USERS: Dict[str, User] = {
    "admin": User(id="usr_admin", email="admin@taskforge.ai", name="Super Administrator", role=UserRole.SUPER_ADMIN),
    "owner": User(id="usr_owner", email="owner@taskforge.ai", name="Workspace Owner", role=UserRole.WORKSPACE_OWNER),
    "operator": User(id="usr_operator", email="operator@taskforge.ai", name="Lead AI Operator", role=UserRole.OPERATOR),
    "reviewer": User(id="usr_reviewer", email="reviewer@taskforge.ai", name="Compliance Reviewer", role=UserRole.REVIEWER),
    "viewer": User(id="usr_viewer", email="viewer@taskforge.ai", name="Audit Viewer", role=UserRole.VIEWER),
}

# Active global default role (can be toggled by frontend or config)
_active_session_role: UserRole = UserRole.WORKSPACE_OWNER


def set_active_session_role(role: UserRole):
    global _active_session_role
    _active_session_role = role


def get_active_session_role() -> UserRole:
    return _active_session_role


def get_current_user(
    x_user_role: Optional[str] = Header(None, alias="X-User-Role"),
    x_user_id: Optional[str] = Header(None, alias="X-User-Id"),
    role_query: Optional[str] = Query(None, alias="role")
) -> User:
    """
    Authenticates the requesting actor and resolves their role context.
    Precedence: X-User-Role header > ?role query param > active session role.
    """
    selected_role = x_user_role or role_query
    if selected_role:
        role_upper = selected_role.upper().strip()
        try:
            matched_role = UserRole(role_upper)
            return User(
                id=x_user_id or f"usr_{matched_role.value.lower()}",
                email=f"{matched_role.value.lower()}@taskforge.ai",
                name=f"{matched_role.value.replace('_', ' ').title()} Actor",
                role=matched_role
            )
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid role '{selected_role}'. Supported roles: {[r.value for r in UserRole]}"
            )

    # Use active session role
    role = get_active_session_role()
    return User(
        id=f"usr_{role.value.lower()}",
        email=f"{role.value.lower()}@taskforge.ai",
        name=f"{role.value.replace('_', ' ').title()} Actor",
        role=role
    )


def require_roles(allowed_roles: List[UserRole]):
    """
    Enforces that the authenticated user possesses one of the designated roles.
    Raises 403 Forbidden with detailed security telemetry if unauthorized.
    """
    def dependency(user: User = Depends(get_current_user)) -> User:
        if user.role not in allowed_roles:
            raise HTTPException(
                status_code=403,
                detail=f"Access Denied: Role '{user.role.value}' is unauthorized. Required role in {[r.value for r in allowed_roles]}."
            )
        return user
    return dependency


def require_permission(permission: str):
    """
    Enforces that the actor possesses a specific granular permission.
    """
    def dependency(user: User = Depends(get_current_user)) -> User:
        user_perms = ROLE_PERMISSIONS.get(user.role, set())
        if permission not in user_perms:
            raise HTTPException(
                status_code=403,
                detail=f"Access Denied: Role '{user.role.value}' lacks required permission '{permission}'."
            )
        return user
    return dependency

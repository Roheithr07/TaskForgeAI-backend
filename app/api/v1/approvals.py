from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.schemas.approval import ApprovalResponse, ApprovalActionRequest
from app.services.approval_service import ApprovalService
from app.core.auth import User, get_current_user

router = APIRouter(prefix="/approvals", tags=["Approvals"])


@router.get("", response_model=List[ApprovalResponse])
def list_approvals(status: Optional[str] = Query(None), db: Session = Depends(get_db)):
    return ApprovalService.get_all_approvals(db, status=status)


@router.get("/{approval_id}", response_model=ApprovalResponse)
def get_approval(approval_id: str, db: Session = Depends(get_db)):
    approval = ApprovalService.get_approval(db, approval_id)
    if not approval:
        raise HTTPException(status_code=404, detail="Approval request not found")
    return approval


@router.post("/{approval_id}/approve", response_model=ApprovalResponse)
def approve_action(
    approval_id: str, 
    payload: ApprovalActionRequest, 
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    try:
        result = ApprovalService.approve_action(db, approval_id, payload, actor=current_user)
        if not result:
            raise HTTPException(status_code=404, detail="Approval request not found")
        return result
    except HTTPException as he:
        raise he
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))


@router.post("/{approval_id}/reject", response_model=ApprovalResponse)
def reject_action(
    approval_id: str, 
    payload: ApprovalActionRequest, 
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    try:
        result = ApprovalService.reject_action(db, approval_id, payload, actor=current_user)
        if not result:
            raise HTTPException(status_code=404, detail="Approval request not found")
        return result
    except HTTPException as he:
        raise he
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))

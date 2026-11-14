import uuid
from datetime import datetime
from sqlalchemy import Column, String, Text, Boolean, Integer, DateTime, ForeignKey, JSON
from sqlalchemy.orm import relationship

from app.database.session import Base


def generate_uuid() -> str:
    return str(uuid.uuid4())


class Workflow(Base):
    __tablename__ = "workflows"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    title = Column(String(255), nullable=False)
    original_prompt = Column(Text, nullable=False)
    status = Column(String(50), default="created")  # created, planned, running, executing, awaiting_approval, completed, failed
    plan_summary = Column(Text, nullable=True)
    thread_id = Column(String(100), nullable=True)
    template_id = Column(String(50), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    steps = relationship("WorkflowStep", back_populates="workflow", cascade="all, delete-orphan", order_by="WorkflowStep.step_number")
    executions = relationship("ExecutionLog", back_populates="workflow", cascade="all, delete-orphan")
    approvals = relationship("ApprovalRequest", back_populates="workflow", cascade="all, delete-orphan")


class WorkflowStep(Base):
    __tablename__ = "workflow_steps"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    workflow_id = Column(String(36), ForeignKey("workflows.id", ondelete="CASCADE"), nullable=False)
    step_number = Column(Integer, nullable=False)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    tool_name = Column(String(100), nullable=False)
    tool_input = Column(JSON, nullable=True)
    tool_output = Column(JSON, nullable=True)
    dependencies = Column(JSON, default=list)  # list of step numbers this step depends on
    retry_count = Column(Integer, default=0)
    max_retries = Column(Integer, default=3)
    error_message = Column(Text, nullable=True)
    is_sensitive = Column(Boolean, default=False)
    status = Column(String(50), default="pending")  # pending, ready, running, executing, awaiting_approval, completed, failed, blocked, rejected, skipped
    verified = Column(Boolean, default=False)
    verification_notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)

    workflow = relationship("Workflow", back_populates="steps")
    approval = relationship("ApprovalRequest", back_populates="step", uselist=False, cascade="all, delete-orphan")


class ApprovalRequest(Base):
    __tablename__ = "approval_requests"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    workflow_id = Column(String(36), ForeignKey("workflows.id", ondelete="CASCADE"), nullable=False)
    step_id = Column(String(36), ForeignKey("workflow_steps.id", ondelete="CASCADE"), nullable=False)
    requesting_user = Column(String(100), default="operator@taskforge.ai")
    assigned_reviewer = Column(String(100), default="REVIEWER")
    tool_name = Column(String(100), nullable=False)
    action_description = Column(Text, nullable=False)
    payload_preview = Column(JSON, nullable=True)
    payload_hash = Column(String(64), nullable=True)
    risk_level = Column(String(20), default="HIGH")  # LOW, MEDIUM, HIGH, CRITICAL
    status = Column(String(50), default="pending")  # pending, approved, rejected, expired, cancelled
    expires_at = Column(DateTime, nullable=True)
    reviewed_at = Column(DateTime, nullable=True)
    reviewed_by = Column(String(100), nullable=True)
    comment = Column(Text, nullable=True)
    execution_status = Column(String(50), default="pending")  # pending, executing, completed, failed
    created_at = Column(DateTime, default=datetime.utcnow)

    workflow = relationship("Workflow", back_populates="approvals")
    step = relationship("WorkflowStep", back_populates="approval")


class ExecutionLog(Base):
    __tablename__ = "execution_logs"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    workflow_id = Column(String(36), ForeignKey("workflows.id", ondelete="CASCADE"), nullable=False)
    step_id = Column(String(36), nullable=True)
    actor = Column(String(100), default="system")
    level = Column(String(20), default="INFO")  # INFO, WARNING, ERROR, SUCCESS, CRITICAL
    event = Column(String(100), nullable=False)
    message = Column(Text, nullable=False)
    details = Column(JSON, nullable=True)
    outcome = Column(String(50), default="SUCCESS")  # SUCCESS, FAILURE, PENDING, HALTED
    timestamp = Column(DateTime, default=datetime.utcnow)

    workflow = relationship("Workflow", back_populates="executions")

import hashlib
import json
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session

from app.core.security import redact_secrets

from app.database.models import Workflow, WorkflowStep, ApprovalRequest, ExecutionLog
from app.schemas.workflow import (
    WorkflowCreateRequest,
    WorkflowResponse,
    WorkflowStatusResponse,
    StepResponse,
    StepPlanItem,
    WorkflowPlanUpdateRequest,
    WorkflowPlanValidationResult,
    WorkflowHistoryResponse
)
from app.agents.policy import PolicyChecker
from app.tools.registry import registry
from app.agents.planner import AIPlanner
from app.graph.workflow_graph import build_dag_workflow_graph, compute_payload_hash
from app.graph.dag_scheduler import DAGScheduler
from app.graph.checkpointer import get_async_checkpointer, list_thread_checkpoints
from app.graph.state import WorkflowState


class WorkflowService:
    @staticmethod
    async def create_and_plan_workflow(db: Session, request: WorkflowCreateRequest) -> WorkflowResponse:
        # 1. Generate plan using AIPlanner
        plan = await AIPlanner.generate_plan(request.prompt, request.title)

        # 2. Persist Workflow
        thread_id = f"thread_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}_{request.prompt[:8].replace(' ', '_')}"
        wf = Workflow(
            title=plan.workflow_name,
            original_prompt=request.prompt,
            status="planned",
            plan_summary=plan.summary,
            thread_id=thread_id
        )
        db.add(wf)
        db.flush()

        # 3. Persist Steps with dependencies
        for s in plan.steps:
            step = WorkflowStep(
                workflow_id=wf.id,
                step_number=s.step_id,
                title=s.name,
                description=s.description,
                tool_name=s.tool_name,
                tool_input=s.input_parameters,
                dependencies=s.dependencies,
                is_sensitive=s.requires_approval,
                status="pending"
            )
            db.add(step)

        # 4. Create initial execution log
        log = ExecutionLog(
            workflow_id=wf.id,
            level="INFO",
            event="WORKFLOW_PLANNED",
            message=f"Workflow planned with {len(plan.steps)} DAG steps (Complexity: {plan.complexity.value}).",
            details={
                "steps_count": len(plan.steps),
                "strategy": plan.execution_strategy,
                "provider_mode": plan.provider_mode
            }
        )
        db.add(log)
        db.commit()
        db.refresh(wf)
        return WorkflowResponse.model_validate(wf)

    @staticmethod
    def get_all_workflows(db: Session) -> List[WorkflowResponse]:
        wfs = db.query(Workflow).order_by(Workflow.created_at.desc()).all()
        return [WorkflowResponse.model_validate(wf) for wf in wfs]

    @staticmethod
    def get_workflow_by_id(db: Session, workflow_id: str) -> Optional[WorkflowResponse]:
        wf = db.query(Workflow).filter(Workflow.id == workflow_id).first()
        if not wf:
            return None
        return WorkflowResponse.model_validate(wf)

    @staticmethod
    async def execute_workflow(db: Session, workflow_id: str) -> WorkflowResponse:
        wf = db.query(Workflow).filter(Workflow.id == workflow_id).first()
        if not wf:
            raise ValueError(f"Workflow '{workflow_id}' not found.")

        steps: List[WorkflowStep] = db.query(WorkflowStep).filter(
            WorkflowStep.workflow_id == workflow_id
        ).order_by(WorkflowStep.step_number).all()

        if not wf.thread_id:
            wf.thread_id = f"thread_{wf.id}"
            db.commit()

        # Build DAG step dictionary {step_number: step_data}
        steps_dict: Dict[int, Dict[str, Any]] = {}
        for s in steps:
            steps_dict[s.step_number] = {
                "id": s.id,
                "step_id": s.step_number,
                "name": s.title,
                "description": s.description,
                "tool_name": s.tool_name,
                "input_parameters": s.tool_input or {},
                "dependencies": s.dependencies or [],
                "expected_output": "",
                "status": s.status,
                "retry_count": s.retry_count,
                "max_retries": s.max_retries,
                "error_message": s.error_message,
                "is_sensitive": s.is_sensitive,
                "requires_approval": s.is_sensitive,
                "tool_output": s.tool_output or {},
                "verified": s.verified,
                "verification_notes": s.verification_notes
            }

        # Check if any step was approved by human supervisor
        approved_approvals = db.query(ApprovalRequest).filter(
            ApprovalRequest.workflow_id == workflow_id,
            ApprovalRequest.status == "approved"
        ).all()
        for app in approved_approvals:
            # find corresponding step
            target_step = next((s for s in steps if s.id == app.step_id), None)
            if target_step and target_step.step_number in steps_dict:
                steps_dict[target_step.step_number]["status"] = "approved"

        initial_state: WorkflowState = {
            "workflow_id": wf.id,
            "thread_id": wf.thread_id,
            "original_prompt": wf.original_prompt,
            "steps": steps_dict,
            "ready_steps": [],
            "status": "running",
            "pending_approval": None,
            "execution_logs": [],
            "concurrency_limit": 4,
            "retry_config": {
                "max_retries": 3,
                "initial_delay": 0.5,
                "max_delay": 4.0,
                "backoff_multiplier": 2.0
            },
            "error": None
        }

        wf.status = "running"
        db.commit()

        # Invoke LangGraph DAG with persistent thread checkpointer
        checkpointer = await get_async_checkpointer()
        graph = build_dag_workflow_graph(checkpointer=checkpointer)
        config = {"configurable": {"thread_id": wf.thread_id}}
        final_state = await graph.ainvoke(initial_state, config=config)

        # Synchronize back to database
        wf.status = final_state.get("status", "completed")

        for sid, updated_s in final_state.get("steps", {}).items():
            db_s = next((s for s in steps if s.step_number == int(sid)), None)
            if db_s:
                db_s.status = updated_s.get("status", db_s.status)
                db_s.tool_output = updated_s.get("tool_output", db_s.tool_output)
                db_s.verified = updated_s.get("verified", db_s.verified)
                db_s.verification_notes = updated_s.get("verification_notes", db_s.verification_notes)
                db_s.retry_count = updated_s.get("retry_count", db_s.retry_count)
                db_s.error_message = updated_s.get("error_message", db_s.error_message)
                if updated_s.get("completed_at"):
                    db_s.completed_at = datetime.fromisoformat(updated_s["completed_at"])

        # Persist approval request if state halted for approval
        pending_approval = final_state.get("pending_approval")
        if pending_approval:
            target_step = next((s for s in steps if s.step_number == int(pending_approval["step_id"])), None)
            step_uuid = target_step.id if target_step else str(pending_approval["step_id"])
            
            existing = db.query(ApprovalRequest).filter(
                ApprovalRequest.workflow_id == wf.id,
                ApprovalRequest.step_id == step_uuid,
                ApprovalRequest.status == "pending"
            ).first()

            if not existing:
                req = ApprovalRequest(
                    workflow_id=wf.id,
                    step_id=step_uuid,
                    requesting_user="operator@taskforge.ai",
                    assigned_reviewer="REVIEWER",
                    tool_name=pending_approval["tool_name"],
                    action_description=pending_approval["action_description"],
                    payload_preview=redact_secrets(pending_approval.get("payload_preview")),
                    payload_hash=pending_approval.get("payload_hash"),
                    risk_level=pending_approval.get("risk_level", "HIGH"),
                    expires_at=datetime.utcnow() + timedelta(hours=24),
                    status="pending",
                    execution_status="pending"
                )
                db.add(req)

        # Persist execution logs with secret redaction
        for log_entry in final_state.get("execution_logs", []):
            db_log = ExecutionLog(
                workflow_id=wf.id,
                step_id=log_entry.get("step_id"),
                actor="langgraph_orchestrator",
                level="INFO",
                event=log_entry.get("event", "STATE_TRANSITION"),
                message=log_entry.get("message", ""),
                details=redact_secrets(log_entry),
                outcome="HALTED" if pending_approval else ("FAILURE" if wf.status in {"failed", "completed_with_errors"} else "SUCCESS")
            )
            db.add(db_log)

        db.commit()
        db.refresh(wf)
        return WorkflowResponse.model_validate(wf)

    @staticmethod
    def get_status(db: Session, workflow_id: str) -> Optional[WorkflowStatusResponse]:
        wf = db.query(Workflow).filter(Workflow.id == workflow_id).first()
        if not wf:
            return None

        steps = db.query(WorkflowStep).filter(
            WorkflowStep.workflow_id == workflow_id
        ).order_by(WorkflowStep.step_number).all()

        completed_count = sum(1 for s in steps if s.status == "completed")
        current_step = next((s for s in steps if s.status in ["running", "executing", "awaiting_approval", "pending", "ready"]), None)

        pending_approval = db.query(ApprovalRequest).filter(
            ApprovalRequest.workflow_id == workflow_id,
            ApprovalRequest.status == "pending"
        ).first()

        return WorkflowStatusResponse(
            id=wf.id,
            status=wf.status,
            steps_total=len(steps),
            steps_completed=completed_count,
            current_step=StepResponse.model_validate(current_step) if current_step else None,
            has_pending_approval=bool(pending_approval),
            pending_approval_id=pending_approval.id if pending_approval else None
        )

    @staticmethod
    def get_dag_graph(db: Session, workflow_id: str) -> Dict[str, Any]:
        """
        Returns full topological DAG structure and parallel branch grouping for the UI.
        """
        wf = db.query(Workflow).filter(Workflow.id == workflow_id).first()
        if not wf:
            raise ValueError(f"Workflow '{workflow_id}' not found.")

        steps_dict = {
            s.step_number: {
                "step_id": s.step_number,
                "title": s.title,
                "tool_name": s.tool_name,
                "dependencies": s.dependencies or [],
                "status": s.status,
                "is_sensitive": s.is_sensitive,
                "retry_count": s.retry_count
            }
            for s in wf.steps
        }

        levels = DAGScheduler.compute_dag_levels(steps_dict)

        return {
            "workflow_id": wf.id,
            "title": wf.title,
            "status": wf.status,
            "thread_id": wf.thread_id,
            "levels": levels,
            "steps": steps_dict,
            "total_steps": len(wf.steps)
        }

    @staticmethod
    async def get_checkpoints(db: Session, workflow_id: str) -> List[Dict[str, Any]]:
        wf = db.query(Workflow).filter(Workflow.id == workflow_id).first()
        if not wf or not wf.thread_id:
            return []
        return await list_thread_checkpoints(wf.thread_id)

    @staticmethod
    def validate_workflow_plan(
        db: Session, 
        workflow_id: str, 
        proposed_steps: Optional[List[StepPlanItem]] = None
    ) -> WorkflowPlanValidationResult:
        wf = db.query(Workflow).filter(Workflow.id == workflow_id).first()
        if not wf:
            raise ValueError(f"Workflow '{workflow_id}' not found.")

        steps_to_check = proposed_steps
        if steps_to_check is None:
            # Validate current database steps
            steps_to_check = [
                StepPlanItem(
                    step_number=s.step_number,
                    title=s.title,
                    description=s.description,
                    tool_name=s.tool_name,
                    tool_input=s.tool_input or {},
                    dependencies=s.dependencies or [],
                    is_sensitive=s.is_sensitive,
                    enabled=True
                )
                for s in wf.steps
            ]

        errors: List[str] = []
        warnings: List[str] = []
        step_numbers = set()
        registered_tools = set(registry._tools.keys())

        # Filter enabled steps
        active_steps = [s for s in steps_to_check if s.enabled]
        if not active_steps:
            return WorkflowPlanValidationResult(
                valid=False,
                errors=["Workflow must contain at least one enabled execution step."],
                warnings=warnings,
                dependency_levels=[]
            )

        # 1. Uniqueness & Tool Validation
        for s in active_steps:
            if s.step_number in step_numbers:
                errors.append(f"Duplicate step number detected: {s.step_number}")
            step_numbers.add(s.step_number)

            if s.tool_name not in registered_tools:
                errors.append(f"Step {s.step_number} specifies unknown tool '{s.tool_name}'. Registered tools: {sorted(list(registered_tools))}")

            # Check sensitive policy
            is_sens, reason = PolicyChecker.evaluate_step(s.tool_name, s.tool_input or {})
            if is_sens and not s.is_sensitive:
                warnings.append(f"Step {s.step_number} ('{s.tool_name}') is classified sensitive by security policy and requires approval.")

        # 2. Dependency checks
        dep_graph: Dict[int, List[int]] = {}
        for s in active_steps:
            for dep in s.dependencies:
                if dep == s.step_number:
                    errors.append(f"Step {s.step_number} cannot depend on itself.")
                elif dep not in step_numbers:
                    errors.append(f"Step {s.step_number} declares missing dependency on step #{dep}.")
            dep_graph[s.step_number] = s.dependencies

        # 3. Cycle Detection
        if not errors:
            visited = {}  # 0 = unvisited, 1 = visiting, 2 = visited
            cycle_found = False

            def dfs(node: int, path: List[int]):
                nonlocal cycle_found
                visited[node] = 1
                for neighbor in dep_graph.get(node, []):
                    if visited.get(neighbor) == 1:
                        cycle_found = True
                        cycle_str = " -> ".join(map(str, path + [neighbor]))
                        errors.append(f"Circular dependency detected in customized plan: {cycle_str}")
                        return
                    elif visited.get(neighbor, 0) == 0:
                        dfs(neighbor, path + [neighbor])
                visited[node] = 2

            for sn in active_steps:
                if visited.get(sn.step_number, 0) == 0:
                    dfs(sn.step_number, [sn.step_number])
                if cycle_found:
                    break

        # 4. Topological Levels
        levels: List[List[int]] = []
        if not errors:
            steps_dict = {
                s.step_number: {
                    "step_id": s.step_number,
                    "dependencies": s.dependencies
                }
                for s in active_steps
            }
            levels = DAGScheduler.compute_dag_levels(steps_dict)

        return WorkflowPlanValidationResult(
            valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
            dependency_levels=levels
        )

    @staticmethod
    def update_workflow_plan(
        db: Session, 
        workflow_id: str, 
        req: WorkflowPlanUpdateRequest
    ) -> WorkflowResponse:
        wf = db.query(Workflow).filter(Workflow.id == workflow_id).first()
        if not wf:
            raise ValueError(f"Workflow '{workflow_id}' not found.")

        if wf.status in ["executing", "running"]:
            raise ValueError("Cannot modify workflow plan while execution is actively running.")

        # Validate proposed plan
        val = WorkflowService.validate_workflow_plan(db, workflow_id, req.steps)
        if not val.valid:
            raise ValueError(f"Invalid workflow plan: {'; '.join(val.errors)}")

        if req.title:
            wf.title = req.title.strip()

        # Invalidate / cancel any pending approvals attached to existing steps to enforce payload security
        pending_apps = db.query(ApprovalRequest).filter(
            ApprovalRequest.workflow_id == workflow_id,
            ApprovalRequest.status == "pending"
        ).all()
        for app in pending_apps:
            app.status = "cancelled"
            app.comment = "Cancelled due to workflow plan customization prior to execution."

        # Delete existing steps and recreate from validated customized plan
        db.query(WorkflowStep).filter(WorkflowStep.workflow_id == workflow_id).delete()

        # Re-insert steps in topological order
        active_steps = [s for s in req.steps if s.enabled]
        for s in active_steps:
            is_sens, _ = PolicyChecker.evaluate_step(s.tool_name, s.tool_input or {})
            new_step = WorkflowStep(
                workflow_id=wf.id,
                step_number=s.step_number,
                title=s.title,
                description=s.description or "",
                tool_name=s.tool_name,
                tool_input=s.tool_input or {},
                dependencies=s.dependencies or [],
                is_sensitive=bool(s.is_sensitive or is_sens),
                status="pending"
            )
            db.add(new_step)

        # Update workflow status back to planned
        wf.status = "planned"

        log = ExecutionLog(
            workflow_id=wf.id,
            actor="operator",
            level="INFO",
            event="WORKFLOW_PLAN_CUSTOMIZED",
            message=f"Workflow customized: updated to {len(active_steps)} steps across {len(val.dependency_levels)} topological levels.",
            details={"steps_count": len(active_steps), "levels": val.dependency_levels},
            outcome="SUCCESS"
        )
        db.add(log)
        db.commit()
        db.refresh(wf)
        return WorkflowResponse.model_validate(wf)

    @staticmethod
    def get_workflow_history(db: Session, workflow_id: str) -> WorkflowHistoryResponse:
        wf = db.query(Workflow).filter(Workflow.id == workflow_id).first()
        if not wf:
            raise ValueError(f"Workflow '{workflow_id}' not found.")

        total_steps = len(wf.steps)
        completed_steps = sum(1 for s in wf.steps if s.status == "completed")
        total_logs = len(wf.executions)
        
        # Count checkpoints
        checkpoints_count = 0
        if wf.thread_id:
            try:
                import asyncio
                # Use sync checkpointer query
                from app.graph.checkpointer import get_async_checkpointer
                # Alternatively count from logs
                checkpoints_count = sum(1 for l in wf.executions if l.event in ["STEP_EXECUTION_COMPLETED", "POLICY_INTERRUPT_TRIGGERED", "WORKFLOW_GRAPH_INITIALIZED"])
            except Exception:
                checkpoints_count = 0

        return WorkflowHistoryResponse(
            workflow_id=wf.id,
            title=wf.title,
            status=wf.status,
            created_at=wf.created_at,
            updated_at=wf.updated_at,
            total_steps=total_steps,
            completed_steps=completed_steps,
            checkpoints_count=checkpoints_count,
            total_logs_count=total_logs
        )

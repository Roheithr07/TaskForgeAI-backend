import asyncio
import hashlib
import json
import random
from datetime import datetime
from typing import Dict, Any, List, Literal

from langgraph.graph import StateGraph, END
from app.graph.state import WorkflowState
from app.graph.dag_scheduler import DAGScheduler
from app.graph.checkpointer import get_async_checkpointer, get_checkpointer
from app.agents.policy import PolicyChecker
from app.agents.verifier import ResultVerifier
from app.tools.registry import registry


def compute_payload_hash(payload: Any) -> str:
    serialized = json.dumps(payload, sort_keys=True, default=str)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


async def initialize_node(state: WorkflowState) -> Dict[str, Any]:
    steps = dict(state.get("steps", {}))
    DAGScheduler.update_blocked_steps(steps)
    
    logs = [{
        "timestamp": datetime.utcnow().isoformat(),
        "event": "WORKFLOW_GRAPH_INITIALIZED",
        "message": f"DAG initialized with {len(steps)} steps across topological dependencies."
    }]
    
    return {
        "steps": steps,
        "status": "running",
        "execution_logs": logs
    }


async def schedule_node(state: WorkflowState) -> Dict[str, Any]:
    steps = dict(state.get("steps", {}))
    concurrency_limit = state.get("concurrency_limit", 4)
    
    # Update any blocked dependencies
    DAGScheduler.update_blocked_steps(steps)
    
    # Find steps ready for execution
    ready = DAGScheduler.get_ready_steps(steps, concurrency_limit=concurrency_limit)
    
    logs = [{
        "timestamp": datetime.utcnow().isoformat(),
        "event": "DAG_DEPENDENCY_RESOLVED",
        "message": f"DAG scheduler identified {len(ready)} ready step(s): {ready}."
    }]
    
    return {
        "steps": steps,
        "ready_steps": ready,
        "execution_logs": logs
    }


async def check_approval_node(state: WorkflowState) -> Dict[str, Any]:
    steps = dict(state.get("steps", {}))
    ready_steps = list(state.get("ready_steps", []))
    logs = []
    
    # Check if any of the ready steps requires approval and is not yet approved
    for step_id in ready_steps:
        step = steps.get(step_id)
        if not step:
            continue
            
        tool_name = step.get("tool_name", "")
        tool_input = step.get("input_parameters", {})
        status = str(step.get("status", "")).lower()
        
        is_sensitive, reason = PolicyChecker.evaluate_step(tool_name, tool_input)
        
        if is_sensitive and status != "approved":
            step["status"] = "awaiting_approval"
            payload_hash = compute_payload_hash(tool_input)
            risk_level = PolicyChecker.classify_risk(tool_name, tool_input)
            
            approval_info = {
                "step_id": step_id,
                "tool_name": tool_name,
                "action_description": f"Approval required for sensitive operation '{tool_name}' (Step {step_id}).",
                "payload_preview": tool_input,
                "payload_hash": payload_hash,
                "risk_level": risk_level,
                "reason": reason
            }
            
            logs.append({
                "timestamp": datetime.utcnow().isoformat(),
                "event": "POLICY_INTERRUPT_TRIGGERED",
                "step_id": str(step_id),
                "message": f"Execution halted at Step {step_id}: {reason}. Awaiting supervisor decision.",
                "details": approval_info
            })
            
            return {
                "steps": {step_id: step},
                "status": "awaiting_approval",
                "pending_approval": approval_info,
                "execution_logs": logs
            }

    return {
        "execution_logs": logs
    }


async def _execute_single_step(
    step_id: int, 
    step_data: Dict[str, Any], 
    retry_config: Dict[str, Any],
    workflow_id: str
) -> Dict[str, Any]:
    tool_name = step_data.get("tool_name", "")
    tool_input = step_data.get("input_parameters", {})
    retry_count = step_data.get("retry_count", 0)
    max_retries = step_data.get("max_retries", retry_config.get("max_retries", 3))
    
    # Bounded exponential backoff with jitter if this is a retry attempt
    if retry_count > 0:
        initial_delay = retry_config.get("initial_delay", 1.0)
        multiplier = retry_config.get("backoff_multiplier", 2.0)
        max_delay = retry_config.get("max_delay", 8.0)
        delay = min(max_delay, initial_delay * (multiplier ** (retry_count - 1))) + random.uniform(0.05, 0.2)
        await asyncio.sleep(delay)

    tool = registry.get_tool(tool_name)
    if not tool:
        return {
            "status": "failed",
            "error_message": f"Tool '{tool_name}' not registered in registry. (DEFINITELY_FAILED)",
            "retry_count": retry_count
        }

    # Inject stable idempotency key for external dispatch tools
    if tool_name == "email_sending" and not tool_input.get("idempotency_key"):
        tool_input = dict(tool_input)
        tool_input["idempotency_key"] = f"idem_{workflow_id}_{step_id}_{compute_payload_hash(tool_input)[:16]}"

    try:
        output = await registry.execute_tool(tool_name, tool_input)
        verified, notes = ResultVerifier.verify(tool_name, output)
        
        if verified:
            return {
                "status": "completed",
                "tool_output": output,
                "verified": True,
                "verification_notes": notes,
                "completed_at": datetime.utcnow().isoformat()
            }
        else:
            # Verification failure
            if retry_count < max_retries:
                return {
                    "status": "retrying",
                    "retry_count": retry_count + 1,
                    "error_message": f"Verification failed: {notes} (TRANSIENT_FAILURE)"
                }
            else:
                return {
                    "status": "failed",
                    "error_message": f"Verification failed after max retries: {notes} (PERMANENT_FAILURE)",
                    "retry_count": retry_count
                }
    except Exception as e:
        err_str = str(e)
        # Classify failure: do NOT retry irreversible sensitive actions with uncertain outcome
        is_sensitive = getattr(tool, "is_sensitive", False)
        is_uncertain = is_sensitive and any(kw in err_str.lower() for kw in ["timeout", "connection reset", "network", "timed out"])

        if is_uncertain:
            return {
                "status": "failed",
                "error_message": f"Uncertain external outcome on sensitive operation '{tool_name}': {err_str}. Automatic retry blocked to prevent duplicate side effects. (UNCERTAIN_OUTCOME)",
                "retry_count": retry_count
            }

        # Non-retryable definitive failures
        if any(term in err_str.lower() for term in ["validation error", "security restriction", "forbidden", "not found"]):
            return {
                "status": "failed",
                "error_message": f"Non-retryable execution error: {err_str} (DEFINITELY_FAILED)",
                "retry_count": retry_count
            }

        if retry_count < max_retries:
            return {
                "status": "retrying",
                "retry_count": retry_count + 1,
                "error_message": f"{err_str} (TRANSIENT_FAILURE)"
            }
        else:
            return {
                "status": "failed",
                "error_message": f"Execution error after max retries: {err_str} (PERMANENT_FAILURE)",
                "retry_count": retry_count
            }


Tuple_ExecutionResult = Dict[str, Any]


async def execute_parallel_node(state: WorkflowState) -> Dict[str, Any]:
    steps = dict(state.get("steps", {}))
    ready_steps = list(state.get("ready_steps", []))
    retry_config = state.get("retry_config", {"max_retries": 3, "initial_delay": 1.0, "max_delay": 8.0, "backoff_multiplier": 2.0})
    workflow_id = state.get("workflow_id", "")
    concurrency_limit = state.get("concurrency_limit", 4)

    semaphore = asyncio.Semaphore(concurrency_limit)
    step_updates: Dict[int, Dict[str, Any]] = {}
    logs: List[Dict[str, Any]] = []

    async def worker(sid: int):
        async with semaphore:
            s_data = dict(steps[sid])
            logs.append({
                "timestamp": datetime.utcnow().isoformat(),
                "event": "STEP_EXECUTION_START",
                "step_id": str(sid),
                "message": f"Executing Step {sid} ('{s_data.get('name')}') using tool '{s_data.get('tool_name')}'."
            })
            
            result = await _execute_single_step(sid, s_data, retry_config, workflow_id)
            step_updates[sid] = result
            
            logs.append({
                "timestamp": datetime.utcnow().isoformat(),
                "event": f"STEP_{result.get('status', 'RUNNING').upper()}",
                "step_id": str(sid),
                "message": f"Step {sid} finished with status '{result.get('status')}'. Notes: {result.get('verification_notes') or result.get('error_message') or 'OK'}"
            })

    # Execute all ready steps concurrently
    tasks = [worker(sid) for sid in ready_steps if sid in steps]
    if tasks:
        await asyncio.gather(*tasks)

    return {
        "steps": step_updates,
        "ready_steps": [],
        "execution_logs": logs
    }


async def collect_results_node(state: WorkflowState) -> Dict[str, Any]:
    steps = dict(state.get("steps", {}))
    newly_blocked = DAGScheduler.update_blocked_steps(steps)
    
    logs = []
    if newly_blocked:
        logs.append({
            "timestamp": datetime.utcnow().isoformat(),
            "event": "DEPENDENCY_BLOCK_APPLIED",
            "message": f"Blocked downstream steps {newly_blocked} due to prerequisite step failures."
        })

    is_complete, final_status = DAGScheduler.evaluate_workflow_status(steps)
    
    if is_complete:
        logs.append({
            "timestamp": datetime.utcnow().isoformat(),
            "event": "WORKFLOW_DAG_COMPLETED",
            "message": f"DAG execution reached terminal status: '{final_status}'."
        })

    return {
        "steps": steps,
        "status": final_status,
        "execution_logs": logs
    }


def route_after_approval_check(state: WorkflowState) -> Literal["awaiting_approval", "execute_parallel", "complete"]:
    if state.get("status") == "awaiting_approval":
        return "awaiting_approval"
        
    ready = state.get("ready_steps", [])
    if not ready:
        return "complete"
        
    return "execute_parallel"


def route_after_collection(state: WorkflowState) -> Literal["schedule_next", "complete"]:
    status = state.get("status", "running")
    if status in {"completed", "completed_with_errors", "failed"}:
        return "complete"
    return "schedule_next"


def build_dag_workflow_graph(checkpointer=None):
    """
    Constructs the StateGraph with dynamic DAG resolution, parallel execution,
    persistent checkpoints, and human-in-the-loop approval interrupts.
    """
    builder = StateGraph(WorkflowState)

    builder.add_node("initialize", initialize_node)
    builder.add_node("schedule", schedule_node)
    builder.add_node("check_approval", check_approval_node)
    builder.add_node("execute_parallel", execute_parallel_node)
    builder.add_node("collect_results", collect_results_node)

    builder.set_entry_point("initialize")
    builder.add_edge("initialize", "schedule")
    builder.add_edge("schedule", "check_approval")

    builder.add_conditional_edges(
        "check_approval",
        route_after_approval_check,
        {
            "awaiting_approval": END,
            "execute_parallel": "execute_parallel",
            "complete": END
        }
    )

    builder.add_edge("execute_parallel", "collect_results")

    builder.add_conditional_edges(
        "collect_results",
        route_after_collection,
        {
            "schedule_next": "schedule",
            "complete": END
        }
    )

    return builder.compile(checkpointer=checkpointer)


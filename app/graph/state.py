from typing import TypedDict, List, Dict, Any, Optional, Annotated


def merge_step_dicts(
    current: Dict[int, Dict[str, Any]], 
    update: Dict[int, Dict[str, Any]]
) -> Dict[int, Dict[str, Any]]:
    """
    Concurrency-safe reducer to merge parallel step updates without overwriting.
    """
    merged = dict(current) if current else {}
    if update:
        for k, v in update.items():
            k_int = int(k)
            if k_int in merged:
                merged[k_int] = {**merged[k_int], **v}
            else:
                merged[k_int] = v
    return merged


def append_logs(
    current: List[Dict[str, Any]], 
    new_logs: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """
    Concurrency-safe log append reducer.
    """
    res = list(current) if current else []
    if new_logs:
        res.extend(new_logs)
    return res


class WorkflowState(TypedDict):
    workflow_id: str
    thread_id: str
    original_prompt: str
    steps: Annotated[Dict[int, Dict[str, Any]], merge_step_dicts]
    ready_steps: List[int]
    status: str  # planning, running, awaiting_approval, completed, failed
    pending_approval: Optional[Dict[str, Any]]
    execution_logs: Annotated[List[Dict[str, Any]], append_logs]
    concurrency_limit: int
    retry_config: Dict[str, Any]
    error: Optional[str]

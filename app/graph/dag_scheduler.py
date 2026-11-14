from typing import Dict, List, Any, Set, Tuple


class DAGScheduler:
    """
    Dependency-aware DAG Scheduler for resolving ready execution tasks,
    detecting blocked paths, grouping parallel branches, and checking completion.
    """

    TERMINAL_STATUSES = {"completed", "failed", "blocked", "rejected", "skipped"}

    @classmethod
    def get_ready_steps(cls, steps: Dict[int, Dict[str, Any]], concurrency_limit: int = 4) -> List[int]:
        """
        Returns list of step_ids whose dependencies are all completed and
        whose current status is 'pending' or 'ready'.
        Bounded by concurrency_limit.
        """
        ready: List[int] = []

        for step_id, step in steps.items():
            status = str(step.get("status", "pending")).lower()
            if status not in {"pending", "ready", "approved"}:
                continue

            deps: List[int] = step.get("dependencies", [])
            # Check if all prerequisite steps are successfully completed
            all_deps_completed = True
            for dep_id in deps:
                dep_step = steps.get(dep_id)
                if not dep_step or str(dep_step.get("status", "")).lower() != "completed":
                    all_deps_completed = False
                    break

            if all_deps_completed:
                ready.append(step_id)
                if len(ready) >= concurrency_limit:
                    break

        return ready

    @classmethod
    def update_blocked_steps(cls, steps: Dict[int, Dict[str, Any]]) -> List[int]:
        """
        Identifies and marks steps as 'blocked' if any of their upstream dependencies
        failed, was blocked, or was rejected.
        Returns list of newly blocked step_ids.
        """
        newly_blocked: List[int] = []
        changed = True

        while changed:
            changed = False
            for step_id, step in steps.items():
                status = str(step.get("status", "pending")).lower()
                if status in cls.TERMINAL_STATUSES:
                    continue

                deps: List[int] = step.get("dependencies", [])
                for dep_id in deps:
                    dep_step = steps.get(dep_id)
                    dep_status = str(dep_step.get("status", "")).lower() if dep_step else "failed"
                    if dep_status in {"failed", "blocked", "rejected"}:
                        step["status"] = "blocked"
                        step["error_message"] = f"Blocked because upstream dependency step {dep_id} status is '{dep_status}'."
                        newly_blocked.append(step_id)
                        changed = True
                        break

        return newly_blocked

    @classmethod
    def compute_dag_levels(cls, steps: Dict[int, Dict[str, Any]]) -> List[List[int]]:
        """
        Computes topological execution layers for parallel branching visualization.
        Layer 0 has no dependencies. Layer N depends only on steps in Layer < N.
        """
        if not steps:
            return []

        step_ids = set(steps.keys())
        assigned: Dict[int, int] = {}
        
        # Calculate level for each node
        def get_level(sid: int, visited: Set[int]) -> int:
            if sid in assigned:
                return assigned[sid]
            if sid in visited:
                return 0  # Cycle fallback
            visited.add(sid)

            deps = steps[sid].get("dependencies", [])
            if not deps:
                level = 0
            else:
                valid_deps = [d for d in deps if d in step_ids]
                level = 1 + max([get_level(d, visited) for d in valid_deps], default=-1)

            assigned[sid] = level
            return level

        for sid in step_ids:
            get_level(sid, set())

        max_level = max(assigned.values()) if assigned else 0
        levels: List[List[int]] = [[] for _ in range(max_level + 1)]
        for sid, lvl in sorted(assigned.items(), key=lambda x: x[0]):
            levels[lvl].append(sid)

        return [lvl for lvl in levels if lvl]

    @classmethod
    def evaluate_workflow_status(cls, steps: Dict[int, Dict[str, Any]]) -> Tuple[bool, str]:
        """
        Returns (is_complete: bool, workflow_status: str).
        """
        all_terminal = True
        has_failure = False
        has_awaiting_approval = False

        for step in steps.values():
            status = str(step.get("status", "pending")).lower()
            if status == "awaiting_approval":
                has_awaiting_approval = True
            if status not in cls.TERMINAL_STATUSES:
                all_terminal = False
            if status in {"failed", "blocked", "rejected"}:
                has_failure = True

        if has_awaiting_approval:
            return False, "awaiting_approval"

        if all_terminal:
            if has_failure:
                # If some steps completed and some failed/blocked, it's failed
                completed_count = sum(1 for s in steps.values() if s.get("status") == "completed")
                return True, "completed_with_errors" if completed_count > 0 else "failed"
            return True, "completed"

        return False, "running"

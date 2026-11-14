from typing import List, Dict, Set
from app.schemas.planning import ExecutionPlan, PlanStep, PlanValidationResult, RiskLevel
from app.tools.registry import registry
from app.agents.policy import PolicyChecker


class PlanValidator:
    """
    Validates execution plans for:
    1. Tool existence in registry (rejecting unknown/invented tools).
    2. Valid dependency IDs and preventing circular dependencies.
    3. Proper policy and approval classification.
    4. Completeness and structural consistency.
    """

    @classmethod
    def validate_plan(cls, plan: ExecutionPlan) -> PlanValidationResult:
        errors: List[str] = []
        warnings: List[str] = []
        registered_tool_names = set(registry._tools.keys())
        
        step_ids: Set[int] = set()
        dep_graph: Dict[str, List[int]] = {}
        has_sensitive_steps = False

        if not plan.steps:
            return PlanValidationResult(
                valid=False,
                errors=["Plan contains no executable steps."],
                warnings=warnings,
                validated_steps_count=0,
                has_sensitive_steps=False,
                dependency_graph={}
            )

        # 1. First Pass: check step uniqueness, tool names, and sensitivity
        for step in plan.steps:
            # Check duplicate step IDs
            if step.step_id in step_ids:
                errors.append(f"Duplicate step_id detected: {step.step_id}.")
            step_ids.add(step.step_id)

            # Check tool registration
            if step.tool_name not in registered_tool_names:
                errors.append(
                    f"Step {step.step_id} ('{step.name}') assigns unknown tool '{step.tool_name}'. "
                    f"Registered tools are: {sorted(list(registered_tool_names))}."
                )

            # Check policy requirements
            is_sensitive, policy_reason = PolicyChecker.evaluate_step(step.tool_name, step.input_parameters)
            if is_sensitive:
                has_sensitive_steps = True
                if not step.requires_approval:
                    warnings.append(
                        f"Step {step.step_id} ('{step.tool_name}') is classified sensitive by policy but was not marked requires_approval. Auto-updating."
                    )
                    step.requires_approval = True
                    step.risk_level = RiskLevel.HIGH

            dep_graph[str(step.step_id)] = step.dependencies

        # 2. Second Pass: check dependency existence and self-dependency
        for step in plan.steps:
            for dep_id in step.dependencies:
                if dep_id == step.step_id:
                    errors.append(f"Step {step.step_id} cannot depend on itself.")
                elif dep_id not in step_ids:
                    errors.append(
                        f"Step {step.step_id} declares dependency on step {dep_id}, which does not exist in the plan."
                    )

        # 3. Third Pass: Cycle Detection (DFS)
        if not errors:
            has_cycle, cycle_path = cls._detect_cycle(plan.steps)
            if has_cycle:
                errors.append(f"Circular dependency detected in execution graph: {' -> '.join(map(str, cycle_path))}.")

        is_valid = len(errors) == 0

        return PlanValidationResult(
            valid=is_valid,
            errors=errors,
            warnings=warnings,
            validated_steps_count=len(plan.steps),
            has_sensitive_steps=has_sensitive_steps,
            dependency_graph=dep_graph
        )

    @classmethod
    def _detect_cycle(cls, steps: List[PlanStep]) -> (bool, List[int]):
        adj: Dict[int, List[int]] = {s.step_id: list(s.dependencies) for s in steps}
        visited: Dict[int, int] = {s.step_id: 0 for s in steps}  # 0: unvisited, 1: visiting, 2: visited
        path: List[int] = []

        def dfs(node: int) -> bool:
            visited[node] = 1
            path.append(node)

            for neighbor in adj.get(node, []):
                if neighbor in visited:
                    if visited[neighbor] == 1:
                        # Found cycle
                        cycle_start = path.index(neighbor)
                        cycle = path[cycle_start:] + [neighbor]
                        path.clear()
                        path.extend(cycle)
                        return True
                    if visited[neighbor] == 0:
                        if dfs(neighbor):
                            return True

            visited[node] = 2
            path.pop()
            return False

        for s in steps:
            if visited[s.step_id] == 0:
                if dfs(s.step_id):
                    return True, path

        return False, []


import json
from typing import List, Optional
from app.schemas.planning import (
    ExecutionPlan,
    PlanStep,
    TaskAnalysis,
    ComplexityLevel,
    RiskLevel,
    TaskCategory,
)
from app.schemas.workflow import StructuredPlan, DecomposedStep, PlanAnalysis
from app.agents.analyzer import TaskAnalyzer
from app.agents.policy import PolicyChecker
from app.agents.plan_validator import PlanValidator
from app.agents.llm import get_llm
from app.tools.registry import registry


class AIPlanner:
    """
    Advanced AI Planning Engine capable of dynamic DAG task decomposition,
    strict tool validation, dependency chaining, and approval detection.
    """

    REGISTERED_TOOLS = [
        "web_research", 
        "document_generation", 
        "text_summarization", 
        "email_drafting", 
        "email_sending", 
        "file_processing"
    ]

    @classmethod
    async def generate_plan(cls, prompt: str, title: Optional[str] = None) -> ExecutionPlan:
        analysis = await TaskAnalyzer.analyze(prompt)
        llm = get_llm()

        workflow_title = title or (
            "Workflow: " + (analysis.objective[:45] + "..." if len(analysis.objective) > 45 else analysis.objective)
        )

        # 1. Attempt Groq-powered dynamic planning
        if llm:
            try:
                system_prompt = (
                    "You are the master AI Planner for TaskForge AI, an autonomous workflow engine.\n"
                    f"Available tools: {json.dumps(cls.REGISTERED_TOOLS)}.\n"
                    "You must ONLY assign tools from this exact list. Never invent tool names.\n"
                    "Decompose the user's objective into an ordered DAG sequence of executable steps.\n"
                    "Output strictly valid JSON matching this schema:\n"
                    "{\n"
                    '  "workflow_name": "title string",\n'
                    '  "objective": "objective string",\n'
                    '  "summary": "plan summary",\n'
                    '  "complexity": "LOW" | "MEDIUM" | "HIGH",\n'
                    '  "estimated_duration": "e.g. 45s",\n'
                    '  "execution_strategy": "Sequential DAG with Policy Gate Interruption",\n'
                    '  "approval_summary": "Description of any required human approvals",\n'
                    '  "steps": [\n'
                    "    {\n"
                    '      "step_id": 1,\n'
                    '      "name": "Step title",\n'
                    '      "description": "Step detail",\n'
                    '      "tool_name": "one of the available tools",\n'
                    '      "input_parameters": {"key": "value"},\n'
                    '      "expected_output": "What artifact or data this step generates",\n'
                    '      "dependencies": [prior step_ids],\n'
                    '      "success_criteria": "How to verify success",\n'
                    '      "risk_level": "LOW" | "MEDIUM" | "HIGH",\n'
                    '      "requires_approval": true | false\n'
                    "    }\n"
                    "  ]\n"
                    "}\n"
                    "No markdown backticks or commentary outside JSON."
                )

                response = await llm.ainvoke([
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"User Goal: {prompt}\nAnalysis: {analysis.model_dump_json()}"}
                ])

                content = response.content.strip()
                if content.startswith("```"):
                    content = content.split("```")[1]
                    if content.startswith("json"):
                        content = content[4:]
                    content = content.strip()

                parsed = json.loads(content)

                steps: List[PlanStep] = []
                for s in parsed.get("steps", []):
                    tool_name = s.get("tool_name", "web_research")
                    # Map unknown tool names safely if LLM hallucinated
                    if tool_name not in cls.REGISTERED_TOOLS:
                        tool_name = cls._map_hallucinated_tool(tool_name)

                    input_params = s.get("input_parameters", {})
                    is_sens, _ = PolicyChecker.evaluate_step(tool_name, input_params)

                    step_id = int(s.get("step_id", len(steps) + 1))
                    raw_deps = s.get("dependencies", [])
                    deps = [int(d) for d in raw_deps if isinstance(d, (int, str)) and str(d).isdigit() and int(d) < step_id]

                    steps.append(PlanStep(
                        step_id=step_id,
                        name=s.get("name", f"Execute {tool_name}"),
                        description=s.get("description", ""),
                        tool_name=tool_name,
                        input_parameters=input_params,
                        expected_output=s.get("expected_output", "Structured step output artifact"),
                        dependencies=deps,
                        success_criteria=s.get("success_criteria", "Successful tool return with verified payload"),
                        risk_level=RiskLevel.HIGH if is_sens else RiskLevel(s.get("risk_level", RiskLevel.LOW.value)),
                        requires_approval=is_sens or s.get("requires_approval", False),
                        status="pending"
                    ))

                plan = ExecutionPlan(
                    workflow_name=parsed.get("workflow_name", workflow_title),
                    objective=parsed.get("objective", prompt),
                    summary=parsed.get("summary", f"Autonomous multi-step execution plan ({len(steps)} steps)"),
                    complexity=ComplexityLevel(parsed.get("complexity", analysis.complexity.value)),
                    total_steps=len(steps),
                    estimated_duration=parsed.get("estimated_duration", f"{len(steps) * 15}s"),
                    steps=steps,
                    execution_strategy=parsed.get("execution_strategy", "Sequential DAG with Policy Gate Interruption"),
                    approval_summary=parsed.get("approval_summary", "Requires human review for sensitive steps."),
                    provider_mode="groq"
                )

                # Validate plan
                validation = PlanValidator.validate_plan(plan)
                if validation.valid:
                    return plan
                else:
                    print(f"[AIPlanner] Groq plan validation errors: {validation.errors}. Falling back to deterministic plan.")
            except Exception as e:
                print(f"[AIPlanner] Groq planning error: {e}. Utilizing deterministic planner.")

        # 2. Fallback Planner
        return cls._fallback_plan(prompt, workflow_title, analysis)

    @classmethod
    def _fallback_plan(cls, prompt: str, title: str, analysis: TaskAnalysis) -> ExecutionPlan:
        steps: List[PlanStep] = []
        prompt_lower = prompt.lower()
        step_id = 1

        # Step 1: Web Research if research requested or in multi-step
        if "web_research" in analysis.required_tools:
            steps.append(PlanStep(
                step_id=step_id,
                name="Domain Intelligence & Competitive Research",
                description="Gather factual data, market trends, and industry benchmarks.",
                tool_name="web_research",
                input_parameters={"query": prompt, "num_results": 3},
                expected_output="Verified research points and citations",
                dependencies=[],
                success_criteria="At least 2 validated research citations returned",
                risk_level=RiskLevel.LOW,
                requires_approval=False,
                status="pending"
            ))
            step_id += 1

        # Step 2: File Processing if file/json processing needed
        if "file_processing" in analysis.required_tools:
            deps = [step_id - 1] if step_id > 1 else []
            steps.append(PlanStep(
                step_id=step_id,
                name="Sanitize & Process Data Artifacts",
                description="Safely validate structure and extract document telemetry in sandbox.",
                tool_name="file_processing",
                input_parameters={"operation": "extract_metadata", "content": prompt},
                expected_output="Sanitized data structure and metrics",
                dependencies=deps,
                success_criteria="Sandbox validation with status 'success'",
                risk_level=RiskLevel.LOW,
                requires_approval=False,
                status="pending"
            ))
            step_id += 1

        # Step 3: Text Summarization
        if "text_summarization" in analysis.required_tools or (analysis.category in [TaskCategory.RESEARCH, TaskCategory.MULTI_STEP_AUTOMATION] and len(steps) >= 1):
            deps = [step_id - 1] if step_id > 1 else []
            steps.append(PlanStep(
                step_id=step_id,
                name="Extract Key Findings & Synthesis",
                description="Condense research points into actionable executive takeaways.",
                tool_name="text_summarization",
                input_parameters={
                    "raw_text": f"Context for {prompt}. Analysis emphasizes modularity, verified guardrails, and operational speed.",
                    "max_bullet_points": 4,
                    "tone": "executive"
                },
                expected_output="Executive summary and bulleted takeaways",
                dependencies=deps,
                success_criteria="Executive summary with compression ratio computed",
                risk_level=RiskLevel.LOW,
                requires_approval=False,
                status="pending"
            ))
            step_id += 1

        # Step 4: Document Generation
        if "document_generation" in analysis.required_tools or step_id <= 2 or analysis.category in [TaskCategory.DOCUMENT_GENERATION, TaskCategory.MULTI_STEP_AUTOMATION]:
            deps = [step_id - 1] if step_id > 1 else []
            steps.append(PlanStep(
                step_id=step_id,
                name="Compile Executive Deliverable Document",
                description="Generate formatted report synthesizing research, metrics, and recommendations.",
                tool_name="document_generation",
                input_parameters={
                    "title": f"Report: {title}",
                    "format_type": "markdown",
                    "sections": [
                        {"heading": "Executive Summary", "content": f"Strategic assessment regarding: {prompt}"},
                        {"heading": "Key Recommendations", "content": "1. Deploy structured agent policies\n2. Enforce human approval gates\n3. Verify execution telemetry"}
                    ]
                },
                expected_output="Formatted markdown document artifact",
                dependencies=deps,
                success_criteria="Compiled document artifact with word count > 0",
                risk_level=RiskLevel.LOW,
                requires_approval=False,
                status="pending"
            ))
            step_id += 1

        # Step 5: Email Drafting (Sensitive action requiring approval)
        if "email_drafting" in analysis.required_tools or "email" in prompt_lower or "notify" in prompt_lower or "send" in prompt_lower:
            deps = [step_id - 1] if step_id > 1 else []
            steps.append(PlanStep(
                step_id=step_id,
                name="Prepare Stakeholder Briefing Email",
                description="Draft executive email for stakeholder notification. Staged awaiting human approval.",
                tool_name="email_drafting",
                input_parameters={
                    "recipient_email": "stakeholders@enterprise.internal",
                    "subject": f"[Briefing] {title}",
                    "body": f"Please review the attached autonomous intelligence findings regarding: {prompt}.",
                    "send_immediately": False
                },
                expected_output="Staged email draft payload with preview",
                dependencies=deps,
                success_criteria="Email draft created with recipient and preview body",
                risk_level=RiskLevel.HIGH,
                requires_approval=True,
                status="pending"
            ))

        # Enforce server-side policy checker on every step
        for s in steps:
            is_sens, _ = PolicyChecker.evaluate_step(s.tool_name, s.input_parameters)
            if is_sens:
                s.is_sensitive = True
                s.requires_approval = True
                s.risk_level = RiskLevel.HIGH

        approval_count = sum(1 for s in steps if s.requires_approval)
        approval_summary = (
            f"{approval_count} step(s) require supervisor authorization before execution."
            if approval_count > 0
            else "Fully automated execution permitted by policy."
        )

        return ExecutionPlan(
            workflow_name=title,
            objective=prompt,
            summary=f"Automated {len(steps)}-step execution plan orchestrated across verified tools with human-in-the-loop checkpoints.",
            complexity=analysis.complexity,
            total_steps=len(steps),
            estimated_duration=f"{len(steps) * 15}s",
            steps=steps,
            execution_strategy="Sequential DAG with Policy Gate Interruption",
            approval_summary=approval_summary,
            clarifications_needed=analysis.clarifications_needed,
            assumptions=analysis.assumptions,
            provider_mode="deterministic_fallback"
        )

    @classmethod
    def _map_hallucinated_tool(cls, name: str) -> str:
        name_lower = name.lower()
        if any(w in name_lower for w in ["search", "google", "browse", "lookup", "query"]):
            return "web_research"
        if any(w in name_lower for w in ["doc", "pdf", "markdown", "write", "report"]):
            return "document_generation"
        if any(w in name_lower for w in ["sum", "summarize", "condense", "tldr"]):
            return "text_summarization"
        if any(w in name_lower for w in ["mail", "email", "send", "message", "notify"]):
            return "email_drafting"
        if any(w in name_lower for w in ["file", "json", "parse", "data"]):
            return "file_processing"
        return "web_research"

    # Backward compatibility method for existing service calls
    @classmethod
    async def create_plan(cls, prompt: str, title: Optional[str] = None) -> StructuredPlan:
        exec_plan = await cls.generate_plan(prompt, title)
        analysis = await TaskAnalyzer.analyze(prompt)

        decomposed = []
        for s in exec_plan.steps:
            decomposed.append(DecomposedStep(
                step_number=s.step_id,
                title=s.name,
                description=s.description,
                tool_name=s.tool_name,
                tool_input=s.input_parameters,
                dependencies=s.dependencies,
                is_sensitive=s.requires_approval
            ))

        plan_analysis = PlanAnalysis(
            intent=analysis.intent,
            goal=analysis.objective,
            assumptions=analysis.constraints,
            required_capabilities=analysis.required_capabilities,
            risk_level=analysis.risk_level.value.lower()
        )

        return StructuredPlan(
            title=exec_plan.workflow_name,
            summary=exec_plan.summary,
            analysis=plan_analysis,
            steps=decomposed
        )

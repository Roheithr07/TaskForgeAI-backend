import json
from typing import List
from app.schemas.planning import TaskAnalysis, TaskCategory, ComplexityLevel, RiskLevel
from app.schemas.workflow import PlanAnalysis
from app.agents.llm import get_llm
from app.core.config import settings


class TaskAnalyzer:
    """
    Intelligent Task Analyzer supporting Groq API semantic classification
    with robust structured fallback.
    """

    @classmethod
    async def analyze(cls, prompt: str) -> TaskAnalysis:
        prompt_trimmed = prompt.strip()
        llm = get_llm()

        # 1. Attempt Groq-powered semantic analysis
        if llm:
            try:
                system_prompt = (
                    "You are the TaskForge AI Intent & Task Classification Analyzer.\n"
                    "Analyze the user's objective and output strictly valid JSON matching this schema:\n"
                    "{\n"
                    '  "objective": "clean summary of goal",\n'
                    '  "intent": "actionable core intent",\n'
                    '  "category": "RESEARCH" | "DOCUMENT_GENERATION" | "SUMMARIZATION" | "DATA_PROCESSING" | "EMAIL" | "BUSINESS_AUTOMATION" | "DEVELOPER_WORKFLOW" | "MULTI_STEP_AUTOMATION" | "GENERAL",\n'
                    '  "complexity": "LOW" | "MEDIUM" | "HIGH",\n'
                    '  "required_capabilities": ["capability1", "capability2"],\n'
                    '  "required_tools": ["web_research" | "document_generation" | "text_summarization" | "email_drafting" | "file_processing"],\n'
                    '  "constraints": ["constraint1"],\n'
                    '  "clarifications_needed": ["clarification1 if any"],\n'
                    '  "assumptions": ["assumption1"],\n'
                    '  "risk_level": "LOW" | "MEDIUM" | "HIGH",\n'
                    '  "requires_approval": true | false,\n'
                    '  "expected_result": "expected artifact or output description"\n'
                    "}\n"
                    "Do NOT include markdown formatting or extra text outside the JSON object."
                )

                response = await llm.ainvoke([
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"Analyze this task prompt:\n{prompt_trimmed}"}
                ])

                content = response.content.strip()
                if content.startswith("```"):
                    content = content.split("```")[1]
                    if content.startswith("json"):
                        content = content[4:]
                    content = content.strip()

                data = json.loads(content)

                # Validate tool names in required_tools to only registered tools
                valid_tools = {"web_research", "document_generation", "text_summarization", "email_drafting", "file_processing"}
                extracted_tools = [t for t in data.get("required_tools", []) if t in valid_tools]
                if not extracted_tools:
                    extracted_tools = cls._infer_tools_from_text(prompt_trimmed)

                return TaskAnalysis(
                    objective=data.get("objective", prompt_trimmed),
                    intent=data.get("intent", f"Execute {data.get('category', 'GENERAL')} task"),
                    category=TaskCategory(data.get("category", "GENERAL")),
                    complexity=ComplexityLevel(data.get("complexity", "MEDIUM")),
                    required_capabilities=data.get("required_capabilities", [t.replace("_", " ") for t in extracted_tools]),
                    required_tools=extracted_tools,
                    constraints=data.get("constraints", [
                        "Execution restricted to registered sandboxed tools",
                        "Policy enforcement gates sensitive external communications"
                    ]),
                    clarifications_needed=data.get("clarifications_needed", []),
                    assumptions=data.get("assumptions", [
                        "Standard execution timeout applies",
                        "Human approval required for irreversible actions"
                    ]),
                    risk_level=RiskLevel(data.get("risk_level", "LOW")),
                    requires_approval=data.get("requires_approval", False) or "email" in extracted_tools or "email_drafting" in extracted_tools,
                    expected_result=data.get("expected_result", "Validated execution output"),
                    provider_mode="groq"
                )

                return TaskAnalysis(
                    objective=data.get("objective", prompt_trimmed),
                    intent=data.get("intent", "Execute automated digital workflow"),
                    category=TaskCategory(data.get("category", TaskCategory.GENERAL.value)),
                    complexity=ComplexityLevel(data.get("complexity", ComplexityLevel.MEDIUM.value)),
                    required_capabilities=data.get("required_capabilities", ["multi_step_automation"]),
                    required_tools=extracted_tools,
                    constraints=data.get("constraints", ["Strict policy guardrails", "Output verification"]),
                    risk_level=RiskLevel(data.get("risk_level", RiskLevel.LOW.value)),
                    requires_approval=bool(data.get("requires_approval", "email_drafting" in extracted_tools)),
                    expected_result=data.get("expected_result", "Completed workflow artifact"),
                    provider_mode="groq"
                )
            except Exception as e:
                print(f"[TaskAnalyzer] Groq analysis exception: {e}. Utilizing deterministic fallback engine.")

        # 2. Deterministic Fallback Engine
        return cls._fallback_analysis(prompt_trimmed)

    @classmethod
    def _fallback_analysis(cls, prompt: str) -> TaskAnalysis:
        prompt_lower = prompt.lower()

        # Category Determination
        category = TaskCategory.GENERAL
        if any(w in prompt_lower for w in ["research", "investigate", "compare", "benchmark", "market", "trends"]):
            category = TaskCategory.RESEARCH
        elif any(w in prompt_lower for w in ["document", "report", "brief", "draft doc", "write a guide"]):
            category = TaskCategory.DOCUMENT_GENERATION
        elif any(w in prompt_lower for w in ["summarize", "tldr", "condense", "key points"]):
            category = TaskCategory.SUMMARIZATION
        elif any(w in prompt_lower for w in ["json", "sanitize", "parse", "extract metadata", "file"]):
            category = TaskCategory.DATA_PROCESSING
        elif any(w in prompt_lower for w in ["email", "notify", "stakeholder email", "send draft"]):
            category = TaskCategory.EMAIL
        elif any(w in prompt_lower for w in ["deploy", "git", "ci/cd", "code"]):
            category = TaskCategory.DEVELOPER_WORKFLOW
        elif any(w in prompt_lower for w in ["business", "invoice", "sales", "crm"]):
            category = TaskCategory.BUSINESS_AUTOMATION

        if (
            sum(
                1
                for c in [
                    "research" in prompt_lower,
                    "document" in prompt_lower or "report" in prompt_lower,
                    "email" in prompt_lower,
                    "summarize" in prompt_lower,
                ]
                if c
            )
            >= 2
        ):
            category = TaskCategory.MULTI_STEP_AUTOMATION

        # Required Tools
        tools = cls._infer_tools_from_text(prompt_lower)

        # Complexity Estimation
        complexity = ComplexityLevel.LOW
        if len(tools) >= 3 or len(prompt.split()) > 20:
            complexity = ComplexityLevel.HIGH
        elif len(tools) >= 2 or len(prompt.split()) > 8 or any(w in prompt_lower for w in ["compare", "benchmark", "frameworks", "analyze", "synthesize"]):
            complexity = ComplexityLevel.MEDIUM

        # Risk Classification
        risk = RiskLevel.LOW
        requires_approval = False
        if any(w in prompt_lower for w in ["send", "email", "delete", "publish", "payment", "dispatch", "external"]):
            risk = RiskLevel.HIGH
            requires_approval = True
        elif complexity == ComplexityLevel.HIGH:
            risk = RiskLevel.MEDIUM

        # Expected Result
        expected_result = "Synthesized digital intelligence report and execution audit"
        if "email" in tools and "document_generation" in tools:
            expected_result = "Comprehensive executive documentation and staged stakeholder email briefing"
        elif "web_research" in tools:
            expected_result = "Verified domain findings and research synthesis with citations"

        # Clarifications and assumptions detection
        clarifications_needed = []
        if len(prompt.split()) < 5:
            clarifications_needed.append("Prompt is brief; specify exact target domain, format, or recipients for precision.")
        if "email" in tools and "@" not in prompt:
            clarifications_needed.append("Target recipient email address is not specified; staged default operator address will be used.")

        assumptions = [
            "Defaulting to sandboxed local execution environment",
            "Sensitive communications staged as drafts prior to supervisor authorization",
            "Tool results verified against expected completion criteria"
        ]

        return TaskAnalysis(
            objective=prompt.strip(),
            intent=f"Orchestrate {category.value.lower().replace('_', ' ')} workflow across {len(tools)} tools",
            category=category,
            complexity=complexity,
            required_capabilities=[t.replace("_", " ") for t in tools],
            required_tools=tools,
            constraints=[
                "Execution must adhere to server-side permission policies",
                "Sensitive actions mandate supervisor authorization",
                "Tool outputs must pass result verification checks"
            ],
            clarifications_needed=clarifications_needed,
            assumptions=assumptions,
            risk_level=risk,
            requires_approval=requires_approval,
            expected_result=expected_result,
            provider_mode="deterministic_fallback"
        )

    @classmethod
    def _infer_tools_from_text(cls, text: str) -> List[str]:
        tools = []
        if any(w in text for w in ["research", "search", "find", "trends", "market", "competitor", "intelligence"]):
            tools.append("web_research")
        if any(w in text for w in ["summarize", "digest", "key points", "condense", "synthesize", "extract"]):
            tools.append("text_summarization")
        if any(w in text for w in ["document", "report", "brief", "draft", "write", "markdown"]):
            tools.append("document_generation")
        if any(w in text for w in ["email", "notify", "send", "stakeholder", "message"]):
            tools.append("email_drafting")
        if any(w in text for w in ["file", "json", "parse", "process", "sanitize", "metadata"]):
            tools.append("file_processing")

        if not tools:
            tools = ["web_research", "document_generation"]
        return tools

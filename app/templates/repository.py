from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import datetime

from app.templates.schemas import (
    WorkflowTemplateResponse,
    TemplateInputParam,
    TemplateStepDefinition,
)
from app.schemas.planning import (
    ExecutionPlan,
    PlanStep,
    ComplexityLevel,
    RiskLevel,
)
from app.database.models import Workflow, WorkflowStep, ExecutionLog


BUILTIN_TEMPLATES: List[Dict[str, Any]] = [
    {
        "id": "research-assistant",
        "name": "Research Assistant",
        "category": "RESEARCH",
        "description": "Autonomous multi-source web research, source extraction, synthesis, and ReportLab PDF document compilation.",
        "version": "1.0.0",
        "icon": "Search",
        "estimated_duration": "40s",
        "complexity": "MEDIUM",
        "is_sensitive": False,
        "inputs": [
            {
                "name": "topic",
                "label": "Research Topic",
                "type": "string",
                "required": True,
                "default": "Autonomous AI Agent Architecture Trends",
                "description": "Subject or industry focus to research."
            },
            {
                "name": "depth",
                "label": "Research Scope",
                "type": "select",
                "required": False,
                "default": "In-Depth Synthesis",
                "options": ["Executive Overview", "In-Depth Synthesis", "Technical Deep Dive"],
                "description": "Breadth and analytical detail of findings."
            },
            {
                "name": "report_title",
                "label": "Report Document Title",
                "type": "string",
                "required": False,
                "default": "Executive Research Synthesis Report",
                "description": "Title displayed on generated PDF document."
            }
        ],
        "steps": [
            {
                "step_number": 1,
                "title": "Investigate Domain Sources",
                "description": "Query online search engine, extract relevant web pages, deduplicate citations, and sanitize prompt injections.",
                "tool_name": "web_research",
                "dependencies": [],
                "is_sensitive": False,
                "is_optional": False,
                "default_input": {"query": "{topic}", "max_results": 5}
            },
            {
                "step_number": 2,
                "title": "Synthesize Key Findings",
                "description": "Condense raw search findings into actionable insights and strategic recommendations.",
                "tool_name": "text_summarization",
                "dependencies": [1],
                "is_sensitive": False,
                "is_optional": False,
                "default_input": {"text": "Findings from web research on {topic}", "summary_type": "executive"}
            },
            {
                "step_number": 3,
                "title": "Compile Executive Report",
                "description": "Compile research synthesis and citations into a publication-ready PDF document.",
                "tool_name": "document_generation",
                "dependencies": [2],
                "is_sensitive": False,
                "is_optional": False,
                "default_input": {"title": "{report_title}", "format": "pdf"}
            }
        ]
    },
    {
        "id": "document-automation",
        "name": "Document Automation",
        "category": "DOCUMENT_GENERATION",
        "description": "Extract raw content from uploaded documents, sanitize metadata, summarize key takeaways, and compile structured executive documentation.",
        "version": "1.0.0",
        "icon": "FileText",
        "estimated_duration": "35s",
        "complexity": "LOW",
        "is_sensitive": False,
        "inputs": [
            {
                "name": "document_subject",
                "label": "Document Subject",
                "type": "string",
                "required": True,
                "default": "Q4 Performance Analysis",
                "description": "Subject or title of the document being processed."
            },
            {
                "name": "document_format",
                "label": "Target Format",
                "type": "select",
                "required": False,
                "default": "pdf",
                "options": ["pdf", "markdown", "text"],
                "description": "Compiled artifact output format."
            }
        ],
        "steps": [
            {
                "step_number": 1,
                "title": "Process Source Document",
                "description": "Parse input payload or file content safely inside the sandbox.",
                "tool_name": "file_processing",
                "dependencies": [],
                "is_sensitive": False,
                "is_optional": False,
                "default_input": {"content": "Document intake for {document_subject}", "operation": "extract"}
            },
            {
                "step_number": 2,
                "title": "Extract Key Takeaways",
                "description": "Run analytical text summarization on parsed document body.",
                "tool_name": "text_summarization",
                "dependencies": [1],
                "is_sensitive": False,
                "is_optional": False,
                "default_input": {"text": "Parsed content of {document_subject}", "summary_type": "key_takeaways"}
            },
            {
                "step_number": 3,
                "title": "Generate Publication Document",
                "description": "Compile clean formatted artifact with tables and headers.",
                "tool_name": "document_generation",
                "dependencies": [2],
                "is_sensitive": False,
                "is_optional": False,
                "default_input": {"title": "{document_subject} - Official Summary", "format": "{document_format}"}
            }
        ]
    },
    {
        "id": "email-assistant",
        "name": "Email Assistant",
        "category": "EMAIL",
        "description": "Gathers background context, drafts personalized correspondence with variable substitution, and stages for supervisor approval before sending.",
        "version": "1.0.0",
        "icon": "Mail",
        "estimated_duration": "30s",
        "complexity": "MEDIUM",
        "is_sensitive": True,
        "inputs": [
            {
                "name": "recipient",
                "label": "Recipient Email",
                "type": "string",
                "required": True,
                "default": "stakeholder@taskforge.ai",
                "description": "Target email destination."
            },
            {
                "name": "subject_topic",
                "label": "Subject / Topic",
                "type": "string",
                "required": True,
                "default": "Weekly Autonomous AI Progress Briefing",
                "description": "Main communication subject."
            },
            {
                "name": "briefing_notes",
                "label": "Context Notes",
                "type": "text",
                "required": False,
                "default": "All 7 milestones successfully reached on schedule. Concurrency limits and security policies enforced.",
                "description": "Specific bullet points or talking points to include."
            }
        ],
        "steps": [
            {
                "step_number": 1,
                "title": "Research Contextual Background",
                "description": "Gather relevant domain background on the topic to enrich communication tone.",
                "tool_name": "web_research",
                "dependencies": [],
                "is_sensitive": False,
                "is_optional": True,
                "default_input": {"query": "{subject_topic}", "max_results": 3}
            },
            {
                "step_number": 2,
                "title": "Draft Stakeholder Email",
                "description": "Compose structured email draft with formal greeting, body paragraphs, and actionable closing.",
                "tool_name": "email_drafting",
                "dependencies": [1],
                "is_sensitive": False,
                "is_optional": False,
                "default_input": {
                    "recipient": "{recipient}",
                    "subject": "{subject_topic}",
                    "template_name": "formal",
                    "variables": {"notes": "{briefing_notes}"}
                }
            },
            {
                "step_number": 3,
                "title": "Dispatch Outbound Email (Privileged)",
                "description": "Held in checkpointed state until authorized by a Human Reviewer or Supervisor.",
                "tool_name": "email_sending",
                "dependencies": [2],
                "is_sensitive": True,
                "is_optional": False,
                "default_input": {
                    "recipient": "{recipient}",
                    "subject": "{subject_topic}",
                    "body": "Staged draft from Step 2"
                }
            }
        ]
    },
    {
        "id": "data-analysis",
        "name": "Data Analysis",
        "category": "DATA_PROCESSING",
        "description": "Process structured JSON or tabular datasets, compute operational metrics, identify statistical anomalies, and generate an analytical briefing.",
        "version": "1.0.0",
        "icon": "BarChart3",
        "estimated_duration": "45s",
        "complexity": "MEDIUM",
        "is_sensitive": False,
        "inputs": [
            {
                "name": "dataset_label",
                "label": "Dataset Identifier",
                "type": "string",
                "required": True,
                "default": "System Telemetry & Performance Logs",
                "description": "Name or classification of data being evaluated."
            },
            {
                "name": "analysis_objective",
                "label": "Analytical Focus",
                "type": "string",
                "required": False,
                "default": "Evaluate throughput, error rates, and latency distributions",
                "description": "Key metrics or hypotheses to investigate."
            }
        ],
        "steps": [
            {
                "step_number": 1,
                "title": "Sanitize & Ingest Data",
                "description": "Validate schema, strip unsafe tokens, and parse records.",
                "tool_name": "file_processing",
                "dependencies": [],
                "is_sensitive": False,
                "is_optional": False,
                "default_input": {"content": "Data sample for {dataset_label}", "operation": "extract"}
            },
            {
                "step_number": 2,
                "title": "Synthesize Metrics & Trends",
                "description": "Extract critical quantitative takeaways and variance patterns.",
                "tool_name": "text_summarization",
                "dependencies": [1],
                "is_sensitive": False,
                "is_optional": False,
                "default_input": {"text": "Analysis focus: {analysis_objective}", "summary_type": "statistical"}
            },
            {
                "step_number": 3,
                "title": "Generate Analytical Report",
                "description": "Compile structured PDF report with tables and recommendations.",
                "tool_name": "document_generation",
                "dependencies": [2],
                "is_sensitive": False,
                "is_optional": False,
                "default_input": {"title": "{dataset_label} - Analysis Report", "format": "pdf"}
            }
        ]
    },
    {
        "id": "business-research",
        "name": "Business Research",
        "category": "BUSINESS_AUTOMATION",
        "description": "Perform deep competitor research, compare product architectures, generate comparative tables in PDF, and stage an executive briefing email.",
        "version": "1.0.0",
        "icon": "Briefcase",
        "estimated_duration": "55s",
        "complexity": "HIGH",
        "is_sensitive": True,
        "inputs": [
            {
                "name": "target_entities",
                "label": "Target Companies / Products",
                "type": "string",
                "required": True,
                "default": "OpenAI, Anthropic, Google DeepMind, Mistral, Meta AI",
                "description": "Comma-separated list of companies or technologies to benchmark."
            },
            {
                "name": "industry_sector",
                "label": "Industry Sector",
                "type": "string",
                "required": False,
                "default": "Autonomous AI Agent Frameworks",
                "description": "Market sector or domain."
            },
            {
                "name": "executive_recipient",
                "label": "Executive Briefing Recipient",
                "type": "string",
                "required": False,
                "default": "leadership@taskforge.ai",
                "description": "Email address for staged briefing."
            }
        ],
        "steps": [
            {
                "step_number": 1,
                "title": "Investigate Market Competitors",
                "description": "Execute web research across targets: {target_entities}.",
                "tool_name": "web_research",
                "dependencies": [],
                "is_sensitive": False,
                "is_optional": False,
                "default_input": {"query": "{target_entities} {industry_sector} product comparison", "max_results": 5}
            },
            {
                "step_number": 2,
                "title": "Compare Findings & Architectural Matrix",
                "description": "Extract comparative metrics, capabilities, and positioning matrix.",
                "tool_name": "text_summarization",
                "dependencies": [1],
                "is_sensitive": False,
                "is_optional": False,
                "default_input": {"text": "Market analysis for {target_entities}", "summary_type": "comparison"}
            },
            {
                "step_number": 3,
                "title": "Compile Executive Benchmark Report",
                "description": "Generate comprehensive PDF report with tables and verified citations.",
                "tool_name": "document_generation",
                "dependencies": [2],
                "is_sensitive": False,
                "is_optional": False,
                "default_input": {"title": "{industry_sector} - Competitive Intelligence Report", "format": "pdf"}
            },
            {
                "step_number": 4,
                "title": "Draft Executive Briefing Email",
                "description": "Prepare summary email communication for executive leadership.",
                "tool_name": "email_drafting",
                "dependencies": [3],
                "is_sensitive": False,
                "is_optional": False,
                "default_input": {
                    "recipient": "{executive_recipient}",
                    "subject": "Executive Briefing: {industry_sector} Intelligence",
                    "variables": {"target": "{target_entities}"}
                }
            }
        ]
    }
]


class TemplateRepository:
    """Manages built-in and customized workflow templates with live database execution metrics."""

    @classmethod
    def list_templates(cls, db: Optional[Session] = None) -> List[WorkflowTemplateResponse]:
        counts: Dict[str, int] = {}
        if db:
            rows = db.query(Workflow.template_id, func.count(Workflow.id)).filter(
                Workflow.template_id.isnot(None)
            ).group_by(Workflow.template_id).all()
            counts = {r[0]: r[1] for r in rows if r[0]}

        results: List[WorkflowTemplateResponse] = []
        for t in BUILTIN_TEMPLATES:
            t_copy = dict(t)
            t_copy["execution_count"] = counts.get(t["id"], 0)
            results.append(WorkflowTemplateResponse(**t_copy))
        return results

    @classmethod
    def get_template(cls, template_id: str, db: Optional[Session] = None) -> Optional[WorkflowTemplateResponse]:
        found = next((t for t in BUILTIN_TEMPLATES if t["id"] == template_id), None)
        if not found:
            return None
        t_copy = dict(found)
        if db:
            count = db.query(func.count(Workflow.id)).filter(Workflow.template_id == template_id).scalar() or 0
            t_copy["execution_count"] = count
        return WorkflowTemplateResponse(**t_copy)

    @classmethod
    def _interpolate(cls, val: Any, inputs: Dict[str, Any]) -> Any:
        if isinstance(val, str):
            res = val
            for k, v in inputs.items():
                res = res.replace(f"{{{k}}}", str(v))
            return res
        elif isinstance(val, dict):
            return {k: cls._interpolate(v, inputs) for k, v in val.items()}
        elif isinstance(val, list):
            return [cls._interpolate(v, inputs) for v in val]
        return val

    @classmethod
    def build_preview_plan(cls, template_id: str, user_inputs: Dict[str, Any]) -> ExecutionPlan:
        tmpl = cls.get_template(template_id)
        if not tmpl:
            raise ValueError(f"Template '{template_id}' not found.")

        # Fill in defaults if not supplied
        effective_inputs: Dict[str, Any] = {}
        for inp in tmpl.inputs:
            val = user_inputs.get(inp.name)
            if val is None or val == "":
                val = inp.default or ""
            effective_inputs[inp.name] = val

        # Interpolate into steps
        plan_steps: List[PlanStep] = []
        for s in tmpl.steps:
            interpolated_input = cls._interpolate(s.default_input, effective_inputs)
            plan_steps.append(PlanStep(
                step_id=s.step_number,
                name=s.title,
                description=cls._interpolate(s.description, effective_inputs),
                tool_name=s.tool_name,
                input_parameters=interpolated_input,
                expected_output=f"Output artifact or verified result of {s.tool_name}",
                dependencies=s.dependencies,
                success_criteria=f"Tool '{s.tool_name}' completes execution with verified outcome",
                risk_level=RiskLevel.HIGH if s.is_sensitive else RiskLevel.LOW,
                is_sensitive=s.is_sensitive,
                requires_approval=s.is_sensitive,
                is_optional=s.is_optional,
                enabled=True,
                status="pending"
            ))

        return ExecutionPlan(
            workflow_name=f"{tmpl.name}: {effective_inputs.get('topic') or effective_inputs.get('document_subject') or effective_inputs.get('subject_topic') or effective_inputs.get('dataset_label') or effective_inputs.get('target_entities') or 'Automated Execution'}",
            objective=f"Execute {tmpl.name} with custom parameters across {len(plan_steps)} DAG steps.",
            summary=tmpl.description,
            complexity=ComplexityLevel(tmpl.complexity),
            total_steps=len(plan_steps),
            estimated_duration=tmpl.estimated_duration,
            steps=plan_steps,
            execution_strategy="Directed Acyclic Graph (Topological Dependency Scheduling)",
            approval_summary="Supervisor authorization required for outbound email communication" if tmpl.is_sensitive else "Autonomous sandboxed execution",
            clarifications_needed=[],
            assumptions=["Template inputs validated", "Sandboxed tool execution mode"],
            provider_mode="template_engine"
        )

    @classmethod
    def instantiate_workflow(
        cls, 
        db: Session, 
        template_id: str, 
        user_inputs: Dict[str, Any], 
        custom_title: Optional[str] = None
    ) -> Workflow:
        tmpl = cls.get_template(template_id, db=db)
        if not tmpl:
            raise ValueError(f"Template '{template_id}' not found.")

        # Build preview plan
        plan = cls.build_preview_plan(template_id, user_inputs)
        title = custom_title or plan.workflow_name

        # Create persistent workflow
        thread_id = f"thread_{template_id}_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"
        wf = Workflow(
            title=title,
            original_prompt=f"Instantiated from template '{tmpl.name}' (v{tmpl.version}) with inputs: {user_inputs}",
            status="planned",
            plan_summary=plan.summary,
            thread_id=thread_id,
            template_id=template_id
        )
        db.add(wf)
        db.flush()

        # Add steps
        for s in plan.steps:
            step = WorkflowStep(
                workflow_id=wf.id,
                step_number=s.step_id,
                title=s.name,
                description=s.description,
                tool_name=s.tool_name,
                tool_input=s.input_parameters,
                dependencies=s.dependencies,
                is_sensitive=s.is_sensitive,
                status="pending"
            )
            db.add(step)

        # Log creation
        log = ExecutionLog(
            workflow_id=wf.id,
            actor="template_engine",
            level="INFO",
            event="TEMPLATE_WORKFLOW_INITIALIZED",
            message=f"Initialized workflow from template '{tmpl.name}' with {len(plan.steps)} steps.",
            details={"template_id": template_id, "inputs": user_inputs},
            outcome="SUCCESS"
        )
        db.add(log)
        db.commit()
        db.refresh(wf)
        return wf


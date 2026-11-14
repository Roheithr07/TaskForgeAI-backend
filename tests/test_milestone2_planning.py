import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.agents.analyzer import TaskAnalyzer
from app.agents.planner import AIPlanner
from app.agents.plan_validator import PlanValidator
from app.schemas.planning import (
    TaskCategory,
    ComplexityLevel,
    RiskLevel,
    ExecutionPlan,
    PlanStep,
)

client = TestClient(app)


@pytest.mark.asyncio
async def test_task_analyzer_research():
    analysis = await TaskAnalyzer.analyze("Research leading AI autonomous agent frameworks and compare benchmarks.")
    assert analysis.category in [TaskCategory.RESEARCH, TaskCategory.MULTI_STEP_AUTOMATION]
    assert "web_research" in analysis.required_tools
    assert analysis.complexity in [ComplexityLevel.MEDIUM, ComplexityLevel.HIGH]
    assert analysis.provider_mode in ["groq", "deterministic_fallback"]


@pytest.mark.asyncio
async def test_task_analyzer_email_sensitive():
    analysis = await TaskAnalyzer.analyze("Send executive briefing email to company leadership.")
    assert "email_drafting" in analysis.required_tools
    assert analysis.risk_level == RiskLevel.HIGH
    assert analysis.requires_approval is True


@pytest.mark.asyncio
async def test_hackathon_demo_planning():
    prompt = "Research five AI companies, compare their products, generate an executive report, and prepare an email briefing."
    plan = await AIPlanner.generate_plan(prompt, "AI Competitive Analysis")
    assert plan.total_steps >= 4
    assert plan.complexity == ComplexityLevel.HIGH

    tool_names = [s.tool_name for s in plan.steps]
    assert "web_research" in tool_names
    assert "document_generation" in tool_names
    assert "email_drafting" in tool_names

    # Check validation passes
    val = PlanValidator.validate_plan(plan)
    assert val.valid is True
    assert val.has_sensitive_steps is True


def test_plan_validator_rejects_unknown_tool():
    invalid_plan = ExecutionPlan(
        workflow_name="Invalid Tool Test",
        objective="Run hallucinated tool",
        summary="Test",
        complexity=ComplexityLevel.LOW,
        total_steps=1,
        estimated_duration="10s",
        steps=[
            PlanStep(
                step_id=1,
                name="Hallucinated tool execution",
                description="This tool does not exist in registry",
                tool_name="unregistered_dangerous_action",
                input_parameters={},
                expected_output="Nothing",
                dependencies=[],
                risk_level=RiskLevel.LOW,
                requires_approval=False
            )
        ],
        execution_strategy="Sequential",
        approval_summary="None",
        provider_mode="test"
    )
    val = PlanValidator.validate_plan(invalid_plan)
    assert val.valid is False
    assert any("unknown tool 'unregistered_dangerous_action'" in e for e in val.errors)


def test_plan_validator_detects_circular_dependencies():
    cycle_plan = ExecutionPlan(
        workflow_name="Cycle Test",
        objective="Test cycle detection",
        summary="Test",
        complexity=ComplexityLevel.HIGH,
        total_steps=2,
        estimated_duration="20s",
        steps=[
            PlanStep(
                step_id=1,
                name="Step 1",
                tool_name="web_research",
                input_parameters={"query": "test"},
                dependencies=[2],  # Step 1 depends on Step 2
                expected_output="Output",
                risk_level=RiskLevel.LOW,
                requires_approval=False
            ),
            PlanStep(
                step_id=2,
                name="Step 2",
                tool_name="text_summarization",
                input_parameters={"raw_text": "test"},
                dependencies=[1],  # Step 2 depends on Step 1 -> Circular!
                expected_output="Output",
                risk_level=RiskLevel.LOW,
                requires_approval=False
            )
        ],
        execution_strategy="Sequential",
        approval_summary="None",
        provider_mode="test"
    )
    val = PlanValidator.validate_plan(cycle_plan)
    assert val.valid is False
    assert any("Circular dependency" in e for e in val.errors)


def test_plan_validator_detects_missing_dependency():
    missing_dep_plan = ExecutionPlan(
        workflow_name="Missing Dep Test",
        objective="Test missing dependency",
        summary="Test",
        complexity=ComplexityLevel.LOW,
        total_steps=1,
        estimated_duration="10s",
        steps=[
            PlanStep(
                step_id=1,
                name="Step 1",
                tool_name="web_research",
                input_parameters={"query": "test"},
                dependencies=[99],  # 99 does not exist
                expected_output="Output",
                risk_level=RiskLevel.LOW,
                requires_approval=False
            )
        ],
        execution_strategy="Sequential",
        approval_summary="None",
        provider_mode="test"
    )
    val = PlanValidator.validate_plan(missing_dep_plan)
    assert val.valid is False
    assert any("does not exist in the plan" in e for e in val.errors)


def test_planning_api_endpoints():
    # 1. Analyze endpoint
    analyze_res = client.post("/api/v1/planning/analyze", json={
        "prompt": "Research autonomous AI platforms and draft executive brief"
    })
    assert analyze_res.status_code == 200
    analysis_data = analyze_res.json()
    assert "objective" in analysis_data
    assert "category" in analysis_data
    assert "required_tools" in analysis_data

    # 2. Generate plan endpoint
    gen_res = client.post("/api/v1/planning/generate", json={
        "prompt": "Research autonomous AI platforms and draft executive brief",
        "title": "API Test Plan"
    })
    assert gen_res.status_code == 200
    plan_data = gen_res.json()
    assert plan_data["workflow_name"] == "API Test Plan"
    assert len(plan_data["steps"]) >= 2

    # 3. Validate endpoint
    val_res = client.post("/api/v1/planning/validate", json=plan_data)
    assert val_res.status_code == 200
    val_data = val_res.json()
    assert val_data["valid"] is True
    assert val_data["validated_steps_count"] == len(plan_data["steps"])


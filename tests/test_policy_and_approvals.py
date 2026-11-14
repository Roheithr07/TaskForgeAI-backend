import pytest
from app.agents.policy import PolicyChecker


def test_policy_checker_sensitive_tool():
    requires_approval, reason = PolicyChecker.evaluate_step("email_drafting", {"send_immediately": True})
    assert requires_approval is True
    assert "Approval" in reason or "approval" in reason


def test_policy_checker_safe_tool():
    requires_approval, reason = PolicyChecker.evaluate_step("web_research", {"query": "Machine learning"})
    assert requires_approval is False


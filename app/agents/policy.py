from typing import Dict, Any, Tuple
from app.tools.registry import registry


class PolicyChecker:
    """
    Enforces server-side security policies, risk classifications,
    and human-in-the-loop triggers based on trusted backend metadata.
    """

    SENSITIVE_TOOLS = {"email_drafting", "email_sending"}
    
    # Operations classified by inherent risk tier
    CRITICAL_KEYWORDS = {"payment", "payout", "wire", "delete", "destroy", "execute_shell", "access_system_files", "modify_iam"}
    HIGH_KEYWORDS = {"send", "publish", "broadcast", "notify_external", "export_credentials"}

    # Minimum risk tier triggering mandatory supervisor approval: LOW | MEDIUM | HIGH | CRITICAL
    APPROVAL_RISK_THRESHOLD = "HIGH"

    @classmethod
    def classify_risk(cls, tool_name: str, tool_input: Dict[str, Any]) -> str:
        """
        Classifies action into standardized risk tiers: LOW, MEDIUM, HIGH, CRITICAL.
        Never relies on LLM self-classification.
        """
        payload_str = str(tool_input).lower()

        # 1. CRITICAL
        for kw in cls.CRITICAL_KEYWORDS:
            if kw in payload_str or kw in tool_name.lower():
                return "CRITICAL"

        # 2. HIGH (external communications and sensitive write tools)
        if tool_name in {"email_sending"} or (tool_name == "email_drafting" and tool_input.get("send_immediately")):
            return "HIGH"
        if tool_name in cls.SENSITIVE_TOOLS:
            return "HIGH"
        for kw in cls.HIGH_KEYWORDS:
            if kw in payload_str:
                return "HIGH"

        # 3. MEDIUM (local document compilation, file transformation)
        if tool_name in {"document_generation", "file_processing"}:
            return "MEDIUM"

        # 4. LOW (pure read-only extraction and synthesis)
        if tool_name in {"web_research", "text_summarization"}:
            return "LOW"

        return "MEDIUM"

    @classmethod
    def evaluate_step(cls, tool_name: str, tool_input: Dict[str, Any]) -> Tuple[bool, str]:
        """
        Evaluates whether a step requires human approval.
        Returns (requires_approval: bool, reason: str).
        """
        risk = cls.classify_risk(tool_name, tool_input)

        if risk == "CRITICAL":
            return True, f"Operation classified as CRITICAL risk ('{tool_name}'). Mandatory administrative sign-off required."

        if risk == "HIGH":
            return True, f"Operation classified as HIGH risk ('{tool_name}'). External communication or state modification mandates supervisor approval."

        if registry.is_sensitive(tool_name) or tool_name in cls.SENSITIVE_TOOLS:
            return True, f"Tool '{tool_name}' performs external or privileged actions and requires human approval."

        return False, "Standard automated operation permitted."

    @classmethod
    def evaluate_step_with_risk(cls, tool_name: str, tool_input: Dict[str, Any]) -> Tuple[bool, str, str]:
        """
        Returns (requires_approval: bool, reason: str, risk_level: str).
        """
        risk = cls.classify_risk(tool_name, tool_input)
        req, reason = cls.evaluate_step(tool_name, tool_input)
        return req, reason, risk

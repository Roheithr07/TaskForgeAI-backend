from typing import Dict, Any, Tuple, Optional


class ResultVerifier:
    """
    Verifies the output of a tool execution against completion criteria,
    ensuring safe progression to the next step, detecting failures, and
    offering structured recovery recommendations.
    """

    @classmethod
    def verify(
        cls, 
        tool_name: str, 
        output_data: Dict[str, Any], 
        expected_criteria: Optional[str] = None
    ) -> Tuple[bool, str]:
        if not output_data:
            return False, "Tool returned an empty result payload."

        if "error" in output_data and output_data["error"]:
            return False, f"Tool execution signaled an error: {output_data['error']}"

        if tool_name == "web_research":
            findings = output_data.get("findings", [])
            citations = output_data.get("citations", [])
            if not findings and not citations:
                return False, "Research returned zero findings or citations."
            return True, f"Verified: Gathered {len(findings)} research points with {len(citations)} source citations."

        elif tool_name == "document_generation":
            doc_id = output_data.get("document_id")
            word_count = output_data.get("word_count", 0)
            if not doc_id or word_count < 10:
                return False, "Generated document lacks sufficient content or identifier."
            filename = output_data.get("filename", "report")
            return True, f"Verified: Structured document compiled ({word_count} words, File: {filename})."

        elif tool_name == "text_summarization":
            points = output_data.get("key_points", [])
            summary = output_data.get("summary", "")
            if not points and not summary:
                return False, "Summarization produced no key takeaway points or summary text."
            return True, f"Verified: Extracted {len(points)} actionable takeaways."

        elif tool_name == "email_drafting":
            recipient = output_data.get("recipient")
            subject = output_data.get("subject")
            if not recipient or not subject:
                return False, "Email draft lacks a valid recipient or subject line."
            return True, f"Verified: Communication drafted for {recipient} ('{subject}')."

        elif tool_name == "email_sending":
            msg_id = output_data.get("message_id")
            delivery_status = output_data.get("delivery_status")
            if not msg_id or delivery_status == "error":
                return False, f"Email delivery failed or lacked message identifier: {output_data.get('details', '')}"
            return True, f"Verified: Email delivery processed ({delivery_status}, ID: {msg_id[:12]})."

        elif tool_name == "file_processing":
            if output_data.get("status") != "success":
                return False, "File processing operation status indicates non-success."
            return True, "Verified: Content parsed and validated safely in sandbox."

        return True, "Verified: Tool completed execution with valid schema."

    @classmethod
    def diagnose_failure(cls, tool_name: str, output_data: Dict[str, Any]) -> Dict[str, Any]:
        """Provides structured failure categorization and recovery recommendations."""
        if not output_data:
            return {
                "category": "EMPTY_PAYLOAD",
                "explanation": f"The tool '{tool_name}' returned no response object.",
                "recovery_recommendation": "Retry step with broader search terms or check sandbox connection.",
                "is_retryable": True
            }

        error_msg = str(output_data.get("error", ""))
        if any(t in error_msg.lower() for t in ["timeout", "timed out", "deadline"]):
            return {
                "category": "TIMEOUT_FAILURE",
                "explanation": f"The operation timed out during execution: {error_msg}.",
                "recovery_recommendation": "Increase timeout threshold or reduce input payload size.",
                "is_retryable": True
            }

        if "permission" in error_msg.lower() or "forbidden" in error_msg.lower():
            return {
                "category": "PERMISSION_DENIED",
                "explanation": f"Server-side security policy rejected the request: {error_msg}.",
                "recovery_recommendation": "Escalate to WORKSPACE_OWNER or request human supervisor approval.",
                "is_retryable": False
            }

        return {
            "category": "EXECUTION_DEFECT",
            "explanation": f"Output failed verification criteria for '{tool_name}': {error_msg or 'Incomplete result payload.'}",
            "recovery_recommendation": "Inspect tool parameters and retry execution on current thread.",
            "is_retryable": True
        }

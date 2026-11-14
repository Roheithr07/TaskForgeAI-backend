import hashlib
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
from app.tools.base import BaseTool


class EmailDraftingInput(BaseModel):
    recipient_email: str = Field(..., description="Recipient email address")
    subject: str = Field(..., description="Subject line")
    body: str = Field(..., description="Main email body or draft content")
    cc: Optional[List[str]] = Field(default=[], description="List of CC email addresses")
    attachments: Optional[List[str]] = Field(default=[], description="List of attachment filenames or generated artifact paths")
    send_immediately: bool = Field(default=False, description="Whether to dispatch immediately upon approval")


class EmailDraftingOutput(BaseModel):
    draft_id: str
    recipient: str
    subject: str
    attachments: List[str]
    status: str
    action_taken: str
    preview: str


class EmailDraftingTool(BaseTool):
    name = "email_drafting"
    description = "Drafts and prepares emails for stakeholders. Deemed sensitive: requires human approval before dispatch or external communication."
    provider = "template_draft_engine"
    connection_status = "ready"
    permission_level = "SENSITIVE_APPROVAL_REQUIRED"
    is_sensitive = True
    requires_approval = True
    timeout_seconds = 10.0
    max_retries = 2
    input_model = EmailDraftingInput
    output_model = EmailDraftingOutput

    async def run(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        data = EmailDraftingInput(**input_data)
        
        draft_hash = hashlib.sha256(f"{data.recipient_email}:{data.subject}:{data.body}".encode("utf-8")).hexdigest()[:8]
        draft_id = f"eml_{draft_hash}"
        action_taken = (
            "Staged for automated dispatch; pending supervisor authorization."
            if data.send_immediately else
            "Draft generated and stored in Outbox queue awaiting final user authorization."
        )
        
        attachment_str = f"\nAttachments: {', '.join(data.attachments)}" if data.attachments else ""
        cc_str = f"\nCc: {', '.join(data.cc)}" if data.cc else ""
        
        result = EmailDraftingOutput(
            draft_id=draft_id,
            recipient=data.recipient_email,
            subject=data.subject,
            attachments=data.attachments or [],
            status="drafted",
            action_taken=action_taken,
            preview=f"To: {data.recipient_email}{cc_str}\nSubject: {data.subject}{attachment_str}\n\n{data.body}"
        )
        return result.model_dump()

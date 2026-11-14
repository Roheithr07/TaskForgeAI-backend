import os
import re
import hashlib
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
from datetime import datetime

from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, HRFlowable
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors

from app.core.config import settings
from app.tools.base import BaseTool

ARTIFACTS_DIR = settings.ARTIFACTS_DIR
os.makedirs(ARTIFACTS_DIR, exist_ok=True)


class DocumentGenerationInput(BaseModel):
    title: str = Field(..., description="Document title")
    format_type: str = Field(default="markdown", description="Document format: markdown, pdf, text, executive_brief")
    sections: List[Dict[str, str]] = Field(..., description="List of section objects containing 'heading' and 'content'")
    author: Optional[str] = Field(default="TaskForge Autonomous Agent", description="Author or agent name")
    custom_filename: Optional[str] = Field(default=None, description="Optional custom filename without directory traversal")


class DocumentGenerationOutput(BaseModel):
    document_id: str
    title: str
    format: str
    filename: str
    file_path: str
    download_url: str
    file_size_bytes: int
    checksum_sha256: str
    content: str
    word_count: int
    generated_at: str


class DocumentGenerationTool(BaseTool):
    name = "document_generation"
    description = "Assembles structured, executive-ready documentation, technical reports, and PDF documents from section inputs."
    provider = "reportlab_doc_engine"
    connection_status = "ready"
    permission_level = "PUBLIC"
    is_sensitive = False
    requires_approval = False
    timeout_seconds = 20.0
    max_retries = 2
    input_model = DocumentGenerationInput
    output_model = DocumentGenerationOutput

    @staticmethod
    def sanitize_filename(name: str, ext: str) -> str:
        # Strip all path navigation or dangerous chars
        clean = re.sub(r'[^a-zA-Z0-9_\-\.]', '_', name).strip('._')
        if not clean:
            clean = "taskforge_document"
        if not clean.lower().endswith(f".{ext.lower()}"):
            clean = f"{clean}.{ext.lower()}"
        return clean

    @classmethod
    def get_safe_artifact_path(cls, filename: str) -> str:
        target_path = os.path.abspath(os.path.join(ARTIFACTS_DIR, filename))
        real_artifacts_dir = os.path.abspath(ARTIFACTS_DIR)
        if not target_path.startswith(real_artifacts_dir):
            raise ValueError(f"Path traversal detected: attempt to write outside {real_artifacts_dir}")
        return target_path

    async def run(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        data = DocumentGenerationInput(**input_data)
        doc_format = data.format_type.lower()
        timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
        doc_id = f"doc_{int(datetime.utcnow().timestamp())}"

        # Markdown / Text Content Builder
        lines = [
            f"# {data.title}",
            f"*Author: {data.author}* | *Generated: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}*",
            "---",
            ""
        ]
        total_text = ""
        for section in data.sections:
            heading = section.get("heading", "Section")
            content = section.get("content", "")
            lines.append(f"## {heading}\n")
            lines.append(f"{content}\n")
            total_text += f" {content}"

        full_content = "\n".join(lines)
        word_count = len(full_content.split())

        if "pdf" in doc_format:
            ext = "pdf"
            base_name = data.custom_filename or f"{data.title}_{timestamp}"
            filename = self.sanitize_filename(base_name, ext)
            file_path = self.get_safe_artifact_path(filename)
            
            # Real PDF compilation with ReportLab
            doc = SimpleDocTemplate(
                file_path,
                pagesize=letter,
                rightMargin=54,
                leftMargin=54,
                topMargin=54,
                bottomMargin=54
            )
            styles = getSampleStyleSheet()

            # Custom styling matching TaskForge dark/indigo brand accents
            title_style = ParagraphStyle(
                'DocTitle',
                parent=styles['Heading1'],
                fontSize=22,
                leading=26,
                textColor=colors.HexColor('#2A2D34'),
                spaceAfter=6
            )
            meta_style = ParagraphStyle(
                'DocMeta',
                parent=styles['Normal'],
                fontSize=9,
                textColor=colors.HexColor('#6B7280'),
                spaceAfter=14
            )
            heading_style = ParagraphStyle(
                'DocHeading',
                parent=styles['Heading2'],
                fontSize=14,
                leading=18,
                textColor=colors.HexColor('#8068EF'),
                spaceBefore=12,
                spaceAfter=6
            )
            body_style = ParagraphStyle(
                'DocBody',
                parent=styles['Normal'],
                fontSize=10,
                leading=14,
                textColor=colors.HexColor('#1F2937'),
                spaceAfter=8
            )

            story = [
                Paragraph(data.title, title_style),
                Paragraph(f"Author: {data.author} &bull; Generated: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}", meta_style),
                HRFlowable(width="100%", thickness=1, color=colors.HexColor('#E5E7EB'), spaceBefore=2, spaceAfter=14)
            ]

            for section in data.sections:
                heading = section.get("heading", "Section")
                content = section.get("content", "")
                story.append(Paragraph(heading, heading_style))
                story.append(Paragraph(content.replace("\n", "<br/>"), body_style))
                story.append(Spacer(1, 6))

            doc.build(story)

            with open(file_path, "rb") as f:
                file_bytes = f.read()
        else:
            ext = "md" if "markdown" in doc_format else "txt"
            base_name = data.custom_filename or f"{data.title}_{timestamp}"
            filename = self.sanitize_filename(base_name, ext)
            file_path = self.get_safe_artifact_path(filename)
            file_bytes = full_content.encode("utf-8")
            with open(file_path, "wb") as f:
                f.write(file_bytes)

        file_size = len(file_bytes)
        checksum = hashlib.sha256(file_bytes).hexdigest()
        download_url = f"/api/v1/artifacts/{filename}"

        result = DocumentGenerationOutput(
            document_id=doc_id,
            title=data.title,
            format=ext.upper(),
            filename=filename,
            file_path=file_path,
            download_url=download_url,
            file_size_bytes=file_size,
            checksum_sha256=checksum,
            content=full_content,
            word_count=word_count,
            generated_at=datetime.utcnow().isoformat()
        )
        return result.model_dump()

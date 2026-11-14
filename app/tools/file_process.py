import os
import json
import io
import re
from typing import Dict, Any, Optional
from pydantic import BaseModel, Field
from pypdf import PdfReader
from app.tools.base import BaseTool

MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024  # 10 MB strict limit
DISALLOWED_EXTENSIONS = {".exe", ".bat", ".cmd", ".sh", ".dll", ".so", ".bin", ".vbs", ".ps1"}


class FileProcessingInput(BaseModel):
    operation: str = Field(..., description="Operation: parse_json, extract_metadata, extract_text, sanitize_text, inspect_pdf")
    content: Optional[str] = Field(default=None, description="Direct text, JSON string, or Base64 payload to process")
    file_path: Optional[str] = Field(default=None, description="Path to file on disk to inspect within allowed storage")
    file_type: Optional[str] = Field(default=None, description="Optional explicit file type hint: json, pdf, txt, docx")
    options: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Operation specific arguments")


class FileProcessingOutput(BaseModel):
    operation: str
    file_type: str
    processed_size_bytes: int
    result_data: Dict[str, Any]
    status: str
    metadata: Dict[str, Any]


class FileProcessingTool(BaseTool):
    name = "file_processing"
    description = "Secure sandboxed processor for extracting content, metadata, and structuring files (PDF, DOCX, TXT, JSON) with strict size limits."
    provider = "sandbox_file_extractor"
    connection_status = "ready"
    permission_level = "PUBLIC"
    is_sensitive = False
    requires_approval = False
    timeout_seconds = 20.0
    max_retries = 2
    input_model = FileProcessingInput
    output_model = FileProcessingOutput

    @staticmethod
    def validate_file_safety(path: str):
        ext = os.path.splitext(path)[1].lower()
        if ext in DISALLOWED_EXTENSIONS:
            raise ValueError(f"Security restriction: Execution of '{ext}' files is strictly prohibited.")
        if os.path.exists(path):
            size = os.path.getsize(path)
            if size > MAX_FILE_SIZE_BYTES:
                raise ValueError(f"File size exceeds maximum permitted threshold (10 MB). File is {round(size / (1024*1024), 2)} MB.")

    async def run(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        data = FileProcessingInput(**input_data)
        op = data.operation.lower()
        
        # Read content from file_path or direct content
        raw_bytes = b""
        inferred_type = (data.file_type or "txt").lower()
        file_meta = {}

        if data.file_path:
            self.validate_file_safety(data.file_path)
            ext = os.path.splitext(data.file_path)[1].lower().replace(".", "")
            if ext:
                inferred_type = ext
            with open(data.file_path, "rb") as f:
                raw_bytes = f.read()
            file_meta["source_filename"] = os.path.basename(data.file_path)
        elif data.content is not None:
            raw_bytes = data.content.encode("utf-8")
            if len(raw_bytes) > MAX_FILE_SIZE_BYTES:
                raise ValueError(f"Content payload exceeds 10 MB limit ({len(raw_bytes)} bytes).")
            if data.content.strip().startswith("{") or data.content.strip().startswith("["):
                inferred_type = "json"
        else:
            raise ValueError("Either 'content' or 'file_path' must be provided.")

        processed_size = len(raw_bytes)
        result_data: Dict[str, Any] = {}

        if op == "parse_json" or (op == "extract_metadata" and inferred_type == "json"):
            text_str = raw_bytes.decode("utf-8", errors="replace")
            try:
                parsed = json.loads(text_str)
                is_dict = isinstance(parsed, dict)
                result_data = {
                    "valid_json": True,
                    "root_type": "object" if is_dict else "array",
                    "element_count": len(parsed),
                    "keys": list(parsed.keys())[:20] if is_dict else [],
                    "sample": parsed if len(text_str) < 500 else "Payload truncated for summary"
                }
            except Exception as e:
                result_data = {"valid_json": False, "error": str(e)}

        elif op in {"inspect_pdf", "extract_text"} and inferred_type == "pdf":
            try:
                reader = PdfReader(io.BytesIO(raw_bytes))
                pages_text = []
                for p_idx, page in enumerate(reader.pages[:10]):  # extract up to first 10 pages
                    extracted = page.extract_text() or ""
                    if extracted.strip():
                        pages_text.append(f"--- Page {p_idx + 1} ---\n{extracted.strip()}")

                doc_info = reader.metadata or {}
                result_data = {
                    "page_count": len(reader.pages),
                    "extracted_text_preview": "\n\n".join(pages_text)[:4000],
                    "pdf_metadata": {
                        "title": doc_info.title if hasattr(doc_info, "title") else None,
                        "author": doc_info.author if hasattr(doc_info, "author") else None,
                        "creator": doc_info.creator if hasattr(doc_info, "creator") else None
                    }
                }
            except Exception as e:
                result_data = {"error": f"PDF parsing error: {str(e)}"}

        elif op == "extract_metadata":
            text_str = raw_bytes.decode("utf-8", errors="replace")
            lines = text_str.splitlines()
            words = text_str.split()
            result_data = {
                "line_count": len(lines),
                "word_count": len(words),
                "character_count": len(text_str),
                "estimated_reading_minutes": max(1, round(len(words) / 200)),
                "detected_encoding": "utf-8"
            }

        elif op == "sanitize_text":
            text_str = raw_bytes.decode("utf-8", errors="replace")
            # Strip null bytes and normalize line breaks
            cleaned = text_str.replace("\x00", "").replace("\r\n", "\n").strip()
            # Remove potential script tags
            cleaned = re.sub(r'<\s*script[^>]*>.*?<\s*/\s*script\s*>', '', cleaned, flags=re.DOTALL | re.IGNORECASE)
            result_data = {
                "sanitized_content": cleaned,
                "original_length": len(text_str),
                "cleaned_length": len(cleaned),
                "modifications": ["stripped_null_bytes", "normalized_newlines", "removed_script_injections"]
            }

        else:
            text_str = raw_bytes.decode("utf-8", errors="replace")
            result_data = {
                "preview": text_str[:1000] + ("..." if len(text_str) > 1000 else ""),
                "total_characters": len(text_str),
                "operation": op
            }

        result = FileProcessingOutput(
            operation=op,
            file_type=inferred_type,
            processed_size_bytes=processed_size,
            result_data=result_data,
            status="success",
            metadata=file_meta
        )
        return result.model_dump()

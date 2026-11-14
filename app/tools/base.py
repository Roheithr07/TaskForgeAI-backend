from abc import ABC, abstractmethod
from typing import Dict, Any, Type, Optional, List
from datetime import datetime
from pydantic import BaseModel


class BaseTool(ABC):
    name: str
    description: str
    provider: str = "internal"
    connection_status: str = "ready"  # ready | connected | configured | offline
    permission_level: str = "PUBLIC"  # PUBLIC | SENSITIVE_APPROVAL_REQUIRED
    is_sensitive: bool = False
    requires_approval: bool = False
    timeout_seconds: float = 15.0
    max_retries: int = 3
    input_model: Type[BaseModel]
    output_model: Type[BaseModel]

    def __init__(self):
        self.total_invocations: int = 0
        self.successful_invocations: int = 0
        self.failed_invocations: int = 0
        self.last_executed_at: Optional[str] = None
        self.audit_log: List[Dict[str, Any]] = []

    @abstractmethod
    async def run(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """Execute the tool logic and return structured output."""
        pass

    def record_execution(self, success: bool, duration_ms: float, error: Optional[str] = None, metadata: Optional[Dict[str, Any]] = None):
        self.total_invocations += 1
        now = datetime.utcnow().isoformat()
        self.last_executed_at = now
        if success:
            self.successful_invocations += 1
        else:
            self.failed_invocations += 1

        log_entry = {
            "timestamp": now,
            "success": success,
            "duration_ms": round(duration_ms, 2),
            "error": error,
            "metadata": metadata or {}
        }
        self.audit_log.append(log_entry)
        if len(self.audit_log) > 50:
            self.audit_log.pop(0)

    def get_stats(self) -> Dict[str, Any]:
        success_rate = (
            round((self.successful_invocations / self.total_invocations) * 100, 1)
            if self.total_invocations > 0 else 100.0
        )
        return {
            "total_invocations": self.total_invocations,
            "successful_invocations": self.successful_invocations,
            "failed_invocations": self.failed_invocations,
            "success_rate_percent": success_rate,
            "last_executed_at": self.last_executed_at
        }

    def get_info(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "provider": self.provider,
            "connection_status": self.connection_status,
            "permission_level": self.permission_level,
            "is_sensitive": self.is_sensitive,
            "requires_approval": self.requires_approval,
            "timeout_seconds": self.timeout_seconds,
            "max_retries": self.max_retries,
            "input_schema": self.input_model.model_json_schema(),
            "output_schema": self.output_model.model_json_schema(),
            "stats": self.get_stats()
        }

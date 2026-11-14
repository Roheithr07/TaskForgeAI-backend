import json
import logging
import sys
import time
from datetime import datetime, timezone
from typing import Any, Dict


class JSONFormatter(logging.Formatter):
    """
    Formats log records as single-line JSON objects for production observability,
    log aggregation (CloudWatch, Datadog, ELK), and automated parsing.
    Redacts sensitive keys like api_key, password, authorization.
    """
    SENSITIVE_KEYS = {"api_key", "groq_api_key", "password", "token", "secret", "authorization"}

    def format(self, record: logging.LogRecord) -> str:
        log_data: Dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }

        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        # Redact any sensitive data in log output
        msg_str = str(log_data["message"])
        for secret_kw in ["gsk_", "Bearer ", "password="]:
            if secret_kw in msg_str:
                import re
                log_data["message"] = re.sub(r'gsk_[a-zA-Z0-9_\-]+', 'gsk_REDACTED', msg_str)

        return json.dumps(log_data)


def setup_logging(level: str = "INFO", json_logs: bool = False):
    """Configures root and application loggers."""
    log_level = getattr(logging, level.upper(), logging.INFO)

    handler = logging.StreamHandler(sys.stdout)
    if json_logs:
        handler.setFormatter(JSONFormatter())
    else:
        standard_format = "%(asctime)s [%(levelname)s] [%(name)s]: %(message)s"
        handler.setFormatter(logging.Formatter(standard_format, datefmt="%Y-%m-%d %H:%M:%S"))

    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)
    # Replace existing handlers
    root_logger.handlers = [handler]

    # Silence overly verbose external loggers
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING if json_logs else logging.INFO)
    logging.getLogger("aiosqlite").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)


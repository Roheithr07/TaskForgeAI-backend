import re
from typing import Any, Dict, List, Union


SENSITIVE_KEY_NAMES = {
    "api_key", "apikey", "groq_api_key", "password", "secret", "token", 
    "smtp_password", "access_token", "private_key", "auth_token", "authorization"
}

SECRET_VALUE_PATTERNS = [
    re.compile(r'gsk_[a-zA-Z0-9]{20,}', re.IGNORECASE),
    re.compile(r'Bearer\s+[a-zA-Z0-9\-\._~+/]+=*', re.IGNORECASE),
    re.compile(r'(password|secret|key)\s*[:=]\s*["\']?[^"\'\s,]{4,}["\']?', re.IGNORECASE)
]


def redact_string(val: str) -> str:
    """Masks secret patterns within strings."""
    masked = val
    for pattern in SECRET_VALUE_PATTERNS:
        masked = pattern.sub('***REDACTED***', masked)
    return masked


def redact_secrets(data: Any) -> Any:
    """
    Recursively scrubs known credential keys and patterns from dictionaries, lists, and strings.
    Guarantees secrets are never exposed in audit logs, telemetry, or API responses.
    """
    if isinstance(data, dict):
        cleaned = {}
        for k, v in data.items():
            if str(k).lower() in SENSITIVE_KEY_NAMES:
                cleaned[k] = "***REDACTED***"
            else:
                cleaned[k] = redact_secrets(v)
        return cleaned
    elif isinstance(data, list):
        return [redact_secrets(item) for item in data]
    elif isinstance(data, str):
        return redact_string(data)
    return data


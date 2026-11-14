import os
import json
import logging
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.core.config import Settings
from app.core.logging_config import JSONFormatter
from app.api.v1.artifacts import safe_artifact_path
from fastapi import HTTPException


@pytest.fixture
def client():
    return TestClient(app)


def test_settings_production_defaults():
    s = Settings(
        APP_ENV="production",
        APP_DEBUG=False,
        GROQ_API_KEY="gsk_test1234567890",
        ALLOWED_ORIGINS="https://app.taskforge.ai,https://admin.taskforge.ai"
    )
    assert s.is_production is True
    assert s.is_groq_configured is True
    assert "https://app.taskforge.ai" in s.parsed_allowed_origins
    assert "https://admin.taskforge.ai" in s.parsed_allowed_origins


def test_health_liveness_endpoint(client):
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "uptime_seconds" in data
    assert "timestamp" in data
    assert "app_name" in data


def test_readiness_probe_endpoint(client):
    response = client.get("/api/v1/ready")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ready"
    assert data["checks"]["database"] is True
    assert data["checks"]["artifacts_storage"] is True


def test_json_log_formatter_and_redaction():
    formatter = JSONFormatter()
    record = logging.LogRecord(
        name="test_logger",
        level=logging.INFO,
        pathname="test.py",
        lineno=10,
        msg="Connecting to Groq using key gsk_abc123xyz456 secret",
        args=(),
        exc_info=None
    )
    formatted = formatter.format(record)
    log_dict = json.loads(formatted)
    
    assert log_dict["level"] == "INFO"
    assert log_dict["logger"] == "test_logger"
    # Ensure sensitive groq key was redacted
    assert "gsk_abc123xyz456" not in log_dict["message"]
    assert "gsk_REDACTED" in log_dict["message"]


def test_safe_artifact_path_traversal_prevention():
    # Legitimate filenames should pass
    valid_path = safe_artifact_path("report_2026.pdf")
    assert os.path.basename(valid_path) == "report_2026.pdf"

    # Traversal sequences must be rejected with HTTPException 400
    with pytest.raises(HTTPException) as exc1:
        safe_artifact_path("../secret.env")
    assert exc1.value.status_code == 400

    with pytest.raises(HTTPException) as exc2:
        safe_artifact_path("subdir/../../etc/passwd")
    assert exc2.value.status_code == 400

    with pytest.raises(HTTPException) as exc3:
        safe_artifact_path("..\\..\\windows\\system32\\cmd.exe")
    assert exc3.value.status_code == 400


def test_root_endpoint_metadata(client):
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert "service" in data
    assert "health" in data
    assert "ready" in data


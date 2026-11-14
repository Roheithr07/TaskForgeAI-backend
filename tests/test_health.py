import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_health_endpoint():
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] in ["healthy", "degraded"]
    assert "app_name" in data
    assert data["app_name"] == "TaskForge AI"


def test_llm_test_endpoint():
    response = client.post("/api/v1/llm/test", json={"prompt": "Test connectivity"})
    assert response.status_code == 200
    data = response.json()
    assert "status" in data


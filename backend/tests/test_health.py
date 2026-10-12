from fastapi.testclient import TestClient

from app import __version__
from app.config import Settings
from app.main import create_app

client = TestClient(create_app(Settings(cors_origins=["http://localhost:5173"])))


def test_health_returns_ok():
    response = client.get("/api/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["service"] == "speakiq-ai-coach-backend"
    assert body["version"] == __version__


def test_health_allows_configured_frontend_origin():
    response = client.get("/api/health", headers={"Origin": "http://localhost:5173"})

    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"


def test_health_does_not_allow_unknown_origin():
    response = client.get("/api/health", headers={"Origin": "http://evil.example"})

    assert "access-control-allow-origin" not in response.headers


def test_unknown_route_returns_404():
    assert client.get("/does-not-exist").status_code == 404

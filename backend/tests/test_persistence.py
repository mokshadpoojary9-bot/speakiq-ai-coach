"""Optional persistence (Prompt 8). No Supabase project, network or credentials are needed: the store is
in memory, and the Supabase client is exercised against a mock HTTP transport."""

import json

import httpx
import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.persistence import AnalysisArchive, DisabledStore, PersistenceError, SupabaseStore, hash_key, make_store

from .audio_samples import encode
from .detection_fixtures import make_take
from .speech_fakes import FakeModel, transcriber_with

SERVICE_KEY = "test-service-role-key-not-real-0123456789"
SUPABASE_URL = "https://example-project.supabase.co"


class MemoryStore:
    configured = True

    def __init__(self) -> None:
        self.rows: dict[str, tuple[str, dict, str]] = {}

    def insert(self, analysis_id, key_hash, result, created_at):
        self.rows[analysis_id] = (key_hash, result, created_at)

    def fetch(self, analysis_id):
        return self.rows.get(analysis_id)

    def remove(self, analysis_id):
        self.rows.pop(analysis_id, None)


def client_with(store=None, **settings) -> tuple[TestClient, MemoryStore | None]:
    store = store if store is not None else MemoryStore()
    app = create_app(Settings(**settings), transcriber=transcriber_with(FakeModel([])), archive=AnalysisArchive(store))
    return TestClient(app), store


def analysis_result(client: TestClient) -> dict:
    response = client.post("/api/analyze", files={"file": ("take.wav", encode(make_take(pauses={14: 2.0}).audio))})
    assert response.status_code == 200
    return response.json()


# --- Without configuration --------------------------------------------------------------------


def test_saving_is_off_without_credentials_and_says_how_to_turn_it_on():
    client = TestClient(create_app(Settings(supabase_url=None, supabase_service_role_key=None), transcriber=transcriber_with(FakeModel([]))))

    assert client.get("/api/health").json()["persistence"] == {"configured": False}
    response = client.post("/api/analyses", json=analysis_result(client))

    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "persistence_not_configured"
    assert "SUPABASE_SERVICE_ROLE_KEY" in response.json()["detail"]["message"]
    assert client.get("/api/analyses/00000000-0000-0000-0000-000000000000", headers={"X-Access-Key": "x" * 20}).status_code == 503


@pytest.mark.parametrize(("url", "key"), [(None, None), (SUPABASE_URL, None), (None, SERVICE_KEY), ("", "")])
def test_partial_configuration_leaves_saving_off(url, key):
    assert isinstance(make_store(url, key), DisabledStore)


def test_analysis_works_normally_without_persistence():
    client = TestClient(create_app(Settings(supabase_url=None, supabase_service_role_key=None), transcriber=transcriber_with(FakeModel([]))))

    body = analysis_result(client)

    assert body["features"]["pauses"]["status"] == "measured"
    assert body["findings"]


def test_empty_placeholders_in_the_environment_count_as_not_configured(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "  ")

    settings = Settings()

    assert (settings.supabase_url, settings.supabase_service_role_key) == (None, None)


# --- Saving, opening and deleting -------------------------------------------------------------


def test_save_then_open_with_the_key_returns_the_same_analysis():
    client, store = client_with()
    result = analysis_result(client)

    saved = client.post("/api/analyses", json=result)

    assert saved.status_code == 201
    body = saved.json()
    assert set(body) == {"id", "access_key", "created_at"}
    stored_hash, stored_result, _ = store.rows[body["id"]]
    assert stored_hash == hash_key(body["access_key"])
    assert body["access_key"] not in json.dumps(store.rows[body["id"]])  # only the hash is kept
    opened = client.get(f"/api/analyses/{body['id']}", headers={"X-Access-Key": body["access_key"]})
    assert opened.status_code == 200
    assert opened.json()["result"] == result
    assert opened.json()["id"] == body["id"]


def test_a_wrong_key_and_an_unknown_id_look_the_same():
    client, _ = client_with()
    saved = client.post("/api/analyses", json=analysis_result(client)).json()

    wrong_key = client.get(f"/api/analyses/{saved['id']}", headers={"X-Access-Key": "not-the-right-key"})
    unknown = client.get("/api/analyses/11111111-1111-1111-1111-111111111111", headers={"X-Access-Key": saved["access_key"]})
    malformed = client.get("/api/analyses/not-a-uuid", headers={"X-Access-Key": saved["access_key"]})

    for response in (wrong_key, unknown, malformed):
        assert response.status_code == 404
        assert response.json()["detail"] == {"code": "analysis_not_found", "message": "No saved analysis matches that ID and access key."}


def test_opening_needs_the_key_header():
    client, _ = client_with()
    saved = client.post("/api/analyses", json=analysis_result(client)).json()

    response = client.get(f"/api/analyses/{saved['id']}")

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "invalid_request"


def test_delete_needs_the_key_and_then_the_analysis_is_gone():
    client, store = client_with()
    saved = client.post("/api/analyses", json=analysis_result(client)).json()

    assert client.delete(f"/api/analyses/{saved['id']}", headers={"X-Access-Key": "wrong-key-123"}).status_code == 404
    assert saved["id"] in store.rows
    assert client.delete(f"/api/analyses/{saved['id']}", headers={"X-Access-Key": saved["access_key"]}).status_code == 204
    assert saved["id"] not in store.rows
    assert client.get(f"/api/analyses/{saved['id']}", headers={"X-Access-Key": saved["access_key"]}).status_code == 404


def test_each_save_gets_a_new_id_and_key():
    client, _ = client_with()
    result = analysis_result(client)

    first, second = (client.post("/api/analyses", json=result).json() for _ in range(2))

    assert first["id"] != second["id"]
    assert first["access_key"] != second["access_key"]
    assert len(first["access_key"]) >= 32


def test_only_real_analysis_results_can_be_saved():
    client, store = client_with()
    demo = {**analysis_result(client), "is_demo": True}
    junk = {"anything": "else"}

    for body in (demo, junk):
        response = client.post("/api/analyses", json=body)
        assert response.status_code == 422
        assert response.json()["detail"]["code"] == "invalid_request"
    assert store.rows == {}


def test_oversized_results_are_refused():
    client, store = client_with(max_saved_result_mb=0.001)

    response = client.post("/api/analyses", json=analysis_result(client))

    assert (response.status_code, response.json()["detail"]["code"]) == (413, "result_too_large")
    assert store.rows == {}


def test_there_is_no_way_to_list_saved_analyses():
    client, _ = client_with()

    paths = client.get("/openapi.json").json()["paths"]

    assert set(paths["/api/analyses"]) == {"post"}
    assert set(paths["/api/analyses/{analysis_id}"]) == {"get", "delete"}


# --- The Supabase client, against a mock transport --------------------------------------------


def supabase_store(handler) -> SupabaseStore:
    return SupabaseStore(SUPABASE_URL, SERVICE_KEY, client=httpx.Client(transport=httpx.MockTransport(handler)))


def test_supabase_requests_use_the_rest_endpoint_and_the_backend_key():
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.method == "GET":
            return httpx.Response(200, json=[{"access_key_hash": "h" * 64, "result": {"a": 1}, "created_at": "2026-10-14T00:00:00+00:00"}])
        return httpx.Response(201 if request.method == "POST" else 204)

    store = supabase_store(handler)
    store.insert("id-1", "h" * 64, {"a": 1}, "2026-10-14T00:00:00+00:00")
    row = store.fetch("id-1")
    store.remove("id-1")

    assert row == ("h" * 64, {"a": 1}, "2026-10-14T00:00:00+00:00")
    insert, fetch, remove = seen
    assert str(insert.url) == f"{SUPABASE_URL}/rest/v1/analyses"
    assert json.loads(insert.content) == {"id": "id-1", "access_key_hash": "h" * 64, "result": {"a": 1}, "created_at": "2026-10-14T00:00:00+00:00"}
    assert fetch.url.params["id"] == "eq.id-1"
    assert remove.method == "DELETE" and remove.url.params["id"] == "eq.id-1"
    for request in seen:
        assert request.headers["apikey"] == SERVICE_KEY
        assert request.headers["authorization"] == f"Bearer {SERVICE_KEY}"


def test_a_missing_row_is_none():
    assert supabase_store(lambda request: httpx.Response(200, json=[])).fetch("id-1") is None


@pytest.mark.parametrize(
    ("handler", "code", "status"),
    [
        (lambda request: httpx.Response(401, json={"message": f"bad key {SERVICE_KEY}"}), "persistence_failed", 502),
        (lambda request: httpx.Response(500, text=f"internal error at {SUPABASE_URL}"), "persistence_failed", 502),
    ],
    ids=["refused", "server-error"],
)
def test_supabase_errors_are_reported_without_leaking_the_key_or_url(handler, code, status):
    with pytest.raises(PersistenceError) as error:
        supabase_store(handler).insert("id-1", "h" * 64, {}, "now")

    assert (error.value.code, error.value.status_code) == (code, status)
    assert SERVICE_KEY not in error.value.message and SUPABASE_URL not in error.value.message


def test_an_unreachable_database_is_reported_without_details():
    def handler(request):
        raise httpx.ConnectError(f"cannot connect to {SUPABASE_URL}")

    with pytest.raises(PersistenceError) as error:
        supabase_store(handler).fetch("id-1")

    assert error.value.code == "persistence_unavailable"
    assert SUPABASE_URL not in error.value.message
    assert error.value.__cause__ is None


def test_the_api_reports_database_failures_safely():
    def handler(request):
        return httpx.Response(503, text=f"upstream down, key {SERVICE_KEY}")

    store = supabase_store(handler)
    client, _ = client_with(store=store)

    response = client.post("/api/analyses", json=analysis_result(client))

    assert response.status_code == 502
    assert response.json()["detail"]["code"] == "persistence_failed"
    assert SERVICE_KEY not in response.text and SUPABASE_URL not in response.text


# --- Secrets ----------------------------------------------------------------------------------


def test_the_service_role_key_is_never_shown():
    settings = Settings(supabase_url=SUPABASE_URL, supabase_service_role_key=SERVICE_KEY)
    client = TestClient(create_app(settings, transcriber=transcriber_with(FakeModel([]))))

    health = client.get("/api/health")

    assert SERVICE_KEY not in repr(settings)
    assert health.json()["persistence"] == {"configured": True}
    assert SERVICE_KEY not in health.text and SUPABASE_URL not in health.text


def test_env_example_holds_only_empty_placeholders_for_supabase():
    from pathlib import Path

    lines = (Path(__file__).resolve().parents[1] / ".env.example").read_text(encoding="utf-8").splitlines()
    values = dict(line.split("=", 1) for line in lines if "=" in line and not line.startswith("#"))

    assert values["SUPABASE_URL"] == ""
    assert values["SUPABASE_SERVICE_ROLE_KEY"] == ""
    frontend_example = (Path(__file__).resolve().parents[2] / "frontend" / ".env.example").read_text(encoding="utf-8")
    assert "SUPABASE" not in frontend_example.replace("Supabase secret keys", "")

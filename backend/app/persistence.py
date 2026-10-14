"""Optional storage of analysis results in Supabase. Off unless the backend is configured for it.

Only the analysis result is stored: measurements, transcript text, findings. Audio is never stored.
There are no user accounts, so access works by possession of a secret: saving returns an ID and a
random access key, only the key's SHA-256 hash is stored, and reading or deleting needs both. There
is deliberately no way to list saved analyses.

Supabase is reached only from the backend, with the service-role key, through its REST interface.
That key bypasses row-level security, so it must never reach the browser; the table itself has
row-level security on and no policies (see docs/supabase/schema.sql), so the public anon key cannot
read or write it.
"""

import hashlib
import hmac
import secrets
import uuid
from datetime import datetime, timezone
from typing import Any, Protocol

import httpx

TIMEOUT_SEC = 10.0


class PersistenceError(Exception):
    """A storage problem. `message` is safe to show to the client."""

    def __init__(self, code: str, message: str, status_code: int) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


NOT_CONFIGURED = PersistenceError(
    "persistence_not_configured",
    "Saving analyses is not set up on this backend. Set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY in backend/.env to enable it.",
    503,
)
NOT_FOUND = PersistenceError("analysis_not_found", "No saved analysis matches that ID and access key.", 404)


def hash_key(key: str) -> str:
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


def new_credentials() -> tuple[str, str]:
    return str(uuid.uuid4()), secrets.token_urlsafe(24)


class Store(Protocol):
    configured: bool

    def insert(self, analysis_id: str, key_hash: str, result: dict[str, Any], created_at: str) -> None: ...

    def fetch(self, analysis_id: str) -> tuple[str, dict[str, Any], str] | None:
        """(key_hash, result, created_at), or None if there is no such row."""

    def remove(self, analysis_id: str) -> None: ...


class DisabledStore:
    configured = False

    def insert(self, *args) -> None:
        raise NOT_CONFIGURED

    def fetch(self, *args):
        raise NOT_CONFIGURED

    def remove(self, *args) -> None:
        raise NOT_CONFIGURED


class SupabaseStore:
    """PostgREST calls against one table. Errors never include the key, the URL or the upstream response."""

    configured = True

    def __init__(self, url: str, service_role_key: str, table: str = "analyses", client: httpx.Client | None = None) -> None:
        self._endpoint = f"{url.rstrip('/')}/rest/v1/{table}"
        self._headers = {"apikey": service_role_key, "Authorization": f"Bearer {service_role_key}"}
        self._client = client or httpx.Client(timeout=TIMEOUT_SEC)

    def _call(self, method: str, **kwargs) -> httpx.Response:
        try:
            response = self._client.request(method, self._endpoint, headers=self._headers | kwargs.pop("headers", {}), **kwargs)
        except httpx.HTTPError as error:
            raise PersistenceError("persistence_unavailable", "The analysis database could not be reached.", 502) from None
        if response.status_code >= 400:
            raise PersistenceError("persistence_failed", f"The analysis database refused the request (HTTP {response.status_code}).", 502)
        return response

    def insert(self, analysis_id: str, key_hash: str, result: dict[str, Any], created_at: str) -> None:
        self._call(
            "POST",
            json={"id": analysis_id, "access_key_hash": key_hash, "result": result, "created_at": created_at},
            headers={"Prefer": "return=minimal"},
        )

    def fetch(self, analysis_id: str):
        rows = self._call("GET", params={"id": f"eq.{analysis_id}", "select": "access_key_hash,result,created_at"}).json()
        if not rows:
            return None
        row = rows[0]
        return row["access_key_hash"], row["result"], row["created_at"]

    def remove(self, analysis_id: str) -> None:
        self._call("DELETE", params={"id": f"eq.{analysis_id}"})


def make_store(url: str | None, service_role_key: str | None, table: str = "analyses") -> Store:
    if not url or not service_role_key:
        return DisabledStore()
    return SupabaseStore(url, service_role_key, table)


class AnalysisArchive:
    """Saving, opening and deleting with the access-key check, on top of any store."""

    def __init__(self, store: Store) -> None:
        self.store = store

    @property
    def configured(self) -> bool:
        return self.store.configured

    def save(self, result: dict[str, Any]) -> tuple[str, str, str]:
        analysis_id, key = new_credentials()
        created_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        self.store.insert(analysis_id, hash_key(key), result, created_at)
        return analysis_id, key, created_at

    def _authorised(self, analysis_id: str, key: str) -> tuple[dict[str, Any], str]:
        try:
            uuid.UUID(analysis_id)
        except ValueError:
            raise NOT_FOUND from None
        row = self.store.fetch(analysis_id)
        # The same answer for a wrong ID and a wrong key, so IDs cannot be probed.
        if row is None or not hmac.compare_digest(row[0], hash_key(key)):
            raise NOT_FOUND
        return row[1], row[2]

    def open(self, analysis_id: str, key: str) -> tuple[dict[str, Any], str]:
        return self._authorised(analysis_id, key)

    def delete(self, analysis_id: str, key: str) -> None:
        self._authorised(analysis_id, key)
        self.store.remove(analysis_id)

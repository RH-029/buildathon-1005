"""Hosted travel memory, independent of the planner and UI (Python 3.10+)."""

import os
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any


class MemoryServiceError(RuntimeError):
    """Safe to display: no credentials or raw provider responses."""


def _text(value: str, name: str, maximum: int = 8000) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string.")
    value = value.strip()
    if len(value) > maximum:
        raise ValueError(f"{name} must be at most {maximum} characters.")
    return value


class TravelMemory:
    """One user_id per traveler. Group reads never create shared preferences.

    Public methods return JSON-serializable dictionaries. Construct once per
    backend process and close at shutdown, or use as a context manager.
    """

    def __init__(self, client: Any = None):
        self._http = None
        if client is not None:  # Inject a fake client for offline tests.
            self._client = client
            return

        from dotenv import load_dotenv
        root = Path(__file__).resolve().parent
        load_dotenv(root / ".env.local")
        load_dotenv(root / ".env")
        key = os.environ.get("MEM0_API_KEY", "").strip()
        if not key:
            raise MemoryServiceError("Set MEM0_API_KEY in .env.local or your environment.")

        os.environ.setdefault("MEM0_TELEMETRY", "false")
        os.environ.setdefault("MEM0_DIR", str(root / "data" / "mem0"))
        import httpx
        from mem0 import MemoryClient

        self._http = httpx.Client(timeout=httpx.Timeout(30, connect=10))
        try:
            self._client = MemoryClient(api_key=key, client=self._http)
        except Exception:
            self._http.close()
            raise MemoryServiceError(
                "Could not connect to Mem0. Check MEM0_API_KEY, account access, and network."
            ) from None

    def close(self) -> None:
        if self._http is not None:
            self._http.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def _call(self, method: str, *args, **kwargs):
        try:
            return getattr(self._client, method)(*args, **kwargs)
        except Exception:
            # Do not turn a provider outage into "no memories" or a saved result.
            raise MemoryServiceError(
                f"Mem0 {method} failed. Check credentials, network, and account quota."
            ) from None

    @staticmethod
    def _normalize(response: Any, traveler_id: str) -> list[dict]:
        rows = response.get("results") if isinstance(response, dict) else response
        if not isinstance(rows, list):
            raise MemoryServiceError("Mem0 returned an unexpected memory response.")
        output = []
        for row in rows:
            if not isinstance(row, dict) or not row.get("id"):
                raise MemoryServiceError("Mem0 returned an invalid memory entry.")
            # Add returns data.memory; search/get-all return memory at the top level.
            data = row.get("data")
            memory_text = row.get("memory")
            if memory_text is None and isinstance(data, dict):
                memory_text = data.get("memory")
            if not isinstance(memory_text, str):
                raise MemoryServiceError("Mem0 returned an invalid memory entry.")
            if row.get("user_id") not in (None, traveler_id):
                raise MemoryServiceError("Mem0 returned a memory outside the requested traveler scope.")
            output.append({
                "id": row["id"],
                "traveler_id": traveler_id,
                "memory": memory_text,
                "metadata": row.get("metadata") or {},
                "score": row.get("score"),
                "created_at": row.get("created_at"),
            })
        return output

    def get_memories(self, traveler_id: str, query: str, limit: int = 8) -> list[dict]:
        traveler_id = _text(traveler_id, "traveler_id", 128)
        query = _text(query, "query")
        if type(limit) is not int or not 1 <= limit <= 50:
            raise ValueError("limit must be an integer between 1 and 50.")
        response = self._call("search", query, filters={"user_id": traveler_id}, top_k=limit)
        return self._normalize(response, traveler_id)

    def get_group_memories(self, traveler_ids: list[str], query: str, limit: int = 8) -> dict:
        if not isinstance(traveler_ids, list) or not 1 <= len(traveler_ids) <= 10:
            raise ValueError("Provide between 1 and 10 traveler IDs.")
        ids = list(dict.fromkeys(_text(t, "traveler_id", 128) for t in traveler_ids))
        return {t: self.get_memories(t, query, limit) for t in ids}

    def _save(self, traveler_id: str, text: str, kind: str, *, trip_id: str | None = None,
              expiration_date: str | None = None, group_id: str | None = None) -> dict:
        traveler_id = _text(traveler_id, "traveler_id", 128)
        text = _text(text, "text")
        metadata = {"source": "traveler", "kind": kind,
                    "recorded_at": datetime.now(timezone.utc).isoformat()}
        if trip_id is not None:
            metadata["trip_id"] = _text(trip_id, "trip_id", 128)
        if group_id is not None:
            metadata["group_id"] = _text(group_id, "group_id", 128)
        options = {}
        if expiration_date is not None:
            try:
                parsed = date.fromisoformat(expiration_date)
            except (TypeError, ValueError):
                raise ValueError("expiration_date must be YYYY-MM-DD.") from None
            if parsed.isoformat() != expiration_date:
                raise ValueError("expiration_date must be YYYY-MM-DD.")
            options["expiration_date"] = expiration_date

        # Forms already contain explicit traveler statements. Save verbatim for
        # synchronous writes and faithful feedback; do not store assistant plans.
        response = self._call("add", [{"role": "user", "content": text}],
                              user_id=traveler_id, metadata=metadata, infer=False, **options)
        if not isinstance(response, dict):
            raise MemoryServiceError("Mem0 returned an unexpected save response.")
        status = str(response.get("status", "")).upper()
        if status == "FAILED":
            raise MemoryServiceError("Mem0 could not save this memory.")
        if status == "PENDING":
            return {"status": "pending", "traveler_id": traveler_id,
                    "event_id": response.get("event_id"), "memories": []}
        memories = self._normalize(response, traveler_id)
        if not memories:
            raise MemoryServiceError("Mem0 did not confirm any saved memories.")
        for memory in memories:
            memory["metadata"] = memory["metadata"] or metadata.copy()
        return {"status": "saved", "traveler_id": traveler_id, "memories": memories}

    def save_preferences(self, traveler_id: str, preferences: str) -> dict:
        """Save only traveler-stated enduring preferences, not current trip constraints."""
        return self._save(traveler_id, preferences, "preference")

    def save_feedback(self, traveler_id: str, feedback: str, *, trip_id: str,
                      group_id: str | None = None) -> dict:
        """Record one person's report about a completed outing, attributed to them."""
        return self._save(traveler_id, feedback, "trip_feedback", trip_id=trip_id, group_id=group_id)

    def save_temporary_context(self, traveler_id: str, context: str, *,
                               trip_id: str, expiration_date: str) -> dict:
        """Optional short-lived context; today's mood must not become a permanent trait."""
        return self._save(traveler_id, context, "temporary", trip_id=trip_id,
                          expiration_date=expiration_date)

"""Read-only normalization, provenance, expiration, and text interpretation."""

from datetime import date, datetime, timezone
from typing import Protocol

from .interpretation import completed_place_id, interpret_text
from .models import TAGS


class MemoryProvider(Protocol):
    def getMemories(self, travelerId: str, query: str) -> list:
        """Return memories for this traveler, already normalized from Mem0 results."""
        ...


class EmptyMemoryProvider:
    def getMemories(self, travelerId, query):
        return []


def eligible_at(item, metadata, now, outing):
    if item.get("is_expired") is True or metadata.get("is_expired") is True:
        return False
    for key in ("expiration_date", "expires_at"):
        value = item.get(key, metadata.get(key))
        if value is None:
            continue  # Mem0 also hides native expired records on normal reads.
        if not isinstance(value, str):
            return False
        try:
            if len(value) == 10:
                expires = date.fromisoformat(value)
                if expires < now.date() or expires < outing.date():
                    return False  # Native day-based expiration includes this date.
            else:
                expires = datetime.fromisoformat(value.replace("Z", "+00:00"))
                if expires.tzinfo is None or expires <= now or expires <= outing:
                    return False
        except ValueError:
            return False
    return True


def normalize_memories(raw, traveler_id, *, now=None, outing=None, trip_id=""):
    if not isinstance(raw, list):
        raise ValueError("getMemories must return a list, not the raw Mem0 response.")
    now = now or datetime.now(timezone.utc)
    outing = outing or now
    normalized = []
    for item in raw:
        if not isinstance(item, dict) or item.get("traveler_id") != traveler_id:
            continue
        metadata = item.get("metadata", {})
        if not isinstance(metadata, dict) or metadata.get("source") not in (None, "traveler"):
            continue
        if not eligible_at(item, metadata, now, outing):
            continue
        kind = item.get("kind", metadata.get("kind"))
        status = item.get("status", metadata.get("status"))
        if kind == "trip_feedback":
            # save_feedback is a traveler report about a completed outing.
            # An explicit non-completed status still wins over that contract.
            if not metadata.get("trip_id") or status not in (None, "completed"):
                continue
            kind, status = "feedback", "completed"
        if kind == "temporary":
            if not trip_id or metadata.get("trip_id") != trip_id:
                continue
            if not any(item.get(k, metadata.get(k)) for k in ("expiration_date", "expires_at")):
                continue
        elif kind not in ("preference", "feedback", "experience"):
            continue
        if kind in ("feedback", "experience") and status != "completed":
            continue
        if not isinstance(item.get("id"), str) or not item["id"]:
            continue
        text = item.get("text", item.get("memory", ""))
        if not isinstance(text, str) or not text.strip():
            continue
        signals = item.get("signals", {})
        if not isinstance(signals, dict):
            continue
        interpreted = interpret_text(text)
        safe = {}
        for key in ("liked_tags", "avoided_tags"):
            tags = signals.get(key, [])
            supplied = {t for t in tags if isinstance(t, str) and t in TAGS} if isinstance(tags, list) else set()
            safe[key] = sorted(supplied | set(interpreted[key]))
        for key in ("slower_pace", "short_drives", "requires_vegetarian", "requires_step_free"):
            safe[key] = signals.get(key) is True or interpreted[key]
        place = item.get("place_id", metadata.get("place_id")) if kind == "experience" else None
        if kind == "feedback":
            place = metadata.get("place_id") or completed_place_id(text, metadata)
        safe["visited_place_id"] = place if isinstance(place, str) else None
        safe["low_energy"] = kind == "temporary" and interpreted["low_energy"]
        normalized.append({"id": item["id"], "traveler_id": traveler_id,
                           "text": text, "kind": kind, "status": status,
                           "metadata": dict(metadata), "trip_id": metadata.get("trip_id"),
                           "created_at": item.get("created_at"),
                           "expiration_date": item.get("expiration_date", metadata.get("expiration_date")),
                           "expires_at": item.get("expires_at", metadata.get("expires_at")),
                           "signals": safe})
    return normalized

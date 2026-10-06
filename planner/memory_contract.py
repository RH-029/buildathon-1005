"""Read-only boundary owned by the planner; storage belongs to the memory owner."""

from typing import Protocol
from .models import TAGS


class MemoryProvider(Protocol):
    def getMemories(self, travelerId: str, query: str) -> list:
        """Return memories for this traveler, already normalized from Mem0 results."""
        ...


class EmptyMemoryProvider:
    def getMemories(self, travelerId, query):
        return []


def normalize_memories(raw, traveler_id):
    """Ignore proposed experiences, unsupported signals, and other users' memories.

    Mem0's raw `memory` string is accepted for display, but actionable signals
    must be structured by the memory adapter. No free-text guessing of constraints.
    """
    if not isinstance(raw, list):
        raise ValueError("getMemories must return a list, not the raw Mem0 response.")
    normalized = []
    for item in raw:
        if not isinstance(item, dict) or item.get("traveler_id") != traveler_id:
            continue
        if item.get("kind") not in ("preference", "feedback", "experience"):
            continue
        if item.get("kind") in ("feedback", "experience") and item.get("status") != "completed":
            continue
        if not isinstance(item.get("id"), str) or not item["id"]:
            continue
        text = item.get("text", item.get("memory", ""))
        if not isinstance(text, str) or not text.strip():
            continue
        signals = item.get("signals", {})
        if not isinstance(signals, dict):
            continue
        safe = {}
        for key in ("liked_tags", "avoided_tags"):
            tags = signals.get(key, [])
            safe[key] = sorted({t for t in tags if isinstance(t, str) and t in TAGS}) if isinstance(tags, list) else []
        safe["slower_pace"] = signals.get("slower_pace") is True
        safe["short_drives"] = signals.get("short_drives") is True
        # Only a completed experience can establish a visit, never a proposal.
        safe["visited_place_id"] = item.get("place_id") if item["kind"] == "experience" else None
        if not isinstance(safe["visited_place_id"], str):
            safe["visited_place_id"] = None
        normalized.append({"id": item["id"], "traveler_id": traveler_id,
                           "text": text[:1000], "signals": safe})
    return normalized

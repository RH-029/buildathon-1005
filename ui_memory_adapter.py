"""UI-owned bridge between hosted TravelMemory records and the Planner contract."""

import json

from planner.models import TAGS

SCHEMA = "travelmind.v1"


def signals_from(value):
    """Accept only explicit structured statements; never infer hard constraints."""
    if not isinstance(value, dict):
        raise ValueError("signals must be an object.")
    allowed = {"liked_tags", "avoided_tags", "slower_pace", "short_drives"}
    if set(value) - allowed:
        raise ValueError("Unsupported memory signals.")
    result = {}
    for key in ("liked_tags", "avoided_tags"):
        tags = value.get(key, [])
        if not isinstance(tags, list) or any(not isinstance(tag, str) or tag not in TAGS for tag in tags):
            raise ValueError("Memory interests must use supported planner tags.")
        result[key] = sorted(set(tags))
    if set(result["liked_tags"]) & set(result["avoided_tags"]):
        raise ValueError("The same interest cannot be both liked and avoided.")
    for key in ("slower_pace", "short_drives"):
        flag = value.get(key, False)
        if not isinstance(flag, bool):
            raise ValueError(f"{key} must be true or false.")
        result[key] = flag
    return result


def envelope(kind, text, signals, place_id=None):
    value = {"schema": SCHEMA, "kind": kind, "text": text, "signals": signals_from(signals)}
    if kind == "feedback":
        value.update(status="completed", place_id=place_id)
    return json.dumps(value, ensure_ascii=False)


def decode_record(record):
    """Legacy prose is visible but does not create guessed ranking signals."""
    raw = record["memory"]
    try:
        data = json.loads(raw)
    except (ValueError, TypeError):
        data = None
    metadata = record.get("metadata") or {}
    if not isinstance(metadata, dict):
        metadata = {}
    structured = isinstance(data, dict) and data.get("schema") == SCHEMA
    kind = metadata.get("kind")
    output = {"id": record["id"], "traveler_id": record["traveler_id"],
              "memory": raw, "text": raw, "kind": kind, "signals": {},
              "structured": False, "created_at": record.get("created_at")}
    if structured and metadata.get("source") == "traveler":
        expected = {"preference": "preference", "trip_feedback": "feedback"}.get(kind)
        if data.get("kind") == expected and isinstance(data.get("text"), str) and data["text"].strip():
            try:
                signals = signals_from(data.get("signals", {}))
            except ValueError:
                return output
            output.update(text=data["text"], signals=signals, kind=expected, structured=True)
            if expected == "feedback" and data.get("status") == "completed":
                output["status"] = "completed"
                # A visit requires the user's explicit completion report.
                place = data.get("place_id")
                if isinstance(place, str) and place.strip():
                    output.update(kind="experience", place_id=place)
    # Plain preferences can be shown by Planner, but contain no actionable signals.
    return output


class PlannerMemoryAdapter:
    def __init__(self, memory):
        self.memory = memory
        self.retrieved = {}

    def getMemories(self, travelerId, query):
        rows = [decode_record(row) for row in self.memory.get_memories(travelerId, query)]
        self.retrieved[travelerId] = rows
        return rows

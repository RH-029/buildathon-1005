"""Structured constraints are authoritative; memory never overrides them."""

from dataclasses import dataclass
from datetime import datetime, timedelta
import math
from zoneinfo import ZoneInfo

PACIFIC = ZoneInfo("America/Los_Angeles")
TAGS = {"nature", "scenic", "quiet", "art", "food", "walking", "hiking", "social", "gardens", "photography"}


class ValidationError(ValueError):
    pass


def fields(value, allowed, label):
    if not isinstance(value, dict):
        raise ValidationError(f"{label} must be an object.")
    unknown = set(value) - set(allowed)
    if unknown:
        raise ValidationError(f"Unsupported {label} fields: {', '.join(sorted(unknown))}.")


def number(value, label, minimum=0, maximum=10000):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValidationError(f"{label} must be a number.")
    if not math.isfinite(value) or not minimum <= value <= maximum:
        raise ValidationError(f"{label} must be between {minimum} and {maximum}.")
    return value


def boolean(value, label):
    if not isinstance(value, bool):
        raise ValidationError(f"{label} must be true or false.")
    return value


def string(value, label):
    if not isinstance(value, str) or not value.strip() or len(value) > 200:
        raise ValidationError(f"{label} must be a nonempty string of at most 200 characters.")
    return value.strip()


@dataclass(frozen=True)
class Traveler:
    id: str
    name: str
    interests: tuple
    budget_per_person: float
    max_drive_minutes: int
    max_intensity: int
    requires_step_free: bool
    requires_vegetarian: bool


@dataclass(frozen=True)
class PlanRequest:
    origin: str
    start: datetime
    end: datetime
    budget_per_person: float
    energy: str
    allow_repeats: bool
    travelers: tuple
    transport: str = "car"
    trip_id: str = ""

    @classmethod
    def from_dict(cls, data):
        fields(data, {"origin", "start", "end", "budget_per_person", "energy",
                      "allow_repeats", "travelers", "transport", "trip_id"}, "request")
        origin = string(data.get("origin"), "origin")
        if data.get("transport", "car") != "car":
            raise ValidationError("This catalog supports car transport only.")
        dates = []
        for key in ("start", "end"):
            try:
                date = datetime.fromisoformat(data[key].replace("Z", "+00:00"))
            except (KeyError, ValueError, AttributeError, TypeError):
                raise ValidationError(f"{key} must be an ISO 8601 timestamp with a UTC offset.")
            if date.tzinfo is None:
                raise ValidationError(f"{key} must include a UTC offset.")
            dates.append(date.astimezone(PACIFIC))
        start, end = dates
        if end <= start or end - start > timedelta(hours=24) or start.date() != end.date():
            raise ValidationError("Provide a positive time window within one Pacific calendar day.")
        budget = number(data.get("budget_per_person"), "budget_per_person")
        energy = data.get("energy", "medium")
        if energy not in ("low", "medium", "high"):
            raise ValidationError("energy must be low, medium, or high.")
        raw_travelers = data.get("travelers")
        if not isinstance(raw_travelers, list) or not 1 <= len(raw_travelers) <= 8:
            raise ValidationError("travelers must contain 1 to 8 people.")
        travelers = []
        for raw in raw_travelers:
            fields(raw, {"id", "name", "interests", "budget_per_person", "max_drive_minutes",
                         "max_intensity", "requires_step_free", "requires_vegetarian"}, "traveler")
            interests = raw.get("interests", [])
            if not isinstance(interests, list) or any(not isinstance(t, str) or t not in TAGS for t in interests):
                raise ValidationError(f"interests must be a list drawn from {', '.join(sorted(TAGS))}.")
            intensity = number(raw.get("max_intensity", 3), "max_intensity", 0, 3)
            drive = number(raw.get("max_drive_minutes", 180), "max_drive_minutes", 0, 180)
            if int(intensity) != intensity or int(drive) != drive:
                raise ValidationError("max_intensity and max_drive_minutes must be integers.")
            travelers.append(Traveler(
                string(raw.get("id"), "traveler.id"), string(raw.get("name"), "traveler.name"),
                tuple(sorted(set(interests))),
                number(raw.get("budget_per_person", budget), "traveler.budget_per_person"),
                int(drive), int(intensity),
                boolean(raw.get("requires_step_free", False), "requires_step_free"),
                boolean(raw.get("requires_vegetarian", False), "requires_vegetarian"),
            ))
        if len({t.id for t in travelers}) != len(travelers):
            raise ValidationError("traveler IDs must be unique.")
        trip_id = string(data["trip_id"], "trip_id") if "trip_id" in data else ""
        return cls(origin, start, end, budget, energy,
                   boolean(data.get("allow_repeats", False), "allow_repeats"), tuple(travelers), trip_id=trip_id)

"""Sample estimates by default; optional Google Routes traffic-aware estimates."""

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import math
from urllib.request import Request, urlopen


class TravelUnavailable(RuntimeError):
    pass


@dataclass(frozen=True)
class TravelEstimate:
    minutes: int
    source: str
    data_status: str
    checked_at: str = ""


class SampleTravelProvider:
    def estimate(self, origin, experience, departure, returning=False):
        key = origin.strip().removesuffix(", CA").strip()
        minutes = experience["drive_minutes"].get(key)
        if minutes is None:
            raise TravelUnavailable("Sample travel supports Mountain View, Palo Alto, and Sunnyvale only.")
        return TravelEstimate(minutes, "curated sample (no traffic data)", "sample")


class GoogleRoutesProvider:
    """Failure excludes the candidate; never silently falls back to sample data."""

    def __init__(self, api_key, opener=urlopen):
        self.api_key = api_key
        self.opener = opener

    def estimate(self, origin, experience, departure, returning=False):
        if departure.astimezone(timezone.utc) <= datetime.now(timezone.utc):
            raise TravelUnavailable("Live Routes needs a future departure time.")
        source, destination = origin, experience["destination"]
        if returning:
            source, destination = destination, source
        body = {"origin": {"address": source}, "destination": {"address": destination},
                "travelMode": "DRIVE", "routingPreference": "TRAFFIC_AWARE",
                "departureTime": departure.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")}
        request = Request("https://routes.googleapis.com/directions/v2:computeRoutes",
                          data=json.dumps(body).encode(), method="POST",
                          headers={"Content-Type": "application/json", "X-Goog-Api-Key": self.api_key,
                                   "X-Goog-FieldMask": "routes.duration"})
        try:
            with self.opener(request, timeout=8) as response:
                result = json.load(response)
            duration = result["routes"][0]["duration"]
            if not isinstance(duration, str) or not duration.endswith("s"):
                raise ValueError("Invalid route duration")
            seconds = float(duration[:-1])
            if not math.isfinite(seconds) or seconds <= 0:
                raise ValueError("Invalid route duration")
        except Exception as error:
            # Do not expose provider response bodies or credentials in endpoint errors.
            raise TravelUnavailable("Google Routes could not verify this drive.") from error
        return TravelEstimate(math.ceil(seconds / 60), "Google Routes traffic-aware estimate", "live_estimate",
                              datetime.now(timezone.utc).isoformat())

"""Planner adapter for the published TravelMemory API; storage stays in Mem0."""

from travel_memory import MemoryServiceError, TravelMemory


class PlannerTravelMemory(TravelMemory):
    """Extend normalization and profile reads without editing the owner module."""

    @staticmethod
    def _normalize(response, traveler_id):
        output = TravelMemory._normalize(response, traveler_id)
        rows = response.get("results") if isinstance(response, dict) else response
        original = {row["id"]: row for row in rows}
        for item in output:
            row = original[item["id"]]
            for key in ("expiration_date", "expires_at", "is_expired", "updated_at"):
                if key in row:
                    item[key] = row[key]
        return output

    def get_profile_memories(self, traveler_id):
        # An exhaustive scoped read complements relevance search: a dietary or
        # accessibility requirement must not be missed because of top_k.
        records = []
        seen = set()
        for page in range(1, 101):
            result = self._call("get_all", filters={"user_id": traveler_id}, page=page, page_size=100)
            rows = self._normalize(result, traveler_id)
            if any(row["id"] in seen for row in rows):
                raise MemoryServiceError("Mem0 pagination repeated records; cannot verify a complete profile.")
            records.extend(rows)
            seen.update(row["id"] for row in rows)
            if not isinstance(result, dict) or not result.get("next"):
                return records
        raise MemoryServiceError("Profile exceeds the planner's retrieval limit; no partial constraint check was used.")


class HostedMemoryProvider:
    def __init__(self, service=None):
        self.service = service if service is not None else PlannerTravelMemory()

    def getMemories(self, travelerId, query):
        profiles = self.service.get_profile_memories(travelerId)
        relevant = self.service.get_memories(travelerId, query, limit=50)
        merged = {item["id"]: item for item in profiles}
        # Exhaustive rows retain expiry and metadata. Search establishes order;
        # a search-only concurrent write is picked up by the next profile read.
        order = list(dict.fromkeys(item["id"] for item in relevant if item["id"] in merged))
        order.extend(item["id"] for item in profiles if item["id"] not in order)
        return [merged[identity] for identity in order]

    def close(self):
        self.service.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

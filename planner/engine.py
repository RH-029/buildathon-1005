"""Constraint-first planning with deterministic, author-attributed memory ranking."""

from dataclasses import asdict
from datetime import datetime, timedelta
import json
import math
from pathlib import Path

from .memory_contract import EmptyMemoryProvider, normalize_memories
from .models import PlanRequest
from .travel import SampleTravelProvider, TravelUnavailable


class MemoryUnavailable(RuntimeError):
    pass


class Planner:
    def __init__(self, memory_provider=None, travel_provider=None, catalog=None):
        self.memory = memory_provider if memory_provider is not None else EmptyMemoryProvider()
        self.travel = travel_provider if travel_provider is not None else SampleTravelProvider()
        if catalog is None:
            catalog = json.loads(Path(__file__).with_name("catalog.json").read_text())
        self.catalog = catalog

    def plan(self, request):
        if not isinstance(request, PlanRequest):
            request = PlanRequest.from_dict(request)
        query = (f"Weekend outing from {request.origin}; {request.start.isoformat()} to "
                 f"{request.end.isoformat()}; energy {request.energy}; interests "
                 f"{', '.join(sorted({tag for t in request.travelers for tag in t.interests}))}. "
                 "Retrieve likes, dislikes, pace feedback, drive preferences, and completed visits.")
        memories = {}
        for traveler in request.travelers:
            try:
                memories[traveler.id] = normalize_memories(
                    self.memory.getMemories(traveler.id, query), traveler.id)
            except Exception as error:
                raise MemoryUnavailable("Memory retrieval failed; retry before generating a personalized plan.") from error
        slower = any(m["signals"]["slower_pace"] for entries in memories.values() for m in entries)
        buffer_minutes = 45 if slower else 20
        budget = min(request.budget_per_person, *(t.budget_per_person for t in request.travelers))
        intensity_limit = min({"low": 1, "medium": 2, "high": 3}[request.energy],
                              *(t.max_intensity for t in request.travelers))
        options, excluded = [], []
        for experience in self.catalog["experiences"]:
            reasons = []
            cost = math.ceil((experience["cost_per_person"] +
                              experience["group_cost"] / len(request.travelers)) * 100) / 100
            if cost > budget:
                reasons.append("Exceeds the strictest per-person budget.")
            if experience["intensity"] > intensity_limit:
                reasons.append("Exceeds this outing's energy or a traveler's intensity limit.")
            for traveler in request.travelers:
                if traveler.requires_step_free and experience.get("step_free") is not True:
                    reasons.append(f"Step-free suitability is unavailable for {traveler.name}.")
                if traveler.requires_vegetarian and experience.get("vegetarian") is not True:
                    reasons.append(f"No vegetarian meal plan for {traveler.name}.")
            if request.start.weekday() not in experience["weekdays"]:
                reasons.append("Closed on this day in the sample schedule.")
            if reasons:
                excluded.append({"place_id": experience["id"], "reasons": reasons})
                continue
            try:
                outward = self.travel.estimate(request.origin, experience, request.start)
                arrival = request.start + timedelta(minutes=outward.minutes + 10)
                opening = datetime.combine(request.start.date(),
                                           datetime.strptime(experience["sample_open"], "%H:%M").time(),
                                           request.start.tzinfo)
                closing = datetime.combine(request.start.date(),
                                           datetime.strptime(experience["sample_close"], "%H:%M").time(),
                                           request.start.tzinfo)
                activity_start = max(arrival, opening)
                primary_minutes = experience["activity_minutes"] + (30 if slower else 0)
                primary_end = activity_start + timedelta(minutes=primary_minutes)
                # Slower pace turns two agenda items into one relaxed activity.
                departure = primary_end + timedelta(minutes=0 if slower else experience["extra_minutes"])
                inward = self.travel.estimate(request.origin, experience, departure, returning=True)
            except TravelUnavailable as error:
                excluded.append({"place_id": experience["id"], "reasons": [str(error)]})
                continue
            back = departure + timedelta(minutes=inward.minutes + buffer_minutes)
            if departure > closing or activity_start < opening:
                reasons.append("Activities extend beyond the sample opening window.")
            if back > request.end:
                reasons.append("Cannot return by the deadline with the driving and breathing-room buffers.")
            for traveler in request.travelers:
                if max(outward.minutes, inward.minutes) > traveler.max_drive_minutes:
                    reasons.append(f"Exceeds {traveler.name}'s maximum one-way drive.")
            if reasons:
                excluded.append({"place_id": experience["id"], "reasons": reasons})
                continue
            timeline = [{"label": "Leave home", "start": request.start.isoformat(),
                         "end": (arrival - timedelta(minutes=10)).isoformat()},
                        {"label": "Parking, arrival, and any wait for opening",
                         "start": (arrival - timedelta(minutes=10)).isoformat(), "end": activity_start.isoformat()},
                        {"label": experience["title"] + (" — slow pace, picnic included" if slower else ""),
                         "start": activity_start.isoformat(), "end": primary_end.isoformat()}]
            if not slower:
                timeline.append({"label": experience["extra_title"], "start": primary_end.isoformat(),
                                 "end": departure.isoformat()})
            timeline.extend([
                {"label": "Drive home", "start": departure.isoformat(),
                 "end": (departure + timedelta(minutes=inward.minutes)).isoformat()},
                {"label": "Breathing room / return margin", "start": (departure + timedelta(minutes=inward.minutes)).isoformat(),
                 "end": back.isoformat()}])
            score, why, tradeoffs, balances = self._rank(request, experience, memories, outward, inward)
            if request.energy == "low":
                why.insert(0, {"source": "current_request", "text": "Low energy today: gentle activities only; this is not saved as a permanent preference."})
            options.append({
                "place_id": experience["id"], "title": experience["title"],
                "description": experience["description"], "score": round(score, 3),
                "estimated_cost_per_person": cost, "estimated_group_cost": round(cost * len(request.travelers), 2),
                "estimated_return": back.isoformat(), "return_deadline": request.end.isoformat(),
                "spare_minutes": int((request.end - back).total_seconds() / 60),
                "activity_count": 1 if slower else 2, "buffer_minutes": buffer_minutes,
                "why_this_fits_you": why, "group_tradeoffs": tradeoffs,
                "traveler_preference_scores": balances, "timeline": timeline,
                "constraint_checks": {"budget": True, "return_deadline": True, "energy": True,
                                      "all_traveler_requirements": True, "basis": "sample catalog assumptions"},
                "sources": {"venue": experience["source_url"], "hours": "sample — verify with venue",
                            "accessibility": "sample — verify the specific route",
                            "outbound_travel": asdict(outward), "return_travel": asdict(inward)},
            })
        options.sort(key=lambda item: (-item["score"], item["sources"]["outbound_travel"]["minutes"], item["place_id"]))
        selected = options[:3]
        return {"status": "ok" if len(selected) == 3 else "insufficient_options",
                "options": selected,
                "message": "Three feasible sample outings." if len(selected) == 3 else
                           f"Found {len(selected)} feasible outing(s); hard constraints were kept. See exclusions before changing a constraint.",
                "data_status": "sample_catalog", "warnings": [self.catalog["notice"]],
                "memory_context": [{"traveler_id": t.id, "traveler_name": t.name,
                                    "retrieved_count": len(memories[t.id])} for t in request.travelers],
                "excluded": excluded}

    @staticmethod
    def _rank(request, experience, memories, outward, inward):
        tags = set(experience["tags"])
        why, tradeoffs, balances = [], [], []
        for traveler in request.travelers:
            likes = set(traveler.interests)
            avoids, visited, short = set(), False, False
            if likes & tags:
                why.append({"source": "current_request", "traveler_id": traveler.id,
                            "traveler_name": traveler.name,
                            "text": f"Matches {traveler.name}'s interests: {', '.join(sorted(likes & tags))}."})
            for memory in memories[traveler.id]:
                signal = memory["signals"]
                likes.update(signal["liked_tags"])
                avoids.update(signal["avoided_tags"])
                short = short or signal["short_drives"]
                is_visit = signal["visited_place_id"] == experience["id"]
                visited = visited or is_visit
                relevant = (set(signal["liked_tags"]) & tags or set(signal["avoided_tags"]) & tags or
                            signal["slower_pace"] or signal["short_drives"] or is_visit)
                if relevant:
                    effect = []
                    if set(signal["liked_tags"]) & tags:
                        effect.append("matches remembered interests")
                    if set(signal["avoided_tags"]) & tags:
                        effect.append("lowers this traveler's preference score")
                    if signal["slower_pace"]:
                        effect.append("one relaxed activity and 45 minutes of breathing room")
                    if signal["short_drives"]:
                        effect.append("favors shorter drives")
                    if is_visit:
                        effect.append("repeat allowed" if request.allow_repeats else "completed visit lowers novelty")
                    why.append({"source": "memory", "memory_id": memory["id"],
                                "traveler_id": traveler.id, "traveler_name": traveler.name,
                                "text": memory["text"], "effect": "; ".join(effect)})
            # Each person gets one vote regardless of how many memories they have.
            score = len(likes & tags) / max(len(likes), 1)
            score -= len(avoids & tags) / max(len(avoids), 1)
            if short:
                score -= max(outward.minutes, inward.minutes) / 90
            if visited and not request.allow_repeats:
                score -= 1.5
                tradeoffs.append(f"{traveler.name} already completed this outing; new places rank higher.")
            if avoids & tags:
                tradeoffs.append(f"{traveler.name} dislikes {', '.join(sorted(avoids & tags))}; other travelers' preferences remain separate.")
            if likes and not likes & tags:
                tradeoffs.append(f"This option does not cover {traveler.name}'s interests in {', '.join(sorted(likes))}.")
            if traveler.requires_vegetarian:
                why.append({"source": "constraint", "traveler_id": traveler.id,
                            "text": f"Bring a vegetarian picnic for {traveler.name}; food is included in the sample budget."})
            if traveler.requires_step_free:
                why.append({"source": "constraint", "traveler_id": traveler.id,
                            "text": f"Step-free option for {traveler.name} under the sample catalog; verify the route before travel."})
            balances.append({"traveler_id": traveler.id, "score": round(score, 3)})
        values = [item["score"] for item in balances]
        # Favor group satisfaction while giving extra weight to the least well-served person.
        return sum(values) / len(values) * 0.7 + min(values) * 0.3, why, tradeoffs, balances

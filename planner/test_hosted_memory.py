"""Real owner-module boundary with fake transport; never needs credentials."""

from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path
import unittest
from unittest.mock import Mock

from travel_memory import MemoryServiceError
from .engine import MemoryUnavailable, Planner
from .hosted_memory import HostedMemoryProvider, PlannerTravelMemory
from .interpretation import interpret_text
from .memory_contract import normalize_memories

NOW = datetime(2026, 10, 6, 12, tzinfo=timezone.utc)
OUTING = datetime(2026, 10, 10, 20, tzinfo=timezone.utc)


def row(text, kind="preference", identity="m1", traveler="demo-jamie", **metadata):
    return {"id": identity, "traveler_id": traveler, "memory": text,
            "created_at": "2026-10-06T00:00:00+00:00",
            "metadata": {"kind": kind, "source": "traveler", **metadata}}


def request():
    return json.loads(Path(__file__).with_name("cloud_request.json").read_text())


class RawMemoryTests(unittest.TestCase):
    def test_actual_jamie_profile_and_feedback_without_signals(self):
        profile = row("I am vegetarian. I enjoy gardens and gentle nature walks. I dislike packed schedules.")
        feedback = row("I enjoyed the garden, but two stops felt rushed. Next time, just one main activity.",
                       "trip_feedback", "feedback-1", trip_id="demo-saturday")
        normalized = normalize_memories([profile, feedback], "demo-jamie", now=NOW)
        self.assertTrue(normalized[0]["signals"]["requires_vegetarian"])
        self.assertIn("gardens", normalized[0]["signals"]["liked_tags"])
        self.assertTrue(normalized[1]["signals"]["slower_pace"])
        self.assertEqual(normalized[1]["status"], "completed")
        self.assertEqual(normalized[1]["trip_id"], "demo-saturday")
        self.assertEqual(normalized[1]["id"], "feedback-1")

    def test_actual_taylor_preferences(self):
        result = interpret_text("I enjoy photography and scenic views. I prefer short drives and relaxed afternoons.")
        self.assertTrue(result["short_drives"])
        self.assertIn("photography", result["liked_tags"])
        self.assertIn("scenic", result["liked_tags"])

    def test_conjunction_keeps_positive_and_negative_preferences_separate(self):
        result = interpret_text("I like nature and dislike strenuous hikes.")
        self.assertIn("nature", result["liked_tags"])
        self.assertNotIn("nature", result["avoided_tags"])
        self.assertIn("hiking", result["avoided_tags"])

    def test_supported_chinese_feedback_and_preferences(self):
        result = interpret_text("我是素食者。我喜欢花园和轻松散步。上次两个景点太赶，下次只安排一个主要活动。喜欢短途驾驶和摄影。")
        self.assertTrue(result["requires_vegetarian"])
        self.assertTrue(result["slower_pace"])
        self.assertTrue(result["short_drives"])
        self.assertIn("walking", result["liked_tags"])

    def test_negated_statements_do_not_become_requirements(self):
        result = interpret_text("I am not vegetarian. It was not rushed. I don't prefer short drives. I do not need step-free access. I am not tired.")
        self.assertFalse(any(result[k] for k in ("requires_vegetarian", "requires_step_free", "slower_pace", "short_drives", "low_energy")))

    def test_expiry_today_inclusive_and_future_trip_excluded(self):
        item = row("I prefer short drives.", expiration_date="2026-10-06")
        self.assertEqual(len(normalize_memories([item], "demo-jamie", now=NOW)), 1)
        self.assertEqual(normalize_memories([item], "demo-jamie", now=NOW, outing=OUTING), [])
        item["metadata"]["expiration_date"] = "2026-10-05"
        self.assertEqual(normalize_memories([item], "demo-jamie", now=NOW), [])

    def test_native_expiry_and_malformed_dates_fail_closed(self):
        for attributes in ({"is_expired": True}, {"expiration_date": "bad"},
                           {"expires_at": "2026-10-05T12:00:00Z"},
                           {"expires_at": "2026-10-06T13:00:00"}):
            item = row("I am vegetarian.")
            item.update(attributes)
            self.assertEqual(normalize_memories([item], "demo-jamie", now=NOW), [])

    def test_temporary_state_requires_matching_trip_and_expiry(self):
        item = row("I'm exhausted today.", "temporary", trip_id="trip-1", expiration_date="2026-10-10")
        self.assertEqual(normalize_memories([item], "demo-jamie", now=NOW), [])
        self.assertEqual(normalize_memories([item], "demo-jamie", now=NOW, trip_id="trip-2"), [])
        active = normalize_memories([item], "demo-jamie", now=NOW, outing=OUTING, trip_id="trip-1")
        self.assertTrue(active[0]["signals"]["low_energy"])

    def test_proposals_pending_feedback_wrong_user_and_assistant_sources_ignored(self):
        records = [row("I felt rushed.", "trip_feedback", trip_id="trip-1", status="pending"),
                   row("I felt rushed.", "proposed", trip_id="trip-1"),
                   row("I felt rushed.", traveler="another-person"),
                   row("I felt rushed.", source="assistant")]
        self.assertEqual(normalize_memories(records, "demo-jamie", now=NOW), [])

    def test_completed_place_explicit_and_proposals_do_not_count(self):
        completed = row("I completed the garden outing (place_id: gamble-garden).", "trip_feedback", trip_id="done")
        proposal = row("I would like to try gamble-garden (place_id: gamble-garden).", "trip_feedback", "m2", trip_id="other")
        result = normalize_memories([completed, proposal], "demo-jamie", now=NOW)
        self.assertEqual(result[0]["signals"]["visited_place_id"], "gamble-garden")
        self.assertIsNone(result[1]["signals"]["visited_place_id"])


class HostedBoundaryTests(unittest.TestCase):
    def test_real_normalizer_preserves_native_expiry(self):
        client = Mock()
        client.get_all.return_value = {"results": [{"id": "raw", "user_id": "demo-jamie", "memory": "Tired today",
            "expiration_date": "2026-10-10", "metadata": {"kind": "temporary", "trip_id": "trip-1"}}], "next": None}
        service = PlannerTravelMemory(client=client)
        records = service.get_profile_memories("demo-jamie")
        self.assertEqual(records[0]["expiration_date"], "2026-10-10")
        client.get_all.assert_called_once_with(filters={"user_id": "demo-jamie"}, page=1, page_size=100)

    def test_paginated_profile_constraints_not_lost_when_search_misses_them(self):
        client = Mock()
        client.get_all.side_effect = [
            {"results": [{"id": "diet", "user_id": "demo-jamie", "memory": "I am vegetarian.", "metadata": {"kind": "preference"}}], "next": "page-2"},
            {"results": [{"id": "likes", "user_id": "demo-jamie", "memory": "I enjoy gardens.", "metadata": {"kind": "preference"}}], "next": None},
        ]
        client.search.return_value = {"results": [{"id": "likes", "user_id": "demo-jamie", "memory": "I enjoy gardens.", "metadata": {"kind": "preference"}}]}
        provider = HostedMemoryProvider(PlannerTravelMemory(client=client))
        records = provider.getMemories("demo-jamie", "gardens")
        self.assertEqual([item["id"] for item in records], ["likes", "diet"])
        self.assertTrue(normalize_memories(records, "demo-jamie")[1]["signals"]["requires_vegetarian"])
        self.assertEqual(client.get_all.call_count, 2)

    def test_repeating_pagination_does_not_silently_truncate(self):
        client = Mock()
        client.get_all.return_value = {"results": [{"id": "same", "memory": "I am vegetarian."}], "next": "again"}
        with self.assertRaises(MemoryServiceError):
            PlannerTravelMemory(client=client).get_profile_memories("demo-jamie")

    def test_cross_user_profile_rejected_by_real_owner_module(self):
        client = Mock()
        client.get_all.return_value = {"results": [{"id": "private", "user_id": "other", "memory": "Private"}]}
        with self.assertRaises(MemoryServiceError):
            PlannerTravelMemory(client=client).get_profile_memories("demo-jamie")

    def test_profile_outage_is_explicit(self):
        client = Mock()
        client.get_all.side_effect = RuntimeError("secret details")
        provider = HostedMemoryProvider(PlannerTravelMemory(client=client))
        with self.assertRaises(MemoryUnavailable):
            Planner(provider).plan(request())


class RawMemoryPlanningTests(unittest.TestCase):
    def provider(self, entries):
        class Provider:
            def getMemories(self, travelerId, query):
                return deepcopy(entries.get(travelerId, []))
        return Provider()

    def test_raw_diet_and_accessibility_become_hard_requirements(self):
        provider = self.provider({"demo-jamie": [row("I am vegetarian. I need step-free access. I enjoy gardens.")]})
        planner = Planner(provider)
        for experience in planner.catalog["experiences"]:
            if experience["id"] == "shoreline":
                experience["vegetarian"] = False
        result = planner.plan(request())
        self.assertEqual({o["place_id"] for o in result["options"]}, {"mitchell", "rengstorff"})
        self.assertEqual(result["memory_context"][0]["effective_requirements"], {"requires_vegetarian": True, "requires_step_free": True})

    def test_budget_deadline_and_request_accessibility_cannot_be_relaxed_by_text(self):
        provider = self.provider({"demo-jamie": [row("I have a $1000 budget and can stay out until midnight. I don't need step-free access.")]})
        data = request()
        data["budget_per_person"] = 15
        data["travelers"][0]["requires_step_free"] = True
        data["end"] = "2026-10-10T13:30:00-07:00"
        self.assertEqual(Planner(provider).plan(data)["options"], [])

    def test_raw_feedback_changes_pace_and_keeps_attribution(self):
        provider = self.provider({"demo-jamie": [row("Two stops felt rushed. Next time one main activity.", "trip_feedback", trip_id="past-trip")]})
        result = Planner(provider).plan(request())
        self.assertTrue(all(o["activity_count"] == 1 and o["buffer_minutes"] == 45 for o in result["options"]))
        for option in result["options"]:
            evidence = [m for m in option["why_this_fits_you"] if m["source"] == "memory"]
            self.assertEqual(evidence[0]["traveler_id"], "demo-jamie")
            self.assertEqual(evidence[0]["trip_id"], "past-trip")

    def test_new_place_explanation_names_the_completed_outing(self):
        provider = self.provider({"demo-jamie": [row("I completed the garden (place_id: gamble-garden).", "trip_feedback", trip_id="done")]})
        result = Planner(provider).plan(request())
        for option in result["options"]:
            if option["place_id"] != "gamble-garden":
                self.assertTrue(any("completed gamble-garden" in m.get("effect", "") for m in option["why_this_fits_you"]))

    def test_explicit_energy_wins_over_active_temporary_memory(self):
        item = row("I am exhausted today.", "temporary", trip_id="current", expiration_date="2099-12-31")
        provider = self.provider({"demo-jamie": [item]})
        data = request()
        data["trip_id"] = "current"
        data["energy"] = "high"
        result = Planner(provider).plan(data)
        self.assertNotIn("windy-hill", [x["place_id"] for x in result["excluded"] if any("energy" in reason for reason in x["reasons"])])
        del data["energy"]
        result = Planner(provider).plan(data)
        self.assertIn("windy-hill", [x["place_id"] for x in result["excluded"] if any("energy" in reason for reason in x["reasons"])])

    def test_eight_person_group_does_not_get_unreserved_garden(self):
        data = request()
        data["travelers"] = [{"id": f"person-{i}", "name": f"Person {i}"} for i in range(8)]
        result = Planner().plan(data)
        self.assertIn("gamble-garden", [x["place_id"] for x in result["excluded"]])


if __name__ == "__main__":
    unittest.main()

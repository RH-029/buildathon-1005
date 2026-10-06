"""Meaningful planner, memory-scope, source, validation, and HTTP regression checks."""

from copy import deepcopy
from datetime import datetime, timedelta, timezone
from io import BytesIO
import json
from pathlib import Path
import unittest

from .demo import DemoMemories
from .engine import MemoryUnavailable, Planner
from .models import PlanRequest, ValidationError
from .server import handler_for
from .travel import GoogleRoutesProvider, TravelEstimate, TravelUnavailable


def sample_request():
    return json.loads(Path(__file__).with_name("demo_request.json").read_text())


class PlannerTests(unittest.TestCase):
    def setUp(self):
        self.request = sample_request()
        self.memory = DemoMemories()

    def test_three_feasible_options_with_attributed_explanations(self):
        result = Planner(self.memory).plan(self.request)
        self.assertEqual(result["status"], "ok")
        self.assertEqual(len(result["options"]), 3)
        for option in result["options"]:
            self.assertLessEqual(datetime.fromisoformat(option["estimated_return"]),
                                 datetime.fromisoformat(self.request["end"]))
            self.assertLessEqual(option["estimated_cost_per_person"], 35)
            self.assertLessEqual(option["sources"]["outbound_travel"]["minutes"], 30)
            self.assertEqual(option["sources"]["return_travel"]["data_status"], "sample")
            for item in option["why_this_fits_you"]:
                if item["source"] == "memory":
                    self.assertTrue(item["memory_id"].startswith(item["traveler_id"]))
        self.assertIn("windy-hill", [item["place_id"] for item in result["excluded"]])

    def test_feedback_changes_fresh_session_and_not_original_request(self):
        original = deepcopy(self.request)
        before = Planner(self.memory).plan(self.request)
        place = before["options"][0]["place_id"]
        self.memory.entries["sam"].extend([
            {"id": "sam-visit", "traveler_id": "sam", "kind": "experience", "status": "completed",
             "place_id": place, "text": "I completed this outing."},
            {"id": "sam-pace", "traveler_id": "sam", "kind": "feedback", "status": "completed",
             "text": "It felt rushed.", "signals": {"slower_pace": True}},
        ])
        after = Planner(self.memory).plan(self.request)
        self.assertNotEqual(after["options"][0]["place_id"], place)
        self.assertTrue(all(o["activity_count"] == 1 and o["buffer_minutes"] == 45 for o in after["options"]))
        self.assertEqual(original, self.request)
        for option in after["options"]:
            pace = [m for m in option["why_this_fits_you"] if m.get("memory_id") == "sam-pace"]
            self.assertEqual(pace[0]["traveler_id"], "sam")

    def test_hard_accessibility_constraint_beats_preferences_and_price(self):
        self.request["travelers"][1]["requires_step_free"] = True
        result = Planner(self.memory).plan(self.request)
        self.assertEqual({o["place_id"] for o in result["options"]}, {"shoreline", "rengstorff", "mitchell"})
        self.assertTrue(any("Step-free" in reason for item in result["excluded"] for reason in item["reasons"]))

    def test_strictest_personal_budget_applies_to_all(self):
        self.request["travelers"][1]["budget_per_person"] = 15
        result = Planner(self.memory).plan(self.request)
        self.assertEqual(result["status"], "insufficient_options")
        self.assertEqual(len(result["options"]), 2)
        self.assertTrue(all(o["estimated_cost_per_person"] <= 15 for o in result["options"]))

    def test_vegetarian_is_a_hard_filter(self):
        planner = Planner(self.memory)
        for experience in planner.catalog["experiences"]:
            experience["vegetarian"] = False
        self.assertEqual(planner.plan(self.request)["options"], [])

    def test_impossible_deadline_does_not_relax_constraints(self):
        self.request["end"] = "2026-10-10T13:30:00-07:00"
        result = Planner(self.memory).plan(self.request)
        self.assertEqual(result["status"], "insufficient_options")
        self.assertEqual(result["options"], [])

    def test_return_drive_checked_separately(self):
        class AsymmetricTravel:
            def estimate(self, origin, experience, departure, returning=False):
                return TravelEstimate(40 if returning else 5, "test", "sample")
        result = Planner(self.memory, AsymmetricTravel()).plan(self.request)
        self.assertEqual(result["options"], [])
        self.assertTrue(any("maximum one-way" in reason for item in result["excluded"] for reason in item["reasons"]))

    def test_unknown_origin_does_not_invent_travel(self):
        self.request["origin"] = "San Francisco"
        result = Planner(self.memory).plan(self.request)
        self.assertEqual(result["options"], [])
        self.assertTrue(any("Sample travel supports" in reason for item in result["excluded"] for reason in item["reasons"]))

    def test_no_activities_after_sample_closing(self):
        self.request["start"] = "2026-10-10T16:45:00-07:00"
        self.assertEqual(Planner(self.memory).plan(self.request)["options"], [])

    def test_proposals_cross_user_and_temporary_memories_do_not_affect_ranking(self):
        before = Planner(self.memory).plan(self.request)
        self.memory.entries["sam"].extend([
            {"id": "wrong-author", "traveler_id": "alex", "kind": "preference",
             "text": "Wrong scope", "signals": {"avoided_tags": ["nature"]}},
            {"id": "proposal", "traveler_id": "sam", "kind": "experience", "status": "proposed",
             "place_id": before["options"][0]["place_id"], "text": "Suggested only."},
            {"id": "temporary", "traveler_id": "sam", "kind": "temporary",
             "text": "Tired last week.", "signals": {"slower_pace": True}},
        ])
        self.assertEqual(Planner(self.memory).plan(self.request), before)

    def test_negative_feedback_keeps_author(self):
        self.memory.entries["sam"].append({"id": "sam-dislike", "traveler_id": "sam", "kind": "feedback",
                                           "status": "completed", "text": "I dislike quiet outings.",
                                           "signals": {"avoided_tags": ["quiet"]}})
        option = Planner(self.memory).plan(self.request)["options"][0]
        self.assertTrue(any("Sam dislikes" in text for text in option["group_tradeoffs"]))
        self.assertFalse(any("Alex dislikes" in text for text in option["group_tradeoffs"]))

    def test_repeat_opt_in_removes_novelty_penalty(self):
        planner = Planner(self.memory)
        top = planner.plan(self.request)["options"][0]["place_id"]
        self.memory.entries["sam"].append({"id": "sam-repeat", "traveler_id": "sam", "kind": "experience",
                                           "status": "completed", "place_id": top, "text": "Visited."})
        self.request["allow_repeats"] = True
        self.assertEqual(Planner(self.memory).plan(self.request)["options"][0]["place_id"], top)

    def test_duplicate_memories_do_not_multiply_one_person_vote(self):
        before = Planner(self.memory).plan(self.request)
        self.memory.entries["sam"] *= 10
        after = Planner(self.memory).plan(self.request)
        self.assertEqual([o["score"] for o in before["options"]], [o["score"] for o in after["options"]])

    def test_memory_failure_is_explicit(self):
        class BrokenMemory:
            def getMemories(self, travelerId, query):
                raise RuntimeError("private provider detail")
        with self.assertRaises(MemoryUnavailable):
            Planner(BrokenMemory()).plan(self.request)

    def test_energy_is_request_scoped(self):
        before = deepcopy(self.memory.entries)
        Planner(self.memory).plan(self.request)
        self.assertEqual(before, self.memory.entries)
        self.request["energy"] = "high"
        self.request["travelers"][1]["max_drive_minutes"] = 90
        result = Planner(self.memory).plan(self.request)
        self.assertNotIn("windy-hill", [item["place_id"] for item in result["excluded"]])


class ValidationTests(unittest.TestCase):
    def test_invalid_input_cases(self):
        cases = [("budget_per_person", float("nan")), ("budget_per_person", -1),
                 ("budget_per_person", True), ("energy", "exhausted"), ("transport", "train"),
                 ("allow_repeats", "false"), ("travelers", []), ("start", "2026-10-10T13:00:00"),
                 ("end", "2026-10-09T19:00:00-07:00"), ("end", "2026-10-11T19:00:00-07:00")]
        for key, value in cases:
            with self.subTest(key=key, value=value):
                request = sample_request()
                request[key] = value
                with self.assertRaises(ValidationError):
                    PlanRequest.from_dict(request)

    def test_unknown_constraint_is_rejected_instead_of_ignored(self):
        request = sample_request()
        request["travelers"][0]["requires_dog_access"] = True
        with self.assertRaises(ValidationError):
            PlanRequest.from_dict(request)

    def test_malformed_travelers(self):
        for key, value in [("id", ""), ("id", "alex"), ("max_drive_minutes", 2.5),
                           ("requires_step_free", "false"), ("interests", ["unknown"]),
                           ("max_intensity", float("inf"))]:
            with self.subTest(key=key):
                request = sample_request()
                request["travelers"][0][key] = value
                with self.assertRaises(ValidationError):
                    PlanRequest.from_dict(request)


class GoogleRoutesTests(unittest.TestCase):
    def test_live_request_has_correct_direction_departure_and_field_mask(self):
        calls = []
        def opener(request, timeout):
            calls.append(request)
            return BytesIO(b'{"routes":[{"duration":"1200.1s"}]}')
        provider = GoogleRoutesProvider("test-key", opener)
        future = datetime.now(timezone.utc) + timedelta(days=1)
        experience = {"destination": "Shoreline Lake"}
        outward = provider.estimate("Mountain View", experience, future)
        inward = provider.estimate("Mountain View", experience, future, returning=True)
        self.assertEqual(outward.minutes, 21)
        self.assertEqual(inward.data_status, "live_estimate")
        self.assertTrue(inward.checked_at)
        body = json.loads(calls[1].data)
        self.assertEqual(body["origin"]["address"], "Shoreline Lake")
        self.assertEqual(body["destination"]["address"], "Mountain View")
        self.assertEqual(body["routingPreference"], "TRAFFIC_AWARE")
        self.assertEqual(calls[0].get_header("X-goog-fieldmask"), "routes.duration")

    def test_live_failure_never_falls_back_or_leaks_provider_details(self):
        def opener(request, timeout):
            raise RuntimeError("secret provider error")
        provider = GoogleRoutesProvider("test-key", opener)
        with self.assertRaisesRegex(TravelUnavailable, "could not verify"):
            provider.estimate("Mountain View", {"destination": "Shoreline"}, datetime.now(timezone.utc) + timedelta(days=1))

    def test_invalid_provider_duration_rejected(self):
        for duration in ("NaNs", "-1s", "bad", "0s"):
            with self.subTest(duration=duration):
                def opener(request, timeout):
                    return BytesIO(json.dumps({"routes": [{"duration": duration}]}).encode())
                with self.assertRaises(TravelUnavailable):
                    GoogleRoutesProvider("test", opener).estimate("Mountain View", {"destination": "Shoreline"},
                                                                 datetime.now(timezone.utc) + timedelta(days=1))


class HTTPTests(unittest.TestCase):
    """Exercise real HTTP parsing/serialization through in-memory socket streams."""

    def exchange(self, method, path, body=b"", content_type="application/json", planner=None, origin=None):
        class Socket:
            def makefile(self, *args, **kwargs):
                return self.input
            def sendall(self, data):
                self.output.write(data)
        socket = Socket()
        extra = f"Origin: {origin}\r\n" if origin else ""
        head = (f"{method} {path} HTTP/1.0\r\nContent-Type: {content_type}\r\n"
                f"Content-Length: {len(body)}\r\n{extra}\r\n")
        socket.input, socket.output = BytesIO(head.encode() + body), BytesIO()
        handler_for(planner or Planner(DemoMemories()), "http://localhost:3000")(socket, ("127.0.0.1", 1234), None)
        headers, response = socket.output.getvalue().split(b"\r\n\r\n", 1)
        return headers.decode(), json.loads(response)

    def test_plan_endpoint_and_cors(self):
        headers, body = self.exchange("POST", "/api/plan", json.dumps(sample_request()).encode(), origin="http://localhost:3000")
        self.assertIn("200 OK", headers)
        self.assertIn("Access-Control-Allow-Origin: http://localhost:3000", headers)
        self.assertEqual(len(body["options"]), 3)

    def test_errors_and_health(self):
        for method, path, payload, content_type, status in [
            ("POST", "/api/plan", b"bad json", "application/json", "400"),
            ("POST", "/api/plan", b"[]", "application/json", "400"),
            ("POST", "/api/plan", b"{}", "text/plain", "415"),
            ("POST", "/api/plan", b"x" * 65537, "application/json", "413"),
            ("GET", "/wrong", b"", "application/json", "404"),
            ("GET", "/health", b"", "application/json", "200")]:
            with self.subTest(status=status):
                headers, _ = self.exchange(method, path, payload, content_type)
                self.assertIn(status, headers.splitlines()[0])

    def test_memory_failure_returns_503(self):
        class BrokenMemory:
            def getMemories(self, travelerId, query):
                raise RuntimeError("private failure")
        headers, body = self.exchange("POST", "/api/plan", json.dumps(sample_request()).encode(), planner=Planner(BrokenMemory()))
        self.assertIn("503", headers)
        self.assertNotIn("private failure", json.dumps(body))


if __name__ == "__main__":
    unittest.main()

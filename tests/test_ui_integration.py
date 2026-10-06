"""Integration checks use real Planner/TravelMemory code with an offline SDK port."""

from http.server import ThreadingHTTPServer
import json
from pathlib import Path
import threading
import unittest
from unittest.mock import Mock
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from travel_memory import TravelMemory
from ui_memory_adapter import decode_record, envelope
from ui_server import UIService, handler_for


class UIIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.sdk = Mock()
        self.sdk.search.return_value = {"results": []}
        self.sdk.add.return_value = {"results": [{"id": "saved-id", "memory": "Stored statement"}]}
        self.memory = TravelMemory(client=self.sdk)
        self.service = UIService(memory=self.memory)
        self.request = json.loads(Path("planner/demo_request.json").read_text())

    def record(self, traveler="sam", kind="preference", signals=None, place=None):
        return {"id": "memory-id", "traveler_id": traveler,
                "memory": envelope("feedback" if kind == "trip_feedback" else kind,
                                   "My stated preferences", signals or {}, place),
                "metadata": {"kind": kind, "source": "traveler"}}

    def test_structured_memory_changes_real_planner_and_keeps_attribution(self):
        record = self.record(signals={"slower_pace": True, "liked_tags": ["nature"]})
        self.sdk.search.side_effect = [{"results": [record]}, {"results": []}]
        result = self.service.dispatch("/api/plan", self.request)
        self.assertEqual(result["status"], "ok")
        self.assertTrue(all(option["activity_count"] == 1 for option in result["options"]))
        self.assertTrue(all(option["buffer_minutes"] == 45 for option in result["options"]))
        self.assertEqual(result["retrieved_memories"]["alex"], [])
        reason = next(item for item in result["options"][0]["why_this_fits_you"] if item["source"] == "memory")
        self.assertEqual((reason["traveler_id"], reason["memory_id"]), ("sam", "memory-id"))
        self.assertEqual(self.sdk.search.call_args_list[0].kwargs["filters"], {"user_id": "sam"})
        self.assertEqual(self.sdk.search.call_args_list[1].kwargs["filters"], {"user_id": "alex"})

    def test_completed_feedback_is_persisted_through_memory_and_becomes_a_visit(self):
        data = {"traveler_id": "sam", "text": "I enjoyed the walk.", "place_id": "shoreline",
                "trip_id": "trip-1", "completed": True,
                "signals": {"liked_tags": ["nature"], "short_drives": True}}
        self.assertEqual(self.service.dispatch("/api/feedback", data)["status"], "saved")
        args, kwargs = self.sdk.add.call_args
        self.assertEqual(kwargs["user_id"], "sam")
        self.assertFalse(kwargs["infer"])
        record = {"id": "feedback", "traveler_id": "sam", "memory": args[0][0]["content"], "metadata": kwargs["metadata"]}
        decoded = decode_record(record)
        self.assertEqual(decoded["kind"], "experience")
        self.assertEqual(decoded["place_id"], "shoreline")
        self.assertEqual(decoded["status"], "completed")
        self.assertTrue(decoded["signals"]["short_drives"])

    def test_unconfirmed_completion_and_conflicting_tags_never_write(self):
        with self.assertRaises(ValueError):
            self.service.dispatch("/api/feedback", {"completed": False})
        with self.assertRaises(ValueError):
            self.service.dispatch("/api/preferences", {"traveler_id": "sam", "text": "Nature",
                "signals": {"liked_tags": ["nature"], "avoided_tags": ["nature"]}})
        self.sdk.add.assert_not_called()

    def test_legacy_feedback_is_displayed_without_inventing_a_completed_visit(self):
        record = {"id": "old", "traveler_id": "sam", "memory": "The last outing felt rushed.",
                  "metadata": {"source": "traveler", "kind": "trip_feedback"}}
        decoded = decode_record(record)
        self.assertFalse(decoded["structured"])
        self.assertEqual(decoded["text"], record["memory"])
        self.assertNotIn("status", decoded)
        self.assertEqual(decoded["signals"], {})

    def test_pending_write_is_not_reported_saved(self):
        self.sdk.add.return_value = {"status": "PENDING", "event_id": "queued"}
        result = self.service.dispatch("/api/preferences", {"traveler_id": "sam", "text": "I enjoy walking.", "signals": {"liked_tags": ["walking"]}})
        self.assertEqual(result["status"], "pending")

    def test_insufficient_options_are_not_padded(self):
        self.request["budget_per_person"] = 0
        result = self.service.dispatch("/api/plan", self.request)
        self.assertEqual(result["status"], "insufficient_options")
        self.assertEqual(result["options"], [])
        self.assertTrue(result["excluded"])

    def test_http_errors_and_static_root(self):
        server = ThreadingHTTPServer(("127.0.0.1", 0), handler_for(self.service))
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        base = f"http://127.0.0.1:{server.server_port}"
        def call(path, body=None, origin=None):
            headers = {"Content-Type": "application/json"}
            if origin:
                headers["Origin"] = origin
            request = Request(base + path, data=json.dumps(body).encode() if body is not None else None, headers=headers)
            try:
                with urlopen(request) as response:
                    return response.status, response.read()
            except HTTPError as error:
                return error.code, error.read()
        try:
            self.assertEqual(call("/")[0], 200)
            self.assertEqual(call("/.env")[0], 404)
            self.assertEqual(call("/api/plan", self.request, "https://foreign.example")[0], 403)
            self.assertEqual(call("/api/plan", {"origin": "Nowhere"})[0], 400)
            self.sdk.search.side_effect = RuntimeError("private-provider-response")
            code, body = call("/api/plan", self.request)
            self.assertEqual(code, 503)
            self.assertNotIn(b"private-provider-response", body)
        finally:
            server.shutdown(); server.server_close(); worker.join()


if __name__ == "__main__":
    unittest.main()

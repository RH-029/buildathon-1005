"""Offline contract tests: no credentials, SDK imports, or network required."""
import unittest
from unittest.mock import Mock

from travel_memory import MemoryServiceError, TravelMemory


class TravelMemoryTests(unittest.TestCase):
    def setUp(self):
        self.client = Mock()
        self.service = TravelMemory(client=self.client)
        self.client.add.return_value = {"results": [{"id": "m1", "memory": "One stop next time."}]}

    def test_search_is_scoped_to_one_traveler(self):
        self.client.search.return_value = {"results": [{"id": "m1", "memory": "Vegetarian"}]}
        result = self.service.get_memories("jamie", "food")
        self.client.search.assert_called_once_with("food", filters={"user_id": "jamie"}, top_k=8)
        self.assertEqual(result[0]["traveler_id"], "jamie")

    def test_foreign_user_is_rejected(self):
        self.client.search.return_value = {"results": [
            {"id": "m1", "memory": "Private preference", "user_id": "someone-else"}]}
        with self.assertRaises(MemoryServiceError):
            self.service.get_memories("jamie", "preferences")

    def test_group_keeps_authorship_and_deduplicates_users(self):
        self.client.search.side_effect = [
            {"results": [{"id": "m1", "memory": "Vegetarian"}]},
            {"results": [{"id": "m2", "memory": "Short drives"}]},
        ]
        result = self.service.get_group_memories(["jamie", "taylor", "jamie"], "plan")
        self.assertEqual(list(result), ["jamie", "taylor"])
        self.assertEqual(result["taylor"][0]["traveler_id"], "taylor")
        self.assertEqual(self.client.search.call_count, 2)

    def test_feedback_is_verbatim_and_attributed_not_group_wide(self):
        result = self.service.save_feedback("jamie", "One stop next time.", trip_id="trip-1", group_id="friends")
        args, kwargs = self.client.add.call_args
        self.assertEqual(args[0], [{"role": "user", "content": "One stop next time."}])
        self.assertEqual(kwargs["user_id"], "jamie")
        self.assertFalse(kwargs["infer"])
        self.assertEqual(kwargs["metadata"]["trip_id"], "trip-1")
        self.assertEqual(kwargs["metadata"]["kind"], "trip_feedback")
        self.assertEqual(result["status"], "saved")

    def test_temporary_context_expires(self):
        self.service.save_temporary_context("jamie", "Tired today", trip_id="trip-1", expiration_date="2026-10-10")
        self.assertEqual(self.client.add.call_args.kwargs["expiration_date"], "2026-10-10")
        self.assertEqual(self.client.add.call_args.kwargs["metadata"]["kind"], "temporary")

    def test_live_add_response_uses_nested_data(self):
        self.client.add.return_value = {
            "status": "SUCCEEDED", "event_id": "event-1",
            "results": [{"id": "m1", "data": {"memory": "One stop next time."}, "event": "ADD"}],
        }
        result = self.service.save_feedback("jamie", "One stop next time.", trip_id="trip-1")
        self.assertEqual(result["status"], "saved")
        self.assertEqual(result["memories"][0]["memory"], "One stop next time.")
        self.assertEqual(result["memories"][0]["metadata"]["trip_id"], "trip-1")

    def test_invalid_input_does_not_reach_provider(self):
        for action in [
            lambda: self.service.get_memories("", "query"),
            lambda: self.service.get_memories("jamie", "query", limit=True),
            lambda: self.service.save_feedback("jamie", "   ", trip_id="trip-1"),
            lambda: self.service.get_group_memories([], "query"),
            lambda: self.service.save_temporary_context("jamie", "Tired", trip_id="trip-1", expiration_date="tomorrow"),
        ]:
            with self.assertRaises(ValueError):
                action()
        self.client.add.assert_not_called()
        self.client.search.assert_not_called()

    def test_outage_is_not_an_empty_memory_result_and_does_not_leak_provider_error(self):
        self.client.search.side_effect = RuntimeError("sensitive provider response")
        with self.assertRaises(MemoryServiceError) as caught:
            self.service.get_memories("jamie", "query")
        self.assertNotIn("sensitive", str(caught.exception))

    def test_pending_is_not_saved(self):
        self.client.add.return_value = {"status": "PENDING", "event_id": "event-1"}
        result = self.service.save_preferences("jamie", "Vegetarian")
        self.assertEqual(result["status"], "pending")
        self.assertEqual(result["event_id"], "event-1")

    def test_failed_and_malformed_writes_are_not_saved(self):
        for response in [{"status": "FAILED"}, {"results": []}, {"message": "unknown"}]:
            self.client.add.return_value = response
            with self.assertRaises(MemoryServiceError):
                self.service.save_preferences("jamie", "Vegetarian")

    def test_empty_search_is_valid_but_malformed_search_is_not(self):
        self.client.search.return_value = {"results": []}
        self.assertEqual(self.service.get_memories("new-traveler", "plan"), [])
        self.client.search.return_value = {"unexpected": []}
        with self.assertRaises(MemoryServiceError):
            self.service.get_memories("jamie", "plan")


if __name__ == "__main__":
    unittest.main()

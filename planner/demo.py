"""Three-minute demo via a read-only fake memory port, with no keys or writes."""

from copy import deepcopy
import json
from pathlib import Path

from .engine import Planner


class DemoMemories:
    """Planner test fixture, not a replacement for the memory owner's persistence."""

    def __init__(self):
        self.entries = {
            "sam": [{"id": "sam-nature", "traveler_id": "sam", "kind": "preference",
                     "text": "I enjoy nature, but dislike strenuous hikes.",
                     "signals": {"liked_tags": ["nature", "scenic"], "avoided_tags": ["hiking"]}}],
            "alex": [{"id": "alex-drive", "traveler_id": "alex", "kind": "preference",
                      "text": "I like time with friends and prefer short drives.",
                      "signals": {"liked_tags": ["social"], "short_drives": True}}],
        }

    def getMemories(self, travelerId, query):
        return deepcopy(self.entries.get(travelerId, []))


def main():
    request = json.loads(Path(__file__).with_name("demo_request.json").read_text())
    memory_port = DemoMemories()
    before = Planner(memory_provider=memory_port).plan(request)
    print("SAMPLE DEMO — same request, fresh planner sessions, no persistent memory writes")
    print("Before feedback:")
    for option in before["options"]:
        print(f"  {option['title']}: {option['activity_count']} agenda items; {option['buffer_minutes']} min margin")
        for explanation in option["why_this_fits_you"]:
            if explanation["source"] == "memory":
                print(f"    {explanation['traveler_name']}: {explanation['text']} → {explanation['effect']}")
        for tradeoff in option["group_tradeoffs"]:
            print(f"    Tradeoff: {tradeoff}")
    visited = before["options"][0]["place_id"]
    # Simulates what the memory owner's saveFeedback/retrieval pipeline returns
    # AFTER the traveler confirms the outing was completed, not when proposed.
    memory_port.entries["sam"].extend([
        {"id": "sam-completed", "traveler_id": "sam", "kind": "experience", "status": "completed",
         "place_id": visited, "text": "We completed this outing last Saturday."},
        {"id": "sam-rushed", "traveler_id": "sam", "kind": "feedback", "status": "completed",
         "text": "The outing felt rushed. Next time I want fewer agenda items and more breathing room.",
         "signals": {"slower_pace": True}},
    ])
    after = Planner(memory_provider=memory_port).plan(request)  # Fresh session, same request.
    print("\nAfter Sam's feedback (Alex's preferences stay attributed to Alex):")
    for option in after["options"]:
        print(f"  {option['title']}: {option['activity_count']} agenda item; {option['buffer_minutes']} min margin")
        for explanation in option["why_this_fits_you"]:
            if explanation["source"] == "memory":
                print(f"    {explanation['traveler_name']}: {explanation['text']} → {explanation['effect']}")
    assert len(before["options"]) == len(after["options"]) == 3
    assert before["options"][0]["place_id"] != after["options"][0]["place_id"]
    assert all(option["activity_count"] == 1 and option["buffer_minutes"] == 45 for option in after["options"])
    print("\nPASS: completed visit changes the top pick; pace feedback changes every itinerary in a fresh session.")


if __name__ == "__main__":
    main()

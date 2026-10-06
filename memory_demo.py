"""Small CLI for the hosted API. Each invocation creates a fresh client."""

import argparse
import json

from travel_memory import MemoryServiceError, TravelMemory


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("check", help="Check authentication without writing memories")
    seed = commands.add_parser("seed", help="Write fictional demo traveler preferences")
    seed.add_argument("--prefix", default="demo")
    search = commands.add_parser("search")
    search.add_argument("traveler_id")
    search.add_argument("query")
    preferences = commands.add_parser("preferences")
    preferences.add_argument("traveler_id")
    preferences.add_argument("text")
    feedback = commands.add_parser("feedback")
    feedback.add_argument("traveler_id")
    feedback.add_argument("trip_id")
    feedback.add_argument("text")
    group = commands.add_parser("group")
    group.add_argument("query")
    group.add_argument("traveler_ids", nargs="+")
    args = parser.parse_args()
    try:
        with TravelMemory() as memory:
            if args.command == "check":
                result = {"status": "connected", "provider": "Mem0 hosted API"}
            elif args.command == "seed":
                result = {
                    "jamie": memory.save_preferences(f"{args.prefix}-jamie",
                        "I am vegetarian. I enjoy gardens and gentle nature walks. I dislike packed schedules."),
                    "taylor": memory.save_preferences(f"{args.prefix}-taylor",
                        "I enjoy photography and scenic views. I prefer short drives and relaxed afternoons."),
                }
            elif args.command == "search":
                result = memory.get_memories(args.traveler_id, args.query)
            elif args.command == "preferences":
                result = memory.save_preferences(args.traveler_id, args.text)
            elif args.command == "feedback":
                result = memory.save_feedback(args.traveler_id, args.text, trip_id=args.trip_id)
            else:
                result = memory.get_group_memories(args.traveler_ids, args.query)
        print(json.dumps(result, indent=2, ensure_ascii=False))
    except (MemoryServiceError, ValueError) as error:
        parser.exit(1, f"Memory error: {error}\n")


if __name__ == "__main__":
    main()

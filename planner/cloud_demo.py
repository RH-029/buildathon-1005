"""Real hosted loop for fictional demo-jamie/demo-taylor in fresh processes.

Running this command writes one fictional completed-outing feedback record to
demo-jamie. It does not reseed profiles or write to any real traveler's history.
"""

import argparse
from datetime import datetime, timedelta
import json
from pathlib import Path
import subprocess
import sys
import time
from uuid import uuid4

from .engine import Planner
from .hosted_memory import HostedMemoryProvider
from .models import PACIFIC

ROOT = Path(__file__).resolve().parent.parent


def fresh_plan(request_path):
    process = subprocess.run([sys.executable, "-m", "planner.cloud_demo", "--snapshot",
                              "--request", str(request_path)], cwd=ROOT,
                             capture_output=True, text=True, timeout=180)
    if process.returncode:
        raise RuntimeError("Fresh hosted planning session failed; check network and Mem0 quota.")
    return json.loads(process.stdout)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--request", type=Path, default=Path(__file__).with_name("cloud_request.json"))
    args = parser.parse_args()
    request = json.loads(args.request.read_text())
    if args.snapshot:
        with HostedMemoryProvider() as memory:
            print(json.dumps(Planner(memory_provider=memory).plan(request), ensure_ascii=False))
        return
    if {t["id"] for t in request["travelers"]} != {"demo-jamie", "demo-taylor"}:
        raise ValueError("This write demo is restricted to demo-jamie and demo-taylor.")
    data_dir = ROOT / "data"
    data_dir.mkdir(exist_ok=True)
    # Refresh a stale fixture's date; every session in this run uses identical input.
    now = datetime.now(PACIFIC)
    saturday = now.date() + timedelta(days=(5 - now.weekday()) % 7 or 7)
    request["start"] = datetime.combine(saturday, datetime.strptime("13:00", "%H:%M").time(), PACIFIC).isoformat()
    request["end"] = datetime.combine(saturday, datetime.strptime("19:00", "%H:%M").time(), PACIFIC).isoformat()
    request_path = data_dir / "planner-cloud-request.json"
    request_path.write_text(json.dumps(request, indent=2))
    print("FICTIONAL CLOUD DEMO: reuse existing profiles; one Jamie feedback write.", flush=True)
    before = fresh_plan(request_path)
    if len(before["options"]) != 3:
        raise RuntimeError("Baseline needs three feasible options; no feedback was written.")
    top = before["options"][0]
    print(f"Before: {top['title']} ({top['activity_count']} main activity; {top['buffer_minutes']} min margin)", flush=True)
    trip_id = "planner-rehearsal-" + uuid4().hex[:12]
    feedback = (f"Fictional hackathon rehearsal: I completed the {top['title']} outing "
                f"(place_id: {top['place_id']}). I enjoyed the scenery, but two stops felt rushed. "
                "Next time, just one main activity and more breathing room. I want a different place next time.")
    with HostedMemoryProvider() as memory:
        saved = memory.service.save_feedback("demo-jamie", feedback, trip_id=trip_id,
                                             group_id="planner-fictional-demo")
    print(f"Feedback: {saved['status']} (Jamie only; trip {trip_id})", flush=True)
    # Write an audit snapshot immediately: reruns can inspect whether the write
    # already happened, including pending status. This is not a memory database.
    report = {"fictional_demo": True, "request": request, "trip_id": trip_id,
              "feedback": saved, "before": before}
    report_path = data_dir / "planner-cloud-demo.json"
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False))
    deadline = time.monotonic() + 120
    after = None
    while time.monotonic() < deadline:
        candidate = fresh_plan(request_path)
        used = [m for option in candidate["options"] for m in option["why_this_fits_you"]
                if m.get("trip_id") == trip_id and m.get("traveler_id") == "demo-jamie"]
        if used:
            after = candidate
            break
        print("Memory is processing or not yet searchable; waiting before a new read.", flush=True)
        time.sleep(5)
    if after is None:
        raise RuntimeError("Feedback was submitted but not retrieved within two minutes; audit saved. No duplicate write was made.")
    checks = {
        "new_top_pick": after["options"][0]["place_id"] != top["place_id"],
        "three_options": len(after["options"]) == 3,
        "slower_pace": all(o["activity_count"] == 1 and o["buffer_minutes"] == 45 for o in after["options"]),
        "jamie_vegetarian_from_memory": next(t for t in after["memory_context"] if t["traveler_id"] == "demo-jamie")["effective_requirements"]["requires_vegetarian"],
        "feedback_attributed_to_jamie": bool(used) and all(m["traveler_id"] == "demo-jamie" for m in used),
        "feedback_not_taylor": not any(m.get("trip_id") == trip_id and m.get("traveler_id") == "demo-taylor"
                                      for o in after["options"] for m in o["why_this_fits_you"]),
        "budget_and_deadline": all(o["estimated_cost_per_person"] <= request["budget_per_person"] and
                                   datetime.fromisoformat(o["estimated_return"]) <= datetime.fromisoformat(request["end"])
                                   for o in after["options"]),
    }
    report.update(after=after, checks=checks)
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False))
    print(f"After fresh process: {after['options'][0]['title']}", flush=True)
    for item in used[:1]:
        print(f"Jamie memory {item['memory_id']}: {item['effect']}", flush=True)
    print(json.dumps(checks, indent=2), flush=True)
    if not all(checks.values()):
        raise RuntimeError("Cloud loop finished but a demo assertion failed; see the audit.")
    print(f"PASS: real Mem0 feedback changed a fresh-process plan. Audit: {report_path}", flush=True)


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        from travel_memory import MemoryServiceError
        if isinstance(error, (MemoryServiceError, ValueError, RuntimeError)):
            raise SystemExit(str(error)) from None
        raise SystemExit("Cloud demo failed; inspect the local configuration and audit.") from None

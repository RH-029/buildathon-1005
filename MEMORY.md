# Hosted travel memory — integration handoff

This module uses **Mem0 Platform (`MemoryClient`)**, not the local Qdrant
`Memory` example in `demo.py`. It needs only `MEM0_API_KEY`; no separate OpenAI
key or local database is needed for these memory operations. Existing setup
scripts are unchanged.

## Install and run

Python 3.10+ is required. From the repository root on macOS/Linux:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-memory.txt
cp .env.example .env.local
# Fill in MEM0_API_KEY in .env.local locally, then:
python memory_demo.py check
```

Do not overwrite an existing `.env.local`. Environment variables take priority
over `.env.local`, which takes priority over `.env`. These files are Git ignored.
Never send the key to the browser or commit it. Each teammate configures their
own local environment file.

On Windows, use `py -m venv .venv`, then call `.venv\Scripts\python.exe`
instead of `python` in the commands above. The existing Hatch environment can
also install `requirements-memory.txt`.

## Planner integration

```python
from travel_memory import TravelMemory, MemoryServiceError

with TravelMemory() as memory:
    # Use explicit profile statements, not an entire assistant conversation.
    saved = memory.save_preferences(
        "jamie", "I am vegetarian and prefer gentle walks to strenuous hikes."
    )

    # Retrieve immediately before generating recommendations.
    memories = memory.get_memories(
        "jamie", "Plan a relaxed four-hour Bay Area outing with vegetarian food"
    )

    # After the actual outing, save each person's own feedback.
    saved = memory.save_feedback(
        "jamie",
        "I enjoyed the garden, but two stops felt rushed. Next time, one main activity.",
        trip_id="saturday-001",
        group_id="weekend-friends",  # Optional metadata, not shared ownership.
    )

    group_memories = memory.get_group_memories(
        ["jamie", "taylor"], "Preferred pace, travel distance, food, and past outings"
    )
```

All returned values are JSON serializable. A retrieved memory looks like:

```json
{
  "id": "provider-memory-id",
  "traveler_id": "jamie",
  "memory": "I prefer gentle walks.",
  "metadata": {"source": "traveler", "kind": "preference", "recorded_at": "..."},
  "score": 0.8,
  "created_at": "..."
}
```

Group reads return a mapping of traveler IDs to separate memory lists. Never
collapse one person's opinion into a group preference. `save_feedback` returns
`{"status": "saved", "traveler_id": "...", "memories": [...]}` when confirmed.
If the provider queues it, the status is `pending` with an `event_id`; show
"Processing memory" rather than "Saved". Do not assume pending data is searchable.

## Demo in fresh processes

The following creates fictional profiles under `demo-jamie` and `demo-taylor`.
Seed once; repeated seeding can create duplicate facts. You can choose a fresh
namespace with `seed --prefix rehearsal2` (use the matching IDs afterward).

```bash
python memory_demo.py seed
python memory_demo.py group "Plan a relaxed Saturday with vegetarian food and scenic photography" demo-jamie demo-taylor
python memory_demo.py feedback demo-jamie demo-saturday "I enjoyed the garden, but two stops felt rushed. Next time, just one main activity."
python memory_demo.py search demo-jamie "What should change about the pace and number of stops next time?"
```

Each command constructs a fresh client: the memory survives process restarts.
The CLI shows retrieved memory; the planner teammate must pass that data into
their model and use its IDs/text in the "Memories used" UI.

## Behavior and boundaries

- User-entered profile facts and outing feedback are stored verbatim with
  `infer=False`, and retrieved using Mem0 semantic search. This intentionally
  avoids extraction latency and accidental rewriting of feedback. It is not
  automatic fact extraction from a full conversation.
- Writes include UTC timestamps, a memory kind, and a trip ID for feedback.
  These are additive records. When preferences change, consider dates and ask
  about contradictions; this module does not automatically overwrite old facts.
- Current budget, return deadline, and transport are structured planner inputs.
  Semantic retrieval is not a reliable exhaustive check for hard constraints.
- A temporary mood can use `save_temporary_context(traveler_id, context,
  trip_id="...", expiration_date="YYYY-MM-DD")`. Expiration is day-based, not
  an exact return time. Mem0 hides expired memories from normal searches.
- Do not save generated itineraries as completed trips. Only the traveler can
  confirm an actual experience.
- The backend must resolve authorized traveler IDs. This library scopes queries
  but does not implement authentication or decide who can view a group member.
- Methods are synchronous. Use a synchronous route or a thread pool in an async
  web backend. Close the service at shutdown.
- `ValueError` indicates invalid input. `MemoryServiceError` indicates setup,
  provider, or response failures. Do not silently replace an outage with empty
  history. Provider errors and credentials are not included in error messages.

## Verification

```bash
python -m unittest discover -s tests -v
```

Offline checks cover traveler isolation, feedback attribution, group separation,
expiration forwarding, malformed responses, pending writes, invalid inputs, and
safe error handling. Online CLI commands require network access and consume
Mem0 API quota.

Verified on October 5, 2026: 11 offline tests pass; hosted authentication,
profile writes, feedback writes, and group retrieval in a fresh process succeed.
The connected workspace already contains the fictional `demo-jamie` and
`demo-taylor` profiles plus Jamie's `demo-saturday` feedback. Start with the
group/search commands to reuse them without seeding again.

## File ownership

Memory changes live in `travel_memory.py`, `memory_demo.py`,
`requirements-memory.txt`, `tests/test_travel_memory.py`, and this document.
Planner/UI teammates can import `TravelMemory` without editing these files.

References: [Mem0 quickstart](https://docs.mem0.ai/platform/quickstart),
[add memory](https://docs.mem0.ai/api-reference/memory/add-memories),
[search memory](https://docs.mem0.ai/api-reference/memory/search-memories).

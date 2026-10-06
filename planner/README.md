# Weekend escape planner

Planner-owned endpoint, recommendation engine, catalog, and tests. Uses Python 3.9+
and the standard library with system time zone data. Existing setup, UI, and
memory files are unchanged.

## Run

From the repository root:

```sh
python3 -m planner.demo
python3 -m unittest planner.test_planner -v
python3 -m planner.server --demo --port 8001 --cors-origin http://localhost:3000
```

On Windows use `python` in place of `python3`. If your Python environment lacks
IANA time zone data (`ZoneInfoNotFoundError`), ask the setup owner to include
`tzdata` in the shared dependencies, or use an environment that already has it.
The existing Mem0 environment is not required for the planner demo. The server
binds to `127.0.0.1`.

In another terminal:

```sh
curl http://127.0.0.1:8001/health
curl -X POST http://127.0.0.1:8001/api/plan \
  -H 'Content-Type: application/json' \
  --data-binary @planner/demo_request.json
```

PowerShell equivalent:

```powershell
python -m planner.server --demo
# In a second terminal:
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8001/api/plan `
  -ContentType 'application/json' -Body (Get-Content planner/demo_request.json -Raw)
```

`--demo` loads sample Sam/Alex preferences. Without it, the server uses no memories
unless `PLANNER_MEMORY_MODULE` is configured. Proposed plans are returned only;
planning performs no memory writes. `planner.demo` simulates completed-outing
feedback through a fake memory port; durable storage and `saveFeedback` belong
to the memory owner.

## UI handoff: POST /api/plan

Use [demo_request.json](demo_request.json) as the canonical request example.
The UI collects these structured fields; free-text conversation parsing belongs
outside this endpoint. No LLM is required to run this planner.

| Field | Meaning |
| --- | --- |
| `origin` | Sample travel: `Mountain View`, `Palo Alto`, or `Sunnyvale` (optional `, CA`). Live Routes accepts an address. |
| `start`, `end` | ISO timestamps with UTC offsets; positive window within one Pacific calendar day, at most 24 hours. |
| `budget_per_person` | USD, including the sample picnic and driving allowance. |
| `transport` | `car` only. Other modes return 400 rather than assuming driving. |
| `energy` | `low`, `medium`, or `high`; applies to this request only. |
| `allow_repeats` | Boolean; defaults to false. Completed visits lower ranking unless true. |
| `travelers` | 1–8 people with unique `id`, display `name`, and optional `interests`. |
| Traveler `budget_per_person` | Optional tighter individual cap; the strictest cap wins. |
| Traveler `max_drive_minutes` | Integer, maximum for **each** direction; default 180. |
| Traveler `max_intensity` | Integer 0–3: resting, gentle, moderate, strenuous; default 3. |
| Traveler `requires_step_free` | Boolean; unknown accessibility excludes the outing. |
| Traveler `requires_vegetarian` | Boolean; requires a vegetarian picnic plan. |

Supported interest tags: `nature`, `scenic`, `quiet`, `art`, `food`, `walking`,
`hiking`, `social`. The small catalog currently covers nature, scenic, quiet,
walking, hiking, and social activities. Unsupported fields and requirements
return 400 so a hard constraint is never silently ignored.

Response fields:

| Field | UI use |
| --- | --- |
| `status` | `ok` for three options, `insufficient_options` for 0–2. Never pad with infeasible outings. |
| `options` | At most three ranked outings, each with `place_id`, title, description, costs, return time, and timeline. |
| `why_this_fits_you` | On each option: current constraints or attributed memories with `traveler_id`, `memory_id`, and concrete `effect`. |
| `group_tradeoffs` | Individual dislikes, missed interests, and repeats remain attributed to that traveler. |
| `traveler_preference_scores` | Explainable ranking contributions; these are relative scores, not probabilities. |
| `constraint_checks` | Feasibility under labeled assumptions; never a guarantee of actual accessibility or availability. |
| `sources` | Venue link, hour/accessibility status, and independent outbound/return estimate provenance. |
| `warnings`, `data_status` | Keep visible; the catalog is sample data even with live travel enabled. |
| `memory_context` | Which travelers were queried and how many eligible memories came back. |
| `excluded` | Reasons rejected outings were not recommended; useful when no options fit. |

HTTP: 200 for a valid planning result including no feasible options; 400 for
invalid input; 413 for missing/oversized body; 415 for non-JSON; 503 if memory
retrieval fails. The planner does not silently switch to unpersonalized results.
The response contains private traveler information and uses `Cache-Control: no-store`.

## Memory owner handoff

Expose `getMemories(travelerId, query) -> list[dict]` in a Python module, then set:

```sh
export PLANNER_MEMORY_MODULE=your_memory_module
python3 -m planner.server
```

Or inject an object directly: `Planner(memory_provider=your_provider).plan(request)`.
`getMemories` is synchronous; async integrations should adapt it at the boundary.
The planner calls it separately for each traveler on **every** request.
`saveFeedback(travelerId, feedback)` remains owned by the memory component;
after it saves feedback, a new plan retrieves the updated records.

Normalize Mem0 search results into this contract (do not return the raw
`{"results": [...]}` envelope):

```json
[
  {
    "id": "sam-pace",
    "traveler_id": "sam",
    "kind": "feedback",
    "status": "completed",
    "text": "Last weekend felt rushed; I want more breathing room.",
    "signals": {"slower_pace": true}
  },
  {
    "id": "sam-visit",
    "traveler_id": "sam",
    "kind": "experience",
    "status": "completed",
    "place_id": "shoreline",
    "text": "I completed the Shoreline outing."
  }
]
```

Use Mem0 user-scoped search and map trusted `user_id`/metadata to `traveler_id`.
The planner drops wrong-user records. `text` (or raw Mem0 `memory`) supplies the
explanation; the adapter supplies structured signals:

- `liked_tags`, `avoided_tags`: supported interest tags.
- `slower_pace`: folds two agenda items into one relaxed activity, extends the
  primary activity by 30 minutes, and increases the return margin from 20 to 45.
- `short_drives`: a soft preference for shorter drives; a firm drive cap belongs
  in the request.
- A `kind: experience`, `status: completed` record with `place_id` establishes
  a completed visit. Feedback also requires `status: completed`.
- `kind: preference` records need no completion status. Temporary and proposed
  records are ignored. Keep current fatigue in `energy`, not permanent signals.

Natural-language extraction belongs to the memory adapter. The planner never
guesses hard constraints from free text. Store proposed plans separately from
completed experiences. Only trusted, confirmed feedback should become signals.

Hard constraints filter first. Then each person receives equal ranking weight,
independent of their memory count, with extra weight for the least satisfied
traveler. Negative feedback affects its author's score; it does not become a
group preference. A slower pace is an explicit group accommodation, attributed
   to the traveler who requested it. Repeats are deprioritized, not hard-excluded.

## Current travel source

The optional provider follows the official [Google Routes computeRoutes API](https://developers.google.com/maps/documentation/routes/compute_route_directions).
Set `GOOGLE_MAPS_API_KEY` in your terminal with Routes API enabled and billing
configured. No additional Python packages are needed. Never put keys in Git.

```sh
export GOOGLE_MAPS_API_KEY='your-local-key'
python3 -m planner.server --demo
```

It fetches traffic-aware outbound and return estimates separately, using their
respective departure times, and reports source/check timestamps. Departure must
be in the future; update the demo request date when needed. This can make two
billable route requests per otherwise eligible catalog item. Failed routes are
excluded with a reason; there is no silent fallback. Automated tests fake the
HTTP source; actual Google calls require your key and have not been verified.

All venue hours, route accessibility, prices, and activity durations are clearly
labeled sample assumptions. Official venue links accompany each option. In
particular, sunset-based real park hours are **not** approximated as actual
17:00 closing times; 09:00–17:00 is a demo schedule only. Sample travel is
available offline, without current traffic. This local endpoint has no identity
authentication; an eventual deployed API must resolve permitted traveler IDs
from the signed-in group rather than trusting request IDs.

## Three-minute demo

1. **0:00–0:40 — Learn/request.** Sam likes nature and needs vegetarian food;
   Alex likes social time and limits each drive to 30 minutes. They are leaving
   Mountain View at 13:00 Saturday, returning by 19:00, have $35 each, and feel
   tired today. Show `demo_request.json` and `DemoMemories` as labeled fixtures.
2. **0:40–1:30 — Plan/explain.** Run `python3 -m planner.demo`. Show three
   feasible choices and the reasons/preferences that contributed. Explain that
   a hard requirement filters before preference balancing.
3. **1:30–2:10 — Reflect.** Sam confirms the top outing was completed and says
   it felt rushed. The script simulates the memory owner's retrieval result:
   one completed visit and one attributed pace preference.
4. **2:10–3:00 — Adapt.** A fresh `Planner` with the identical request now
   chooses a new top outing, uses one relaxed activity, and reserves 45 minutes
   of breathing room. Show Sam's memory ID and its effect. Alex's drive and
   Sam's vegetarian constraints still pass. The real persisted loop is completed
   when the memory owner's `saveFeedback` and retrieval adapter are connected.

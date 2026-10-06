# TravelMind integration

Run `ui_server.py` using the environment in [SETUP.md](SETUP.md). It serves `ui/`
and all API routes on http://localhost:3000. Static-only `http.server` no longer
supports the UI workflow. No mock recommendation data or browser-local memory
storage is used. The upstream Planner still owns its sample venue catalog and
default sample drive estimates; these notices remain visible in the UI.

## Planner: POST /api/plan

The browser sends the Planner's canonical request, without frontend memory results:

```json
{
  "origin": "Mountain View",
  "start": "2026-10-10T13:00:00-07:00",
  "end": "2026-10-10T19:00:00-07:00",
  "budget_per_person": 35,
  "energy": "low",
  "transport": "car",
  "allow_repeats": false,
  "travelers": [
    {"id": "demo-jamie", "name": "Jamie", "interests": ["nature"],
     "budget_per_person": 35, "max_drive_minutes": 30, "max_intensity": 1,
     "requires_vegetarian": true, "requires_step_free": false}
  ]
}
```

Inputs use Pacific time with a calculated UTC offset, including daylight saving
time. The server validates all hard constraints with `PlanRequest.from_dict`.
The result is the Planner response (`options`, `why_this_fits_you`, `timeline`,
`warnings`, `sources`, `excluded`, `memory_context`), plus `retrieved_memories`:
a mapping of traveler IDs to the records actually retrieved for that plan.
One `PlannerMemoryAdapter` is created per request and calls hosted
`TravelMemory.get_memories` independently for each traveler.

## Memory routes

All routes require same-origin JSON POST requests.

| Route | JSON request | Response |
| --- | --- | --- |
| `/api/memories` | `traveler_id`, `query` | `{ "memories": [...] }` |
| `/api/preferences` | `traveler_id`, `text`, `signals` | TravelMemory's `saved` or `pending` result |
| `/api/feedback` | `traveler_id`, `text`, `signals`, `place_id`, `trip_id`, `completed: true` | TravelMemory's `saved` or `pending` result |

`signals` supports `liked_tags`, `avoided_tags`, `slower_pace`, and `short_drives`.
The supported tags are `nature`, `scenic`, `quiet`, `art`, `food`, `walking`,
`hiking`, and `social`. Signals come from the traveler's explicit selections,
never guessed hard constraints or assistant suggestions. Text is limited to 200
characters by the integration service. Pending writes remain labeled processing.

`ui_memory_adapter.py` bridges the current contract mismatch without editing
Planner- or Memory-owned files. It stores the traveler's text and explicit signals
in a versioned JSON envelope through the existing `save_preferences` and
`save_feedback` methods, which preserve text with `infer=False`. Retrieval maps
this envelope to the Planner's attributed signals. Confirmed completed outing
feedback also becomes an `experience` with `place_id` for novelty ranking.

Earlier plain-text memories remain visible, with their original IDs and authors.
They do not gain inferred ranking signals. Legacy feedback without structured
completion metadata is not interpreted as a confirmed visit. No temporary energy,
budget, unconfirmed proposal, or generated itinerary is saved as a permanent fact.

## Ownership and operation

UI-owned: `ui/`, `ui_server.py`, `ui_memory_adapter.py`, `requirements-ui.txt`,
`tests/test_ui_integration.py`, and this document. Planner and Memory modules
are imported without modification.

Provider credentials stay server-side in Git-ignored `.env` / `.env.local`.
Serving is restricted to `ui/`. The API binds to loopback, checks Host and Origin,
does not log request bodies, and returns safe errors without fallback history.
It is a local collaboration app; traveler IDs are not authentication. A deployed
version must resolve authorized traveler IDs from a signed-in session.

Checks:

```powershell
.\.venv\Scripts\python.exe -m unittest planner.test_planner tests.test_travel_memory tests.test_ui_integration -v
node --check ui/app.js
node --check ui/api.js
```

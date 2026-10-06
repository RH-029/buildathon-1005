# TravelMind — your weekend escape agent

**Live app:** [https://buildathon-1005.onrender.com/](https://buildathon-1005.onrender.com/)

TravelMind turns a free Bay Area afternoon into up to three outings that fit
your group's time, energy, budget, and requirements. Each recommendation shows
the memories that influenced it. Save personal interests and completed-outing
feedback to hosted Mem0, then generate a new plan to use that history.

The complete app is **`ui_server.py`**. It serves the frontend in `ui/` and the
Python API from one address. You do not need a separate frontend server,
Node.js build, local database, Docker, or OpenAI key to run this flow.

## 1. Requirements

- Python **3.10 or newer**; Python **3.12** is the deployment target.
- A Mem0 Platform API key and network access to Mem0.
- Git to clone/pull the repository.

Check your Python version first:

```bash
python3 --version
```

If macOS's `python3` reports 3.9, use an installed `python3.12` in the commands
below. On Windows, check `py -3.12 --version`.

## 2. Install locally

### macOS / Linux

```bash
git clone https://github.com/RH-029/buildathon-1005.git
cd buildathon-1005
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-ui.txt
```

If you already have this checkout and a suitable `.venv`, use that directory
and activate the existing environment. The UI requirements include the hosted
memory dependencies and Pacific time zone data.

### Windows PowerShell

```powershell
git clone https://github.com/RH-029/buildathon-1005.git
cd buildathon-1005
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-ui.txt
```

These Windows commands call the environment's Python directly, so activation
and PowerShell execution-policy changes are unnecessary.

## 3. Configure your key

Create `.env.local` in the repository root **only if it does not already exist**.
Its contents should be:

```dotenv
MEM0_API_KEY=your_mem0_api_key
MEM0_TELEMETRY=false
```

The key is already configured in the current development checkout. Preserve
that file when pulling updates. It is Git-ignored, so a fresh clone or a Render
deployment needs its own key configuration. Never put the key in frontend code,
the README, or a Git commit. Terminal environment variables take priority over
`.env.local`, which takes priority over `.env`.

Optional: add `GOOGLE_MAPS_API_KEY` to enable the planner's Google Routes travel
estimates. It requires an enabled Routes API and billing. Without it, the
planner uses clearly labeled sample drive estimates. Venue hours, prices, and
accessibility remain sample catalog assumptions in either mode.

## 4. Start the full app

With the macOS/Linux environment activated:

```bash
python ui_server.py
```

Windows:

```powershell
.\.venv\Scripts\python.exe ui_server.py
```

Open **http://localhost:3000** in your browser. Keep the terminal running; press
Ctrl+C to stop the app. The same server handles the UI, planning, preferences,
memory retrieval, and feedback. Opening `ui/index.html` directly or serving it
with `python -m http.server` does not run the API.

If port 3000 is in use:

```bash
python ui_server.py --port 3001
```

Then open http://localhost:3001. A `PORT` environment variable also changes the
default port, so use the address printed by the server.

Verify the local server in a second terminal:

```bash
curl http://localhost:3000/api/health
```

PowerShell equivalent:

```powershell
Invoke-RestMethod http://localhost:3000/api/health
```

The health endpoint checks that the app can serve requests; it does not make
a Mem0 network call. To verify the actual key and connection:

```bash
python memory_demo.py check
```

On Windows, replace `python` with `.\.venv\Scripts\python.exe`.

## 5. Try the memory loop in the browser

1. The first traveler defaults to **Jamie**, ID `demo-jamie`. These IDs refer
   to fictional demo profiles in the configured Mem0 workspace; do not reseed
   them for each run.
2. Click **+ Add traveler** and enter name `Taylor`, ID `demo-taylor`. Select
   interests and set each person's drive, budget, activity, and dietary/access
   requirements. Choose **Remember interests** to save selected interests.
3. Set origin **Mountain View**, choose an outing date, leave at **13:00**,
   return by **19:00**, budget **$35 per person**, and energy **Low**. Set
   Jamie's **Vegetarian picnic required** checkbox. Sample travel also supports
   **Palo Alto** and **Sunnyvale**.
4. Click **Find our experiences**. Inspect the recommendations, **Why this
   fits your crew**, memories, exclusions, timelines, and data-source notices.
   If fewer than three outings fit, the planner keeps the constraints and
   explains the exclusions rather than adding infeasible options.
5. After a completed outing, expand **After your outing · share feedback** on
   that card. Select the author, write their feedback, optionally check
   **I prefer a slower pace next time**, and confirm **I actually completed
   this outing** before saving. For a rehearsal, use fictional demo travelers
   and explicitly describe it as fictional.
6. Generate another plan, or reload the page and re-enter the same traveler
   IDs and request. Hosted memory persists; the author stays attached to each
   record. A `pending` write remains labeled processing until searchable.

The UI also supports explicit interest/pace selections stored in a versioned
memory envelope. Its adapter and routes are described in [UI-CONTRACT.md](UI-CONTRACT.md).
The planner's separate cloud adapter interprets supported raw English/Chinese
phrases and performs exhaustive profile reads; see [planner/README.md](planner/README.md).

## 6. Deploy the complete app on Render

Create a **Web Service** using this GitHub repository, with runtime **Python 3**.
The service runs the frontend and API together; no separate Static Site is needed.

### Fill in the form

| Render field | Value |
| --- | --- |
| Name | `travelmind` (or another available name) |
| Repository | `RH-029/buildathon-1005` |
| Branch | `feature/planner` after these changes are committed and pushed; use `main` after they are merged |
| Root Directory | Leave blank (repository root) |
| Runtime / Language | Python 3 |
| Build Command | `pip install -r requirements-ui.txt` |
| Start Command | `python ui_server.py --host 0.0.0.0 --port $PORT` |
| Health Check Path | `/api/health` |

For the two fields in the screenshot, copy these exact values without a leading `$`:

**Build Command**

```bash
pip install -r requirements-ui.txt
```

**Start Command**

```bash
python ui_server.py --host 0.0.0.0 --port $PORT
```

The `$PORT` at the end is part of the start command. Render supplies its value.
The `gunicorn your_application.wsgi` placeholder does not match this app:
`ui_server.py` is a Python HTTP server, not a WSGI application.

### Environment variables

Under Render's **Environment** settings, add:

| Key | Value | Required? |
| --- | --- | --- |
| `MEM0_API_KEY` | Your existing Mem0 key from `.env.local`; paste its value only, without quotes | Yes |
| `MEM0_TELEMETRY` | `false` | Recommended |
| `PYTHONUNBUFFERED` | `1` | Recommended for immediate startup logs |
| `GOOGLE_MAPS_API_KEY` | Your separate Google Routes key | Optional |

The checked-in `.python-version` selects Python **3.12**. Leave `PYTHON_VERSION`
unset unless you deliberately want to override that file; a Render environment
override requires a fully qualified released version such as `3.12.10`.

Render supplies `PORT` and `RENDER_EXTERNAL_URL`. The app uses the external URL
to accept the deployed hostname and HTTPS same-origin requests while rejecting
unrelated hosts/origins. No CORS configuration is needed for this one-service
deployment. If you later use a custom domain, set `APP_PUBLIC_URL` to its exact
origin, for example `https://travel.example.com` (no path).

No database service or persistent disk is required for memory: it is stored
in hosted Mem0. Your local `.env.local` and `.venv` are not uploaded through Git;
Render installs dependencies and reads its own environment variables.

### Publish and verify

1. Commit and push the README, `.python-version`, and server changes to the
   branch selected in Render. A local change is not deployed until it is pushed.
2. Add the environment variables, then choose **Deploy Web Service** (or redeploy
   an existing service after saving its environment settings).
3. In logs, confirm the server listens on `0.0.0.0` and Render's assigned port.
4. Open the service's **HTTPS** URL. Test `/api/health`, then create a plan using
   the fictional demo travelers and verify that the memory routes work.

This is a small hackathon demo server. Traveler IDs are not authentication:
the current app has no sign-in or per-user access control, so only use a Mem0
workspace containing fictional demo data for a public deployment. Real-user
deployment requires authenticated authorization for traveler IDs.

Render references: [web services and port binding](https://render.com/docs/web-services#port-binding),
[Python version selection](https://render.com/docs/python-version),
[environment variables](https://render.com/docs/configure-environment-variables),
and [health checks](https://render.com/docs/health-checks).

## 7. Tests and standalone planner commands

Run these from the repository root with the environment activated:

```bash
python -m unittest planner.test_planner planner.test_hosted_memory -v
python -m unittest discover -s tests -v
```

Optional JavaScript syntax checks (Node.js is needed for these checks only):

```bash
node --check ui/app.js
node --check ui/api.js
```

The planner can also be run independently of the browser:

```bash
python -m planner.demo                    # Offline fixtures; no memory writes
python -m planner.cloud_demo --snapshot   # Read-only hosted plan
python -m planner.cloud_demo              # Writes one fictional Jamie feedback record
python -m planner.server --hosted-memory  # Planner API only, on port 8001
```

Use `ui_server.py` for the complete app and for Render, not the planner-only server.
The old `demo.py` / `run-demo.ps1` are separate local-Qdrant SDK examples;
they are not the TravelMind app's startup commands. Their original setup remains
documented in [SETUP.md](SETUP.md).

## Troubleshooting

| Symptom | What to check |
| --- | --- |
| `ModuleNotFoundError`, missing packages | Activate `.venv` and install `requirements-ui.txt` using that environment's Python. |
| `ZoneInfoNotFoundError` | Install `requirements-ui.txt`; it includes `tzdata`, particularly useful on Windows. |
| Port already in use | Start with `--port 3001` and open the matching address. |
| UI loads but planning returns 503 | Verify `MEM0_API_KEY`, network/account access, and quota with `python memory_demo.py check`. Health alone does not verify Mem0. |
| Render cannot find `requirements.txt` | Use the build command `pip install -r requirements-ui.txt` and leave Root Directory blank. |
| Render reports no open ports | Use `--host 0.0.0.0 --port $PORT` and confirm this updated server is on the deployed branch. |
| Render returns 403 | Open the service's configured HTTPS URL. For a custom domain, set `APP_PUBLIC_URL` to that origin and redeploy. |
| Fewer than three outings | Review exclusions. Sample travel supports three origins and car transport; budgets, time windows, and access requirements can rule out options. |
| Feedback does not immediately change ranking | A pending write may not be searchable yet; retry planning after it finishes. Existing pace feedback can already affect the baseline. Use the same traveler IDs. |

More details: [memory handoff](MEMORY.md), [planner guide](planner/README.md),
and [UI integration contract](UI-CONTRACT.md). Application code and documentation
use English.

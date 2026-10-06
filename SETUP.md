# Mem0 setup

Application repository: `D:\mem0\buidathon-1005`. The existing directory name is preserved.
Application code, launch scripts, and documentation belong in this repository.

The upstream Mem0 checkout and its installed environments remain at `D:\mem0\mem0`.
This separate dependency checkout preserves the existing virtual environment and editable installation paths.

```text
D:\mem0\
  buidathon-1005\       Application repository
    demo.py            Online memory example
    check_setup.py     Offline installation check
    run-demo.ps1       Application entry point
    SETUP.md           Setup instructions
    data\              Local runtime data (Git ignored)
  mem0\                Upstream SDK checkout
    .venv\             Hatch tooling
    .hatch\local\      SDK and development dependencies
    hatch.toml         Local Hatch configuration
```

## Run the travel UI

```powershell
cd D:\mem0\buidathon-1005
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-ui.txt
# Set MEM0_API_KEY in .env or .env.local locally, then:
.\.venv\Scripts\python.exe ui_server.py
```

Open http://localhost:3000. Stop the server with Ctrl+C.
The UI calls the real Planner and hosted Mem0 through one local integration server.
`.env.local` takes priority over `.env`; environment variables take priority over both.
An unavailable Memory service returns an error and never falls back to local storage.
The server serves only `ui/`, keeping local environment files outside its document root.
Use `demo-jamie` / `demo-taylor` to retrieve the existing fictional profiles, or enter
your own traveler IDs. Profile writes happen only through **Remember interests**;
outing feedback requires an explicit completion confirmation.

Planner venue facts remain a sample catalog. Default drive estimates support
Mountain View, Palo Alto, and Sunnyvale. Optional `GOOGLE_MAPS_API_KEY` enables live
Google Routes estimates, including billable requests; venue facts remain sample.
All date/time inputs use Pacific time. See [UI-CONTRACT.md](UI-CONTRACT.md).
UI work belongs to `codex/ui`. This loopback service is intended for local development.
To restart an already installed environment, run only the final command above.

## Run the memory demo

```powershell
cd D:\mem0\buidathon-1005
$env:OPENAI_API_KEY = 'YOUR_OPENAI_API_KEY'
.\run-demo.ps1
```

The script uses OpenAI models and local Qdrant storage. Model calls consume API credits.
Memory data is stored in the application's `data` directory. The key stays in the current terminal.
Docker is not required for this SDK example.

## Verify the installation

```powershell
cd D:\mem0\mem0
.\.venv\Scripts\hatch.exe run local:python ..\buidathon-1005\check_setup.py
.\.venv\Scripts\hatch.exe run local:pytest tests/llms/test_openai.py tests/vector_stores/test_qdrant.py -q
```

Installed version: mem0ai 2.2.1, Python 3.12, Hatch 1.18.1.
SDK import and local Qdrant/SQLite initialization succeeded.
The upstream tests previously reported 116 passes and one Windows SQLite file cleanup failure.
The upstream repository's pre-commit hooks are installed. Anonymous SDK telemetry is disabled.
Online memory operations require an API key and have not been verified.

## Optional self-hosted dashboard

See `D:\mem0\mem0\server\README.md`. Start Docker Desktop, copy `server/.env.example`
to `server/.env`, set `POSTGRES_PASSWORD` and `OPENAI_API_KEY`, then run `docker compose up -d`
from the server directory. Dashboard: http://localhost:3000. API docs: http://localhost:8888/docs.

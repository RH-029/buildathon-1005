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

## Run the demo

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

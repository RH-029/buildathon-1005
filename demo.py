"""Run using run-demo.ps1 from this directory."""
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
DATA.mkdir(exist_ok=True)
os.environ.setdefault("MEM0_DIR", str(DATA))
os.environ.setdefault("MEM0_TELEMETRY", "false")

if not os.environ.get("OPENAI_API_KEY"):
    raise SystemExit("Set OPENAI_API_KEY in your terminal before running this demo.")

from mem0 import Memory

memory = Memory.from_config({
    "vector_store": {"provider": "qdrant", "config": {
        "collection_name": "local_demo", "path": str(DATA / "qdrant"),
        "embedding_model_dims": 1536,
    }},
    "history_db_path": str(DATA / "history.db"),
})
print(json.dumps(memory.add(
    [{"role": "user", "content": "I prefer Chinese replies and use Windows for development."}],
    user_id="demo_user",
), ensure_ascii=False, indent=2))
print(json.dumps(memory.search("What are my preferences?", filters={"user_id": "demo_user"}),
                 ensure_ascii=False, indent=2))

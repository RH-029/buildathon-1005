"""Offline installation check: no model calls, credentials, or existing data."""
import os
import tempfile
from pathlib import Path

os.environ["MEM0_TELEMETRY"] = "false"
os.environ["MEM0_DIR"] = str(Path(__file__).resolve().parent / "data")

from mem0 import Memory

with tempfile.TemporaryDirectory() as temporary:
    memory = Memory.from_config({
        "llm": {"provider": "openai", "config": {"api_key": "offline-check"}},
        "embedder": {"provider": "openai", "config": {"api_key": "offline-check"}},
        "vector_store": {"provider": "qdrant", "config": {
            "path": str(Path(temporary) / "qdrant"), "collection_name": "setup_check",
            "embedding_model_dims": 1536,
        }},
        "history_db_path": str(Path(temporary) / "history.db"),
    })
    try:
        assert memory.get_all(filters={"user_id": "setup_check"})["results"] == []
    finally:
        memory.vector_store.client.close()
        memory.db.close()
print("PASS: SDK initializes with local Qdrant and SQLite; empty memory read succeeds.")

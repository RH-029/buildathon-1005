"""TravelMind UI and API service for local use and a small hosted demo."""

import argparse
from datetime import datetime
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import threading
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

from planner.engine import MemoryUnavailable, Planner
from planner.models import PlanRequest, fields, string
from planner.travel import GoogleRoutesProvider
from travel_memory import MemoryServiceError, TravelMemory
from ui_memory_adapter import PlannerMemoryAdapter, decode_record, envelope, signals_from

ROOT = Path(__file__).resolve().parent


class UIService:
    def __init__(self, memory=None, travel_provider=None):
        self.memory = memory
        self.travel_provider = travel_provider
        self.lock = threading.Lock()

    def memory_service(self):
        if self.memory is None:
            try:
                self.memory = TravelMemory()
            except ImportError:
                raise MemoryServiceError("Install requirements-ui.txt and restart the TravelMind server.") from None
        return self.memory

    def dispatch(self, path, data):
        # One hosted client; keep each plan's retrieved records private to that request.
        with self.lock:
            if path == "/api/plan":
                request = PlanRequest.from_dict(data)
                memory = self.memory_service()
                adapter = PlannerMemoryAdapter(memory)
                travel = self.travel_provider
                key = os.environ.get("GOOGLE_MAPS_API_KEY")
                if travel is None and key:
                    travel = GoogleRoutesProvider(key)
                result = Planner(memory_provider=adapter, travel_provider=travel).plan(request)
                result["retrieved_memories"] = adapter.retrieved
                return result
            if path == "/api/memories":
                fields(data, {"traveler_id", "query"}, "memory request")
                return {"memories": [decode_record(row) for row in self.memory_service().get_memories(
                    string(data.get("traveler_id"), "traveler_id"), string(data.get("query"), "query"))]}
            if path == "/api/preferences":
                fields(data, {"traveler_id", "text", "signals"}, "preference request")
                traveler = string(data.get("traveler_id"), "traveler_id")
                text = string(data.get("text"), "text")
                signals = signals_from(data.get("signals", {}))
                return self.memory_service().save_preferences(traveler, envelope("preference", text, signals))
            if path == "/api/feedback":
                fields(data, {"traveler_id", "text", "signals", "place_id", "trip_id", "completed"}, "feedback request")
                if data.get("completed") is not True:
                    raise ValueError("Confirm that you completed this outing before saving trip feedback.")
                traveler = string(data.get("traveler_id"), "traveler_id")
                text = string(data.get("text"), "text")
                place = string(data.get("place_id"), "place_id")
                trip = string(data.get("trip_id"), "trip_id")
                signals = signals_from(data.get("signals", {}))
                return self.memory_service().save_feedback(
                    traveler, envelope("feedback", text, signals, place), trip_id=trip)
            raise ValueError("Unknown API endpoint.")

    def close(self):
        if self.memory is not None:
            self.memory.close()


def public_origin(value):
    """Validate the configured origin instead of trusting forwarded headers."""
    if not value:
        return None
    parsed = urlsplit(value)
    if (parsed.scheme not in {"http", "https"} or not parsed.hostname or
            parsed.username or parsed.password or parsed.path not in {"", "/"} or
            parsed.query or parsed.fragment):
        raise ValueError("public-url must be an http(s) origin without a path, query, or credentials.")
    try:
        parsed.port
    except ValueError:
        raise ValueError("public-url has an invalid port.") from None
    return f"{parsed.scheme}://{parsed.netloc}".rstrip("/")


def handler_for(service, public_url=None):
    configured_origin = public_origin(public_url)
    configured_host = urlsplit(configured_origin).netloc.casefold() if configured_origin else None

    class Handler(SimpleHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def end_headers(self):
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            super().end_headers()

        def reply(self, status, value):
            payload = json.dumps(value, ensure_ascii=False, allow_nan=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def local_host(self):
            # Local aliases plus one configured external host, never a wildcard.
            host = self.headers.get("Host", "").casefold()
            return host in {f"localhost:{self.server.server_port}",
                            f"127.0.0.1:{self.server.server_port}", configured_host}

        def same_origin(self):
            origin = self.headers.get("Origin")
            if origin is None:
                return True  # CLI calls and Render health checks omit Origin.
            host = self.headers.get("Host", "").casefold()
            expected = configured_origin if host == configured_host else f"http://{host}"
            return origin == expected

        def do_GET(self):
            if not self.local_host():
                self.reply(403, {"error": "Use the configured TravelMind address."})
                return
            if self.path == "/api/health":
                self.reply(200, {"service": "TravelMind", "memory": "hosted_mem0",
                                 "catalog": "sample_catalog",
                                 "travel": "google_routes" if os.environ.get("GOOGLE_MAPS_API_KEY") else "sample_estimates",
                                 "pacific_date": datetime.now(ZoneInfo("America/Los_Angeles")).date().isoformat()})
            elif urlsplit(self.path).path.startswith("/api/"):
                self.reply(404, {"error": "Unknown API endpoint."})
            else:
                super().do_GET()

        def do_POST(self):
            if not self.local_host() or not self.same_origin():
                self.reply(403, {"error": "Use the same origin as the TravelMind UI."})
                return
            if self.path not in {"/api/plan", "/api/memories", "/api/preferences", "/api/feedback"}:
                self.reply(404, {"error": "Unknown API endpoint."})
                return
            if self.headers.get("Content-Type", "").split(";")[0].strip() != "application/json":
                self.reply(415, {"error": "Content-Type must be application/json."})
                return
            try:
                size = int(self.headers.get("Content-Length", "0"))
                if not 0 < size <= 65536:
                    self.reply(413, {"error": "Provide a JSON body of at most 64 KiB."})
                    return
                data = json.loads(self.rfile.read(size))
                result = service.dispatch(self.path, data)
            except (ValueError, UnicodeDecodeError) as error:
                self.reply(400, {"error": str(error)})
                return
            except (MemoryServiceError, MemoryUnavailable) as error:
                self.reply(503, {"error": str(error)})
                return
            except Exception:
                self.reply(500, {"error": "TravelMind service failed. Check the local server setup."})
                return
            self.reply(200, result)
    # Serve only ui/, never the root directory containing .env.local.
    return partial(Handler, directory=str(ROOT / "ui"))


def main():
    parser = argparse.ArgumentParser(description="TravelMind UI with real Planner and hosted Mem0")
    parser.add_argument("--port", type=int, default=os.environ.get("PORT", "3000"))
    parser.add_argument("--host", default="127.0.0.1", help="Use 0.0.0.0 on Render")
    parser.add_argument("--public-url", default=os.environ.get("APP_PUBLIC_URL") or os.environ.get("RENDER_EXTERNAL_URL"),
                        help="External origin; Render supplies RENDER_EXTERNAL_URL automatically")
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error("port must be between 1 and 65535")
    try:
        origin = public_origin(args.public_url)
    except ValueError as error:
        parser.error(str(error))
    if args.host not in {"127.0.0.1", "localhost", "0.0.0.0"}:
        parser.error("host must be 127.0.0.1, localhost, or 0.0.0.0")
    try:
        from dotenv import load_dotenv
    except ImportError:
        parser.error("Install requirements-ui.txt first.")
    load_dotenv(ROOT / ".env.local")
    load_dotenv(ROOT / ".env")
    service = UIService()
    server = ThreadingHTTPServer((args.host, args.port), handler_for(service, origin))
    server.daemon_threads = False
    server.timeout = 1
    print(f"TravelMind: {origin or f'http://localhost:{args.port}'} (listening on {args.host}:{args.port})", flush=True)
    print("Memory: hosted Mem0 (no mock fallback). Catalog: planner sample assumptions.", flush=True)
    if not os.environ.get("MEM0_API_KEY", "").strip():
        print("Set MEM0_API_KEY in .env.local and restart to enable memory and planning.", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        service.close()


if __name__ == "__main__":
    main()

"""Local planner HTTP endpoint, using only the Python standard library."""

import argparse
import importlib
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

from .engine import MemoryUnavailable, Planner
from .models import ValidationError
from .travel import GoogleRoutesProvider


def handler_for(planner, cors_origin=None):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format, *args):
            pass  # Request bodies and travelers' preferences are never logged.

        def reply(self, status, value):
            payload = json.dumps(value, allow_nan=False).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Cache-Control", "no-store")
            if cors_origin and self.headers.get("Origin") == cors_origin:
                self.send_header("Access-Control-Allow-Origin", cors_origin)
                self.send_header("Vary", "Origin")
                self.send_header("Access-Control-Allow-Methods", "POST, GET, OPTIONS")
                self.send_header("Access-Control-Allow-Headers", "Content-Type")
            self.end_headers()
            self.wfile.write(payload)

        def do_OPTIONS(self):
            self.reply(200, {"ok": True})

        def do_GET(self):
            if self.path == "/health":
                self.reply(200, {"ok": True, "service": "weekend-escape-planner"})
            else:
                self.reply(404, {"error": "Use POST /api/plan or GET /health."})

        def do_POST(self):
            if self.path != "/api/plan":
                self.reply(404, {"error": "Unknown endpoint."})
                return
            if self.headers.get("Content-Type", "").split(";")[0].strip() != "application/json":
                self.reply(415, {"error": "Content-Type must be application/json."})
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= 65536:
                    self.reply(413, {"error": "Provide a JSON body of at most 64 KiB."})
                    return
                data = json.loads(self.rfile.read(length))
                result = planner.plan(data)
            except (ValueError, UnicodeDecodeError, ValidationError) as error:
                self.reply(400, {"error": str(error)})
                return
            except MemoryUnavailable as error:
                self.reply(503, {"error": str(error)})
                return
            except Exception:
                self.reply(500, {"error": "Planner failed. Check the server configuration."})
                return
            self.reply(200, result)
    return Handler


def main():
    parser = argparse.ArgumentParser(description="Local weekend escape planner endpoint")
    parser.add_argument("--port", type=int, default=8001)
    parser.add_argument("--demo", action="store_true", help="Use clearly labeled sample traveler memories")
    parser.add_argument("--hosted-memory", action="store_true", help="Use the real TravelMemory module and .env.local Mem0 key")
    parser.add_argument("--cors-origin", help="Exact local UI origin, e.g. http://localhost:3000")
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error("port must be between 1 and 65535")
    if args.cors_origin:
        parsed = urlsplit(args.cors_origin)
        if parsed.scheme != "http" or parsed.hostname not in ("localhost", "127.0.0.1") or parsed.path or parsed.query or parsed.fragment:
            parser.error("cors-origin must be an exact localhost or 127.0.0.1 HTTP origin")
    memory = None
    module_name = os.environ.get("PLANNER_MEMORY_MODULE")
    if args.hosted_memory and (args.demo or module_name):
        parser.error("Choose one of --hosted-memory, --demo, or PLANNER_MEMORY_MODULE")
    if module_name:
        if args.demo:
            parser.error("Choose either --demo or PLANNER_MEMORY_MODULE")
        memory = importlib.import_module(module_name)  # Module exposes getMemories(travelerId, query).
    elif args.demo:
        from .demo import DemoMemories
        memory = DemoMemories()
    elif args.hosted_memory:
        from .hosted_memory import HostedMemoryProvider
        memory = HostedMemoryProvider()
    api_key = os.environ.get("GOOGLE_MAPS_API_KEY")
    planner = Planner(memory_provider=memory,
                      travel_provider=GoogleRoutesProvider(api_key) if api_key else None)
    server = None
    try:
        server = ThreadingHTTPServer(("127.0.0.1", args.port), handler_for(planner, args.cors_origin))
        print(f"Planner: http://127.0.0.1:{args.port}/api/plan", flush=True)
        print(f"Memories: {'Mem0 hosted' if args.hosted_memory else 'demo' if args.demo else module_name or 'empty'}; travel: {'Google Routes' if api_key else 'sample'}; venue facts: sample", flush=True)
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        if server is not None:
            server.server_close()
        if args.hosted_memory:
            memory.close()


if __name__ == "__main__":
    main()

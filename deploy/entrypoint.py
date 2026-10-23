"""Liara starts in explicit maintenance or an already prepared shadow mission."""

import json
import os
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path


def main():
    if os.environ.get("ROYIN_MAINTENANCE", "false") == "true":
        duration = int(os.environ.get("ROYIN_MAINTENANCE_SECONDS", "1800"))
        if not 10 <= duration <= 3600:
            raise ValueError("Maintenance must last ten seconds to one hour")
        port = int(os.environ.get("PORT", "3000"))

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                if self.path not in ("/", "/healthz", "/readyz"):
                    self.send_error(404)
                    return
                body = json.dumps(
                    dict(status="MAINTENANCE_NO_ENGINE", ready=False, model_http=0, live_orders=0)
                ).encode()
                self.send_response(503 if self.path == "/readyz" else 200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *_):
                pass

        server = HTTPServer(("0.0.0.0", port), Handler)
        server.timeout = 1
        expires = time.monotonic() + duration
        try:
            while time.monotonic() < expires:
                server.handle_request()
        finally:
            server.server_close()
        return 0
    if os.environ.get("ROYIN_MAINTENANCE", "false") != "false":
        raise ValueError("Maintenance flag must be explicit true/false")
    kind = os.environ.get("ROYIN_SERVICE_KIND", "shadow")
    if kind == "fresh-live":
        from scripts.run_fresh_service import main as run_service
    elif kind == "shadow":
        from scripts.run_service import main as run_service
    else:
        raise ValueError("Service kind must be shadow or fresh-live")

    root = Path("/state")
    if not os.path.ismount(root):
        raise ValueError("Dedicated persistent volume is not mounted")
    # Never construct a budget or financial database here; state must be transferred first.
    arguments = [
        "--run",
        "--state-root",
        str(root),
        "--policy",
        os.environ.get("ROYIN_SERVICE_POLICY", "/state/service-contract.json"),
    ]
    if kind == "shadow":
        arguments.extend(["--require-mount", "--port", os.environ.get("PORT", "3000")])
    return run_service(arguments)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, OSError, TypeError) as exc:
        print(json.dumps(dict(status="BLOCKED_ENTRYPOINT", error_type=type(exc).__name__)))
        raise SystemExit(2) from None

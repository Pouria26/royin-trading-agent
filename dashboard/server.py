"""Local read-only monitoring API and fixed static assets, standard library only."""

import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

try:
    from .sources import Sources, envelope
except ImportError:
    from sources import Sources, envelope

ASSETS = Path(__file__).resolve().parent / "static"
ROUTES = {"/": ("index.html", "text/html; charset=utf-8"),
          "/app.js": ("app.js", "text/javascript; charset=utf-8"),
          "/style.css": ("style.css", "text/css; charset=utf-8"),
          "/fonts/Vazirmatn-Variable.woff2": ("fonts/Vazirmatn-Variable.woff2", "font/woff2"),
          "/fonts/InterVariable.woff2": ("fonts/InterVariable.woff2", "font/woff2")}


def handler_for(sources, *, allowed_hosts=None, allowed_origins=None, authorize=None):
    class Handler(BaseHTTPRequestHandler):
        server_version = "RoyInMonitor/1"
        sys_version = ""

        def log_message(self, *_):
            pass  # Request targets can contain hostile text; never log them.

        def send(self, code, body, mime="application/json; charset=utf-8"):
            if not isinstance(body, bytes):
                body = json.dumps(body, ensure_ascii=False, allow_nan=False).encode("utf8")
            self.send_response(code)
            self.send_header("Content-Type", mime)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'")
            self.send_header("Allow", "GET, HEAD")
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(body)

        def do_HEAD(self):
            self.do_GET()

        def do_GET(self):
            port = self.server.server_port
            hosts = allowed_hosts or {f"127.0.0.1:{port}", f"localhost:{port}"}
            origins = allowed_origins or {f"http://127.0.0.1:{port}", f"http://localhost:{port}"}
            if self.headers.get("Host") not in hosts:
                return self.send(403, envelope("INVALID", error="HOST_DENIED"))
            origin = self.headers.get("Origin")
            if origin and origin not in origins:
                return self.send(403, envelope("INVALID", error="ORIGIN_DENIED"))
            # Opening a link from a messenger/search page is a legitimate navigation.
            # Keep cross-site API reads, assets and embedded documents isolated.
            navigation = (self.path == "/" and self.command == "GET"
                          and self.headers.get("Sec-Fetch-Mode") == "navigate"
                          and self.headers.get("Sec-Fetch-Dest") == "document")
            if self.headers.get("Sec-Fetch-Site") == "cross-site" and not navigation:
                return self.send(403, envelope("INVALID", error="CROSS_SITE_DENIED"))
            if authorize is not None and not authorize(self):
                return
            try:
                if len(self.path) > 2048:
                    raise ValueError("request bound")
                url = urlsplit(self.path)
                query = parse_qs(url.query, keep_blank_values=True, strict_parsing=True, max_num_fields=8)
                if any(len(v) != 1 or len(v[0]) > 160 for v in query.values()):
                    raise ValueError("query")
                params = {k: v[0] for k, v in query.items()}
                if url.path in ROUTES and not params:
                    name, mime = ROUTES[url.path]
                    return self.send(200, (ASSETS / name).read_bytes(), mime)
                if url.path == "/api/v1/overview" and not params:
                    return self.send(200, sources.overview())
                if url.path == "/api/v1/runs" and not params:
                    return self.send(200, sources.runs())
                if url.path not in {"/api/v1/evaluation", "/api/v1/decisions", "/api/v1/orders"}:
                    return self.send(404, envelope("UNAVAILABLE", error="NOT_FOUND"))
                allowed = {"run", "dataset"}
                if url.path != "/api/v1/evaluation":
                    allowed |= {"arm", "offset", "limit", "action"}
                if set(params) - allowed or not {"run", "dataset"} <= params.keys():
                    raise ValueError("query")
                if url.path == "/api/v1/evaluation":
                    result = sources.evaluation(params["run"], params["dataset"])
                else:
                    offset, limit = int(params.get("offset", "0")), int(params.get("limit", "25"))
                    action = params.get("action", "ALL")
                    if not 0 <= offset <= 5000 or not 1 <= limit <= 100 or action not in {"ALL", "WAIT", "ENTER", "EXIT"}:
                        raise ValueError("pagination")
                    result = sources.rows(params["run"], params["dataset"], params.get("arm"),
                                          url.path.rsplit("/", 1)[-1], offset, limit, action)
                return self.send(200, result)
            except KeyError:
                return self.send(404, envelope("UNAVAILABLE", error="SELECTION_NOT_FOUND"))
            except (ValueError, TypeError, AttributeError):
                return self.send(400, envelope("INVALID", error="INVALID_REQUEST_OR_EVIDENCE"))
            except OSError:
                return self.send(503, envelope("UNAVAILABLE", error="SOURCE_TEMPORARILY_UNAVAILABLE"))

        def reject(self):
            self.close_connection = True
            # Drain only small framed bodies so closing a read-only rejection does
            # not reset the socket before clients can read the 405 response.
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if 0 < length <= 4096 and not self.headers.get("Transfer-Encoding"):
                    self.connection.settimeout(1)
                    self.rfile.read(length)
            except (ValueError, OSError):
                pass
            self.send(405, envelope("INVALID", error="READ_ONLY_GET_HEAD"))

        do_POST = do_PUT = do_PATCH = do_DELETE = do_OPTIONS = do_TRACE = do_CONNECT = reject

    return Handler


def make_server(port=8765, root=None):
    return ThreadingHTTPServer(("127.0.0.1", port), handler_for(Sources(root or Path(__file__).resolve().parents[1])))


def main():
    parser = argparse.ArgumentParser(description="RoyIn localhost read-only evidence dashboard; no financial or model calls")
    parser.add_argument("--port", type=int, default=8765, help="localhost port (1024-65535), default 8765")
    args = parser.parse_args()
    if not 1024 <= args.port <= 65535:
        parser.error("port must be 1024-65535")
    server = make_server(args.port)
    print(f"SERVER_AVAILABLE http://127.0.0.1:{args.port} | read-only | worker UNKNOWN", flush=True)
    try:
        server.serve_forever(poll_interval=.25)
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()

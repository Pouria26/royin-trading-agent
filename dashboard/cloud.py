"""Authenticated, separate monitoring service. It has no financial keys or disk."""

import base64
import hashlib
import hmac
import json
import os
import secrets
import tempfile
import threading
import time
from collections import deque
from http.server import ThreadingHTTPServer
from pathlib import Path

from dashboard.monitor_snapshot import MAX_PUSH_BYTES, activity_view, snapshot_view, stamp
from dashboard.server import handler_for
from dashboard.sources import Sources


def signature(key, sent_at, nonce, body):
    return hmac.new(key.encode(), str(sent_at).encode() + b"\n" + nonce.encode() + b"\n" + body,
                    hashlib.sha256).hexdigest()


class MonitorSources(Sources):
    def __init__(self, root):
        super().__init__(root)
        self.activity = None
        self.received_at = None
        self.state_lock = threading.Lock()

    def overview(self):
        with self.state_lock:
            result = super().overview()
            result["live_activity"] = self.activity
            result["monitor_received_at"] = self.received_at
            return result


def make_cloud_server(*, host, port, root, username, password, ingest_key, mission):
    if not username or len(password) < 20 or len(ingest_key) < 32:
        raise ValueError("Explicit strong monitoring credentials are required")
    sources = MonitorSources(root)
    replay_nonces = deque(maxlen=128)
    last_sent_at = 0
    auth_value = "Basic " + base64.b64encode((username + ":" + password).encode()).decode()

    def authorize(handler):
        value = handler.headers.get("Authorization", "")
        if len(value) <= 1024 and hmac.compare_digest(value.encode(), auth_value.encode()):
            return True
        body = b"Authentication required"
        handler.send_response(401)
        handler.send_header("WWW-Authenticate", 'Basic realm="RoyIn monitor", charset="UTF-8"')
        handler.send_header("Cache-Control", "no-store")
        handler.send_header("Content-Length", str(len(body)))
        handler.end_headers()
        if handler.command != "HEAD":
            handler.wfile.write(body)
        return False

    origins = {"https://" + host}
    if host.startswith(("127.0.0.1:", "localhost:")):
        origins.add("http://" + host)
    base = handler_for(sources, allowed_hosts={host, "localhost:" + str(port)},
                       allowed_origins=origins, authorize=authorize)

    class Handler(base):
        def do_GET(self):
            if self.path == "/healthz":
                return self.send(200, dict(status="MONITOR_SERVER_AVAILABLE"))
            return super().do_GET()

        def do_POST(self):
            nonlocal last_sent_at
            self.close_connection = True
            if self.path != "/internal/snapshot":
                return self.reject()
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= MAX_PUSH_BYTES or self.headers.get("Transfer-Encoding"):
                    return self.send(413, dict(status="REJECTED_SIZE"))
                sent_at = int(self.headers.get("X-Royin-Time", "0"))
                nonce = self.headers.get("X-Royin-Nonce", "")
                supplied = self.headers.get("X-Royin-Signature", "")
                if abs(int(time.time()) - sent_at) > 60 or len(nonce) != 32 or len(supplied) != 64:
                    return self.send(403, dict(status="REJECTED_SIGNATURE"))
                self.connection.settimeout(5)
                body = self.rfile.read(length)
                if len(body) != length or not hmac.compare_digest(supplied, signature(ingest_key, sent_at, nonce, body)):
                    return self.send(403, dict(status="REJECTED_SIGNATURE"))
                payload = json.loads(body)
                if payload.get("schema_version") != "royin.monitor-push.v1":
                    raise ValueError("Unexpected push schema")
                snap = snapshot_view(payload["snapshot"], mission)
                activity = activity_view(payload.get("activity", {}))
                if max(stamp(snap["heartbeat_at"]), stamp(snap["observed_at"])) > int(time.time()) + 60:
                    raise ValueError("Future observation")
                with sources.state_lock:
                    if nonce in replay_nonces or sent_at < last_sent_at:
                        return self.send(409, dict(status="REJECTED_REPLAY"))
                    target = Path(root) / ".local/dashboard/engine-snapshot.json"
                    target.parent.mkdir(parents=True, exist_ok=True)
                    temporary = target.with_name("snapshot-" + secrets.token_hex(8) + ".tmp")
                    temporary.write_text(json.dumps(snap), encoding="utf-8")
                    temporary.replace(target)
                    sources.cache.clear()
                    sources.activity = activity
                    sources.received_at = int(time.time())
                    last_sent_at = sent_at
                    replay_nonces.append(nonce)
                return self.send(200, dict(status="MONITOR_SNAPSHOT_ACCEPTED"))
            except (ValueError, KeyError, TypeError, AttributeError, OSError):
                return self.send(400, dict(status="REJECTED_MONITOR_INPUT"))

    return ThreadingHTTPServer(("0.0.0.0", port), Handler)


def main():
    # No engine/account/budget environment variable is consumed by this application.
    with tempfile.TemporaryDirectory(prefix="royin-monitor-") as root:
        server = make_cloud_server(host=os.environ["MONITOR_HOST"], port=int(os.environ.get("PORT", "3000")),
                                   root=Path(root), username=os.environ["MONITOR_USERNAME"],
                                   password=os.environ["MONITOR_PASSWORD"], ingest_key=os.environ["MONITOR_INGEST_KEY"],
                                   mission=os.environ["MONITOR_MISSION"])
        server.serve_forever(poll_interval=.5)


if __name__ == "__main__":
    main()

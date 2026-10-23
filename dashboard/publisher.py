"""Bounded report-file publisher; never imports or starts the trading engine."""

import argparse
import json
import os
import secrets
import time
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlsplit

from dashboard.cloud import signature
from dashboard.monitor_snapshot import MAX_PUSH_BYTES, read_activity, read_json, snapshot_view


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def run(settings):
    import fcntl  # Linux-only publisher; importing this module remains portable for tests.

    target = urlsplit(settings["target"])
    if (target.scheme != "https" or target.hostname != "royin-monitor.liara.run"
            or target.path != "/internal/snapshot" or target.query or target.fragment
            or target.username or target.password or target.port not in (None, 443)):
        raise ValueError("Unexpected monitoring destination")
    stop_at = int(settings["stop_at"])
    if not 0 < stop_at - int(time.time()) <= 4 * 86400:
        raise ValueError("Publisher must have a finite four-day maximum lifetime")
    os.nice(10)
    root = Path(settings["mission_root"])
    snapshot = Path(settings["snapshot"])
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    with (Path(settings["control_root"]) / "publisher.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        activity, previous_stat = {}, None
        while int(time.time()) < stop_at:
            try:
                raw = snapshot_view(read_json(snapshot, 64 * 1024), settings["mission"])
                signals = root / "signals/manifest.json"
                status = signals.stat() if signals.exists() else None
                current_stat = (status.st_mtime_ns, status.st_size) if status else None
                # Audit changes are small; the large model manifest is parsed only after a change.
                if current_stat != previous_stat or not activity:
                    activity = read_activity(root)
                    previous_stat = current_stat
                else:
                    latest = read_activity_tail(root)
                    activity.update(events=latest["events"])
                payload = json.dumps(dict(schema_version="royin.monitor-push.v1", snapshot=raw,
                                          activity=activity), allow_nan=False).encode()
                if len(payload) > MAX_PUSH_BYTES:
                    raise ValueError("Monitoring push exceeds limit")
                sent_at, nonce = int(time.time()), secrets.token_hex(16)
                request = urllib.request.Request(settings["target"], data=payload, method="POST", headers={
                    "Content-Type": "application/json", "X-Royin-Time": str(sent_at), "X-Royin-Nonce": nonce,
                    "X-Royin-Signature": signature(settings["ingest_key"], sent_at, nonce, payload)})
                with opener.open(request, timeout=5) as response:
                    accepted = response.status == 200
                    response.read(1024)
                state = dict(at=int(time.time()), accepted=accepted, pid=os.getpid())
            except (ValueError, OSError, urllib.error.URLError, TypeError, AttributeError) as exc:
                state = dict(at=int(time.time()), accepted=False, error_type=type(exc).__name__, pid=os.getpid())
            (Path(settings["control_root"]) / "publisher-status.json").write_text(json.dumps(state), encoding="utf-8")
            time.sleep(30)


def read_activity_tail(root):
    # Reuse the same allowlist without reparsing the model manifest on every tick.
    from dashboard.monitor_snapshot import read_audit
    return read_audit(root)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--settings", required=True)
    args = parser.parse_args()
    run(read_json(args.settings, 8192))


if __name__ == "__main__":
    main()

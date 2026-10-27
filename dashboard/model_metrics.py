"""Read-only model telemetry; reservations, recorded SDK usage and invoices stay distinct."""

import hashlib
import json
from decimal import Decimal
from pathlib import Path

from dashboard.sources import count, decimal, digest, ident, readonly_budget

MAX_MANIFEST_BYTES = 64 * 1024 * 1024
MAX_TRACES = 1000


def metrics_view(raw):
    """Both publisher and receiver allowlist the same non-secret aggregate fields."""
    if not isinstance(raw, dict) or raw.get("schema_version") != "royin.model-metrics.v1":
        raise ValueError("Invalid model telemetry schema")
    at = raw.get("observed_at")
    if type(at) is not int or not 0 < at < 4102444800:
        raise ValueError("Invalid model telemetry timestamp")
    result = dict(schema_version="royin.model-metrics.v1", observed_at=at)
    for name in ("reservation", "usage", "model"):
        row = raw.get(name)
        if not isinstance(row, dict) or row.get("status") not in ("AVAILABLE", "EMPTY", "UNAVAILABLE", "INVALID"):
            raise ValueError("Invalid model telemetry component")
        clean = dict(status=row["status"])
        if name == "reservation":
            clean.update(amount=decimal(row.get("amount"), False),
                         requests=count(row.get("requests")), reserved_tokens=count(row.get("reserved_tokens")),
                         credit_id=ident(row.get("credit_id")), scope=ident(row.get("scope")))
            required = ("amount", "requests", "reserved_tokens")
        elif name == "usage":
            clean.update({key: count(row.get(key)) for key in
                          ("input_tokens", "output_tokens", "reported_traces", "attempted_traces")})
            clean["manifest_sha256"] = digest(row.get("manifest_sha256"))
            required = ("input_tokens", "output_tokens", "reported_traces", "attempted_traces", "manifest_sha256")
            if (clean["reported_traces"] is not None and clean["attempted_traces"] is not None
                    and clean["reported_traces"] > clean["attempted_traces"]):
                raise ValueError("Usage coverage exceeds recorded attempts")
        else:
            clean.update(provider=ident(row.get("provider")), model=ident(row.get("model")),
                         average_latency_seconds=decimal(row.get("average_latency_seconds"), False))
            clean.update({key: count(row.get(key)) for key in ("decisions", "errors", "timeouts")})
            required = ("provider", "model", "decisions", "errors", "timeouts")
        if row["status"] in ("AVAILABLE", "EMPTY") and any(clean[key] is None for key in required):
            raise ValueError("Available telemetry requires actual evidence")
        result[name] = clean
    return result


def recorded_usage(path):
    """Project actual trace usage, including valid outputs later rejected by the host."""
    with Path(path).open("rb") as stream:
        raw = stream.read(MAX_MANIFEST_BYTES + 1)
    if len(raw) > MAX_MANIFEST_BYTES:
        raise ValueError("Model telemetry manifest size bound")
    manifest = json.loads(raw)
    if manifest.get("model_mode") != "REAL_MODEL":
        raise ValueError("Telemetry requires recorded real-model attempts")
    rows = manifest["arms"]["paper_portfolio"]["decision_traces"]
    if not isinstance(rows, list) or len(rows) > MAX_TRACES:
        raise ValueError("Model telemetry trace bound")
    traces = [r for r in rows if r.get("model_trace", {}).get("evidence_kind") == "REAL_MODEL_ATTEMPT"]
    reported, inputs, outputs, errors, timeouts = 0, 0, 0, 0, 0
    latencies, providers, models = [], set(), set()
    for row in traces:
        trace = row["model_trace"]
        providers.add(ident(trace.get("provider")))
        models.add(ident(trace.get("model")))
        usage = trace.get("usage")
        if isinstance(usage, dict):
            incoming, outgoing = count(usage.get("input_tokens")), count(usage.get("output_tokens"))
            if incoming is not None and outgoing is not None:
                inputs += incoming
                outputs += outgoing
                reported += 1
        errors += trace.get("host_outcome") == "HOST_FALLBACK"
        timeouts += (row.get("decision") or {}).get("reason") == "WAIT: Model inference timed out"
        latency = trace.get("elapsed_seconds")
        if latency is not None:
            latencies.append(Decimal(decimal(str(latency), False)))
    usage = dict(status="AVAILABLE" if reported else "UNAVAILABLE",
                 input_tokens=inputs if reported else None, output_tokens=outputs if reported else None,
                 reported_traces=reported, attempted_traces=len(traces), manifest_sha256=hashlib.sha256(raw).hexdigest())
    model = dict(status="AVAILABLE" if len(providers) == len(models) == 1 and None not in providers | models else "UNAVAILABLE",
                 provider=next(iter(providers)) if len(providers) == 1 else None,
                 model=next(iter(models)) if len(models) == 1 else None,
                 decisions=len(traces), errors=errors, timeouts=timeouts,
                 average_latency_seconds=str(sum(latencies) / len(latencies)) if latencies else None)
    return usage, model


class ModelMetricsReader:
    """One bounded read-only DB transaction per push; large traces reparse only on change."""

    def __init__(self, manifest, budget, credit_id):
        self.manifest, self.budget, self.credit_id = Path(manifest), Path(budget), credit_id
        self.signature, self.cached = None, None

    def read(self, now):
        try:
            status = self.manifest.stat()
            signature = (status.st_mtime_ns, status.st_size)
            if signature != self.signature or self.cached is None:
                self.cached = recorded_usage(self.manifest)
                self.signature = signature
            usage, model = self.cached
        except (OSError, ValueError, KeyError, TypeError, AttributeError):
            usage, model = dict(status="UNAVAILABLE"), dict(status="UNAVAILABLE")
        return metrics_view(dict(schema_version="royin.model-metrics.v1", observed_at=now,
                                 reservation=readonly_budget(self.budget, credit_id=self.credit_id),
                                 usage=usage, model=model))

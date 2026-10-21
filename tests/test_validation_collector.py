import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from scripts import collect_validation_data as collector


class CollectorTests(unittest.TestCase):
    def test_three_get_plan_and_native_disagreement_rejects_day(self):
        for mismatch in (False, True):
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                protocol = {
                    "public_get_cap": 3,
                    "symbols": ["USDTTMN"],
                    "first_day_including_warmup": "2026-09-14",
                    "end_exclusive": "2026-09-15",
                    "rate_spacing_seconds": 0,
                }
                protocol_path = root / "protocol.json"
                protocol_path.write_text(json.dumps(protocol))
                calls = []

                def fetch(client, endpoint, query, directory, calls=calls, mismatch=mismatch):
                    calls.append((endpoint, query))
                    if endpoint.endswith("markets"):
                        return {}, {}
                    step = 60 if query["resolution"] == "1" else 3600
                    times = list(range(query["from"], query["to"], step))
                    n = len(times)
                    payload = {
                        "s": "ok",
                        "t": times,
                        "o": ["100"] * n,
                        "h": ["102" if mismatch and step == 3600 else "101"] * n,
                        "l": ["99"] * n,
                        "c": ["100"] * n,
                        "v": ["1" if step == 60 else "60"] * n,
                    }
                    return payload, {
                        "source_url": "https://api.wallex.ir/v1/udf/history",
                        "query": query,
                    }

                with (
                    patch.object(collector, "ROOT", root),
                    patch.object(collector, "fetch_public", fetch),
                    patch.object(
                        collector,
                        "parse_catalog",
                        return_value={
                            "USDTTMN": SimpleNamespace(
                                is_spot=True, base_asset="USDT", quote_asset="TMN"
                            )
                        },
                    ),
                    patch.object(collector, "load_restrictions", return_value=frozenset()),
                ):
                    status = collector.main(["--protocol", str(protocol_path)])
                self.assertEqual(len(calls), 3)
                self.assertEqual(status, 2 if mismatch else 0)
                report = json.loads(
                    next((root / "data/validation").glob("*/manifest.json")).read_text()
                )
                self.assertEqual(len(report["datasets"]), 0 if mismatch else 1)

    def test_plan_larger_than_cap_rejects_before_network(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "p.json"
            path.write_text(
                json.dumps(
                    {
                        "public_get_cap": 2,
                        "symbols": ["USDTTMN"],
                        "first_day_including_warmup": "2026-09-14",
                        "end_exclusive": "2026-09-15",
                    }
                )
            )
            with patch.object(collector, "fetch_public") as fetch:
                with self.assertRaises(ValueError):
                    collector.main(["--protocol", str(path)])
                fetch.assert_not_called()

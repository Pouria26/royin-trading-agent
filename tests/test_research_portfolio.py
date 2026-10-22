"""Synthetic trust-boundary fixtures; they never attest a real provider response."""

import copy
import hashlib
import json
import tempfile
import unittest
from dataclasses import asdict, replace
from datetime import UTC, datetime
from decimal import Decimal as D
from pathlib import Path
from unittest.mock import patch

from royin.evaluation import (
    buy_and_hold_decision,
    portfolio_bindings,
    recorded_portfolio_producer,
    run_simulation,
)
from royin.features import extract_features
from royin.market_data import Candle, CandleSeries
from royin.risk import MarketRules, RiskPolicy
from scripts.evaluate_portfolio_ai import synthetic_scenario
from scripts.research_portfolio import (
    diagnostic_report,
    load_real_lineage,
    load_research_inputs,
    prepare_pilot,
    validate_assumptions,
)


def assumptions():
    return dict(
        binding_stage="TEMPORARY_LOGIC_ONLY_NOT_FINAL_FREEZE",
        purpose="DIAGNOSTIC_EXPOSED_NOT_HOLDOUT",
        ai_role="FULL_DECISION_PROPOSAL_NOT_VETO",
        time_label_assumption="INTERVAL_START_UNVERIFIED",
        finality_assumption="CAPTURED_CLOSED_NOT_EXCHANGE_FINALITY",
        price_unit="TMN_PER_USDT",
        volume_asset_assumption="BASE_USDT_UNVERIFIED_DIAGNOSTIC",
        registered_at_utc=datetime.now(UTC).isoformat(),
        initial_capital_tmn="5000000",
        max_order_tmn="1500000",
        max_exposure_tmn="3000000",
        stop_loss_pct=".02",
        max_drawdown_pct=".05",
        synthetic_market_rules=dict(
            tick_size="1", step_size=".01", min_quantity="1", min_notional="100000"
        ),
        cost_scenarios=[
            dict(name="base", taker_fee=".003", slippage=".0005"),
            dict(name="higher_cost", taker_fee=".006", slippage=".002"),
        ],
    )


class ResearchInputTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.addCleanup(self.temp.cleanup)
        (self.root / "config").mkdir()
        self.write(
            "config/wallex-credit-market-policy.json",
            dict(
                schema_version=1, market_type="SPOT", leverage_allowed=False, unavailable_markets=[]
            ),
        )
        self.plan = self.root / "assumptions.json"
        self.write("assumptions.json", assumptions())

    def write(self, name, value):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        raw = (json.dumps(value, default=str, sort_keys=True) + "\n").encode()
        path.write_bytes(raw)
        return hashlib.sha256(raw).hexdigest()

    def inputs(self, segments=None):
        segments = segments or [synthetic_scenario()[0]]
        catalog = dict(
            success=True,
            result=dict(
                markets=[
                    dict(
                        symbol="USDTTMN",
                        base_asset="USDT",
                        quote_asset="TMN",
                        is_spot=True,
                        amount_precision=2,
                        price_precision=0,
                    )
                ]
            ),
        )
        csha = self.write("catalog.json", catalog)
        catalog_source = dict(
            source_url="https://api.wallex.ir/hector/web/v1/markets",
            query={},
            raw_file="catalog.json",
            raw_sha256=csha,
            fetched_at_utc="2026-10-21T00:00:00Z",
        )
        requests, records = [dict(source=catalog_source)], []
        for i, candles in enumerate(segments):
            query = dict(
                symbol="USDTTMN",
                resolution="60",
                **{"from": candles[0].open_time, "to": candles[-1].open_time + 3600},
            )
            raw = dict(s="ok", t=[c.open_time for c in candles])
            raw.update(
                {
                    k: [str(getattr(c, f)) for c in candles]
                    for k, f in zip(
                        "ohlcv", ("open", "high", "low", "close", "volume"), strict=True
                    )
                }
            )
            rsha = self.write(f"raw{i}.json", raw)
            source = dict(
                source_url="https://api.wallex.ir/v1/udf/history",
                query=query,
                raw_file=f"raw{i}.json",
                raw_sha256=rsha,
                fetched_at_utc="2026-10-21T00:00:00Z",
            )
            requests.append(dict(source=source))
            data = dict(
                symbol="USDTTMN",
                base_asset="USDT",
                quote_asset="TMN",
                interval_seconds=3600,
                source_contract="WALLEX_NATIVE_60_SOURCE_V1",
                cutoff=query["to"],
                incomplete_bins=[],
                sources=[source],
                candles=[asdict(c) for c in candles],
            )
            digest = self.write(f"normalized{i}.json", data)
            records.append(
                dict(
                    path=f"normalized{i}.json",
                    sha256=digest,
                    symbol="USDTTMN",
                    interval_seconds=3600,
                    start=query["from"],
                    end=query["to"],
                    status="ACCEPTED",
                )
            )
        parent_sha = self.write("capture.json", dict(requests=requests))
        self.manifest = dict(
            contract_id="WALLEX_NATIVE_60_SOURCE_V1",
            parent_capture_path="capture.json",
            parent_capture_sha256=parent_sha,
            catalog=catalog_source,
            datasets=records,
        )
        digest = self.write("manifest.json", self.manifest)
        return self.root / "manifest.json", digest

    def test_raw_reconciliation_and_explicit_unknown_units(self):
        path, digest = self.inputs()
        _, datasets = load_research_inputs(path, digest, root=self.root)
        self.assertEqual(len(datasets[0][2]), 64)
        data = json.loads((self.root / "normalized0.json").read_text())
        data["candles"][0]["close"] = str(D(data["candles"][0]["close"]) + 1)
        self.manifest["datasets"][0]["sha256"] = self.write("normalized0.json", data)
        digest = self.write("manifest.json", self.manifest)
        with self.assertRaisesRegex(ValueError, "complete raw coverage"):
            load_research_inputs(path, digest, root=self.root)
        for field in ("price_unit", "volume_asset_assumption", "time_label_assumption"):
            plan = assumptions()
            plan[field] = "UNKNOWN"
            with self.subTest(field=field), self.assertRaises(ValueError):
                validate_assumptions(plan)

    def test_two_segments_preserve_gap_and_internal_gap_future_reject(self):
        candles = synthetic_scenario()[0]
        path, digest = self.inputs([candles[:35], candles[36:]])
        _, datasets = load_research_inputs(path, digest, root=self.root)
        self.assertEqual([len(c) for _, _, c in datasets], [35, 28])
        self.assertEqual(datasets[1][2][0].open_time - datasets[0][2][-1].open_time, 7200)
        for bad in [candles[:35] + candles[36:], [replace(candles[0], open_time=4102444800)]]:
            path, digest = self.inputs([bad])
            with self.assertRaises(ValueError):
                load_research_inputs(path, digest, root=self.root)

    def test_bar_must_be_closed_at_capture_not_merely_closed_today(self):
        path, _ = self.inputs()
        data = json.loads((self.root / "normalized0.json").read_text())
        source = data["sources"][0]
        source["fetched_at_utc"] = datetime.fromtimestamp(
            data["candles"][0]["open_time"] + 30, UTC
        ).isoformat()
        capture = json.loads((self.root / "capture.json").read_text())
        capture["requests"][1]["source"] = source
        self.manifest["parent_capture_sha256"] = self.write("capture.json", capture)
        self.manifest["datasets"][0]["sha256"] = self.write("normalized0.json", data)
        digest = self.write("manifest.json", self.manifest)
        with self.assertRaisesRegex(ValueError, "Future/open"):
            load_research_inputs(path, digest, root=self.root)

    def test_market_deny_and_hash_mismatch_fail_before_model(self):
        path, digest = self.inputs()
        with self.assertRaisesRegex(ValueError, "Hash mismatch"):
            load_research_inputs(path, "0" * 64, root=self.root)
        self.write(
            "config/wallex-credit-market-policy.json",
            dict(
                schema_version=1,
                market_type="SPOT",
                leverage_allowed=False,
                unavailable_markets=["USDT/TMN"],
            ),
        )
        with self.assertRaisesRegex(ValueError, "market policy"):
            load_research_inputs(path, digest, root=self.root)

    def test_real_arm_is_blocked_and_fake_never_supplies_its_curve(self):
        path, digest = self.inputs()
        with patch("httpx.Client.request", side_effect=AssertionError("network forbidden")):
            result = diagnostic_report(path, digest, self.plan, root=self.root)
        scenario = result["datasets"][0]["cost_scenarios"]["base"]
        self.assertEqual(scenario["arms"]["rule_ai"]["status"], "BLOCKED_RECORDED_AI")
        self.assertIsNone(scenario["arms"]["rule_ai"]["equity_curve"])
        self.assertEqual(scenario["fake_wiring_arm"]["evidence_kind"], "FAKE_MODEL")
        self.assertEqual(result["primary_status"], "BLOCKED_DATA")
        self.assertIsNone(result["selected_candidate"])
        orders = {o["client_id"] for o in scenario["arms"]["rule"]["orders"]}
        linked = {
            t["client_id"] for t in scenario["arms"]["rule"]["decision_traces"] if t["client_id"]
        }
        self.assertTrue(linked.issubset(orders))

    def test_pilot_preparation_is_twelve_own_state_cutoffs_without_calling_model(self):
        path, digest = self.inputs()
        with patch(
            "scripts.research_portfolio.fake_portfolio_producer",
            side_effect=AssertionError("no model during proposal"),
        ):
            result = prepare_pilot(path, digest, self.plan, root=self.root)
        self.assertEqual(result["maximum_decisions"], 12)
        self.assertEqual(result["maximum_http_requests"], 24)
        self.assertEqual(D(result["maximum_reserved_usd"]), D(".04"))
        self.assertEqual(result["first_snapshot"]["available_tmn_cash"], "5000000")
        self.assertEqual(len(result["decision_cutoffs"]), 12)
        self.assertEqual(result["paid_requests"], 0)


class RecordedLineageTests(unittest.TestCase):
    def test_legacy_real_label_cannot_bypass_reviewed_v2_importer(self):
        from royin.agent import SYSTEM_INSTRUCTIONS
        from royin.evaluation import evaluate_strategy_suite

        candles, rules, policy = synthetic_scenario()
        snap = extract_features(
            CandleSeries(tuple(candles[:31]), 3600),
            "USDTTMN",
            cutoff=candles[30].open_time + 3600,
            available_tmn_cash=D(5000000),
        )
        manifest = dict(
            prompt_sha256=hashlib.sha256(SYSTEM_INSTRUCTIONS.encode()).hexdigest(),
            model="gpt-6-luna",
            data_sha256=hashlib.sha256(
                json.dumps([asdict(c) for c in candles], default=str, sort_keys=True).encode()
            ).hexdigest(),
            config_sha256=hashlib.sha256(
                repr((rules, policy, D(5000000), 3600)).encode()
            ).hexdigest(),
        )
        record = dict(
            source="REAL_MODEL",
            manifest=manifest,
            snapshot_sha256=snap.snapshot_sha256,
            snapshot=snap.to_canonical_dict(),
        )
        with self.assertRaisesRegex(ValueError, "Legacy REAL_MODEL records lack reviewed V2"):
            evaluate_strategy_suite(
                candles, rules, policy, interval_seconds=3600, ai_records=[record]
            )

    def test_best_episode_attribution_uses_independent_flat_price_fee_oracle(self):
        candles = [
            Candle(1700002800 + i * 3600, D(100), D(101), D(99), D(100), D(100)) for i in range(40)
        ]
        rules = MarketRules(
            "USDTTMN", "USDT", "TMN", D(1), D(".01"), D(1), D(".01"), D(".003"), D(".003")
        )
        policy = RiskPolicy(D(100), D(100), D(".02"), D(".05"), candles[-1].open_time + 3600)
        result = run_simulation(
            candles,
            buy_and_hold_decision,
            rules,
            policy,
            initial_capital=D(1000),
            interval_seconds=3600,
            slippage_pct=D(0),
            enable_logging=False,
        )
        # Budget100 -> qty0.99; buy/sell at100, each fee0.297 => loss0.594.
        self.assertEqual(D(result["final_equity_mtm_tmn"]), D("999.406"))
        self.assertEqual(D(result["best_closed_episode_pnl_tmn"]), D("-.594"))
        self.assertEqual(D(result["best_closed_episode_fraction_of_net_pnl"]), D(1))
        self.assertEqual(D(result["net_return_without_best_closed_episode_pct"]), D(0))

    def test_one_word_fake_to_real_relabel_is_rejected(self):
        candles, rules, policy = synthetic_scenario()
        expected = portfolio_bindings(candles, rules, policy, D(5000000), 3600, D(".0005"))
        record = dict(
            source="REAL_MODEL",
            origin_kind="SDK_TEST_MODEL",
            manifest=expected,
            snapshot_sha256="a" * 64,
        )
        for lineage in (None, {"anything": {}}):
            with self.assertRaises(ValueError):
                recorded_portfolio_producer(
                    [record], expected, source="REAL_MODEL", real_lineage=lineage
                )

    def test_reviewed_response_bytes_and_output_must_match_exact_state(self):
        # Handwritten provider-shaped fixture: proves the importer, never an actual paid model.
        from royin.agent import SYSTEM_INSTRUCTIONS
        from royin.evaluation import always_wait_decision

        candles, rules, policy = synthetic_scenario()
        expected = portfolio_bindings(candles, rules, policy, D(5000000), 3600, D(".0005"))
        snap = extract_features(
            CandleSeries(tuple(candles[:31]), 3600),
            "USDTTMN",
            cutoff=candles[30].open_time + 3600,
            available_tmn_cash=D(5000000),
        )
        dec = always_wait_decision(snap)
        proposal = {
            k: getattr(dec, k) for k in ("action", "evidence_ids", "reason", "invalidation")
        }
        response = dict(
            object="chat.completion",
            id="synthetic-completion-not-provider-evidence",
            model="gpt-6-luna",
            choices=[
                dict(
                    finish_reason="tool_calls",
                    message=dict(
                        tool_calls=[
                            dict(function=dict(name="final_result", arguments=json.dumps(proposal)))
                        ]
                    ),
                )
            ],
        )
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            body = json.dumps(response).encode()
            digest = hashlib.sha256(body).hexdigest()
            (root / "response.json").write_bytes(body)
            prompt = f"Evaluate market snapshot for USDTTMN at cutoff {snap.cutoff}."
            messages = [
                dict(role="system", content=SYSTEM_INSTRUCTIONS),
                dict(role="user", content=prompt),
            ]
            first = dict(
                model="gpt-6-luna",
                reasoning_effort="none",
                max_completion_tokens=512,
                messages=messages,
            )
            second = dict(
                first,
                messages=[
                    *messages,
                    dict(
                        role="assistant",
                        tool_calls=[
                            dict(
                                id="read1",
                                function=dict(name="read_market_snapshot", arguments="{}"),
                            )
                        ],
                    ),
                    dict(
                        role="tool",
                        tool_call_id="read1",
                        content=json.dumps(snap.to_canonical_dict()),
                    ),
                ],
            )
            request_bytes = json.dumps([first, second]).encode()
            request_sha = hashlib.sha256(request_bytes).hexdigest()
            (root / "requests.json").write_bytes(request_bytes)
            entry = dict(
                request_file="requests.json",
                request_sha256=request_sha,
                response_file="response.json",
                response_sha256=digest,
                manifest=expected,
                snapshot_sha256=snap.snapshot_sha256,
                decision=dec.model_dump(mode="json"),
                request=dict(
                    system_instructions=SYSTEM_INSTRUCTIONS,
                    user_prompt=f"Evaluate market snapshot for USDTTMN at cutoff {snap.cutoff}.",
                    snapshot=snap.to_canonical_dict(),
                ),
            )
            raw = json.dumps(
                dict(
                    review_status="INDEPENDENTLY_REVIEWED",
                    reviewer_ref="SYNTHETIC_TEST_ONLY",
                    responses=[entry],
                )
            ).encode()
            path = root / "review.json"
            path.write_bytes(raw)
            lineage = load_real_lineage(path, hashlib.sha256(raw).hexdigest())
            record = dict(
                source="REAL_MODEL",
                origin_kind="REAL_MODEL_PROVIDER_RESPONSE",
                manifest=expected,
                snapshot_sha256=snap.snapshot_sha256,
                snapshot=snap.to_canonical_dict(),
                decision=dec.model_dump(mode="json"),
                response_sha256=digest,
                request_sha256=request_sha,
            )
            producer = recorded_portfolio_producer(
                [record], expected, source="REAL_MODEL", real_lineage=lineage
            )
            self.assertEqual(producer(snap).action, "WAIT")
            altered = copy.deepcopy(lineage)
            altered[digest]["request"]["snapshot"]["available_tmn_cash"] = "1"
            with self.assertRaises(ValueError):
                recorded_portfolio_producer(
                    [record], expected, source="REAL_MODEL", real_lineage=altered
                )
            (root / "response.json").write_bytes(b"{}")
            with self.assertRaises(ValueError):
                load_real_lineage(path, hashlib.sha256(raw).hexdigest())

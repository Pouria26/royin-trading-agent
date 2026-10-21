"""Independent monetary and temporal oracles; all credentials/data are synthetic."""

import hashlib
import json
import tempfile
import unittest
from decimal import Decimal as D
from pathlib import Path
from unittest.mock import patch

import httpx2
from test_agent_regressions import _make_dummy_snapshot

from royin.agent import decide
from royin.broker import PaperBroker
from royin.config import RuntimeConfig
from royin.ledger import Ledger
from royin.market_data import Candle
from royin.risk import MarketRules, RiskResult


def rules():
    return MarketRules(
        "USDTTMN", "USDT", "TMN", D("0.01"), D("0.01"), D("1"), D("0.01"), D("0.0025"), D("0.003")
    )


def intent(action="ENTER", price="100", quantity="1", stop=None):
    return RiskResult(
        True,
        "synthetic",
        action,
        "USDTTMN",
        D(quantity),
        D(price),
        D(stop) if stop else None,
        D(price) * D(quantity) * D("0.003"),
    )


def bar(t=2000):
    return Candle(t, D("100"), D("110"), D("90"), D("100"), D("100"))


class ExecutionOracles(unittest.TestCase):
    def test_unknown_limit_cannot_reconcile_at_a_worse_price(self):
        ledger = Ledger()
        ledger.set_balance("TMN", D("1000"))
        broker = PaperBroker(ledger, rules())
        broker.submit_order(intent(), client_id="unknown", timestamp=1000, simulate_unknown=True)
        with self.assertRaises(ValueError):
            broker.reconcile_order(
                "unknown", simulated_state="FILLED", timestamp=2000, executed_price=D("101")
            )

    def test_limit_friction_does_not_create_price_improvement(self):
        for side in ("ENTER", "EXIT"):
            for slip in ("0", "0.01"):
                ledger = Ledger()
                ledger.set_balance("TMN", D("1000"))
                ledger.set_balance("USDT", D("1"))
                broker = PaperBroker(ledger, rules())
                broker.submit_order(intent(side), client_id="fixed", timestamp=1000)
                broker.process_candle(bar(), slippage_pct=D(slip))
                self.assertEqual(broker.orders["fixed"].price, D("100"))

    def test_order_inside_candle_cannot_use_earlier_extrema(self):
        ledger = Ledger()
        ledger.set_balance("TMN", D("1000"))
        broker = PaperBroker(ledger, rules())
        broker.submit_order(intent(), client_id="late", timestamp=1010)
        self.assertNotIn("late", broker.process_candle(bar(1000)))
        self.assertEqual(ledger.get_balance("USDT").total, 0)

    def test_committed_fill_recovers_broker_state_and_stop(self):
        with tempfile.TemporaryDirectory() as tmp:
            ledger = Ledger(Path(tmp) / "ledger.sqlite")
            ledger.set_balance("TMN", D("1000"))
            broker = PaperBroker(ledger, rules())
            broker.submit_order(intent(stop="95"), client_id="crash", timestamp=1000)
            # Crash after ledger commit, before broker's in-memory/status update.
            ledger.record_fill(
                fill_id="fill_crash",
                client_id="crash",
                price=D("100"),
                quantity=D("1"),
                fee=D("0.3"),
                fee_asset="TMN",
                timestamp=2900,
            )
            restarted = PaperBroker(Ledger(Path(tmp) / "ledger.sqlite"), rules())
            self.assertEqual(restarted.orders["crash"].status, "FILLED")
            restarted.process_candle(Candle(3000, D("100"), D("101"), D("99"), D("100"), D("100")))
            self.assertEqual(ledger.get_balance("USDT").total, 1)
            self.assertEqual(restarted.active_stop_prices["USDTTMN"], D("95"))

    def test_sell_base_fee_consumes_inventory_and_basis(self):
        ledger = Ledger()
        ledger.set_balance("TMN", D("1000"))
        ledger.record_intent(
            client_id="b",
            symbol="USDTTMN",
            side="BUY",
            order_type="LIMIT",
            price=D("100"),
            quantity=D("2"),
            timestamp=1000,
        )
        ledger.record_fill(
            fill_id="b",
            client_id="b",
            price=D("100"),
            quantity=D("2"),
            fee=D("0"),
            fee_asset="TMN",
            timestamp=1001,
        )
        ledger.record_intent(
            client_id="s",
            symbol="USDTTMN",
            side="SELL",
            order_type="LIMIT",
            price=D("120"),
            quantity=D("1"),
            timestamp=1002,
        )
        ledger.record_fill(
            fill_id="s",
            client_id="s",
            price=D("120"),
            quantity=D("1"),
            fee=D("0.1"),
            fee_asset="USDT",
            timestamp=1003,
        )
        self.assertEqual(ledger.get_balance("USDT").total, D("0.9"))
        self.assertEqual(ledger.get_realized_pnl(), D("10"))  # 120 - 1.1*100

    def test_partial_fill_restart_only_matches_remaining_quantity(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "l.sqlite"
            ledger = Ledger(path)
            ledger.set_balance("TMN", D("1000"))
            broker = PaperBroker(ledger, rules())
            broker.submit_order(intent(quantity="2"), client_id="partial", timestamp=1000)
            ledger.record_fill(
                fill_id="partial_first",
                client_id="partial",
                price=D("100"),
                quantity=D("0.5"),
                fee=D("0.15"),
                fee_asset="TMN",
                timestamp=1100,
            )
            restored = PaperBroker(Ledger(path), rules())
            restored.process_candle(bar())
            self.assertEqual(ledger.get_balance("USDT").total, D("2"))
            self.assertEqual(ledger.get_balance("TMN").free, D("799.4"))
            restored.process_candle(bar(3000))
            self.assertEqual(ledger.get_balance("USDT").total, D("2"))


class BudgetOracle(unittest.IsolatedAsyncioTestCase):
    async def test_injected_network_client_cannot_bypass_budget(self):
        with patch.object(
            httpx2.AsyncClient, "send", side_effect=AssertionError("offline spy")
        ) as send:
            async with httpx2.AsyncClient() as client:
                with self.assertRaises(ValueError):
                    await decide(_make_dummy_snapshot(), config=RuntimeConfig(), client=client)
            send.assert_not_called()

    async def test_provider_failure_logs_safe_fallback_without_raw_exception(self):
        from royin.logger import AuditLogger

        secret = "12345|synthetic-exception-only"

        def fail(request):
            raise httpx2.RequestError("api_key=" + secret)

        with tempfile.TemporaryDirectory() as tmp, AuditLogger(Path(tmp), False) as audit:
            async with httpx2.AsyncClient(transport=httpx2.MockTransport(fail)) as client:
                with self.assertLogs("royin.agent", level="ERROR") as logs:
                    decision = await decide(
                        _make_dummy_snapshot(), config=RuntimeConfig(), client=client, audit=audit
                    )
            self.assertEqual(decision.action, "WAIT")
            text = audit.audit_path.read_text() + str(logs.output)
            self.assertNotIn(secret, text)
            self.assertIn("HOST_FALLBACK", text)


class MetricOracles(unittest.TestCase):
    def test_partial_exits_are_one_completed_position_and_fees_not_subtracted_twice(self):
        from royin.evaluation import position_metrics

        ledger = Ledger()
        ledger.set_balance("TMN", D("1000"))
        for cid, side, qty, price, fee in [
            ("b", "BUY", "2", "100", "2"),
            ("s1", "SELL", "1", "120", "1.2"),
            ("s2", "SELL", "1", "110", "1.1"),
        ]:
            ledger.record_intent(
                client_id=cid,
                symbol="USDTTMN",
                side=side,
                order_type="LIMIT",
                price=D(price),
                quantity=D(qty),
                quote_fee_reserve=D(fee),
                timestamp=1000,
            )
            ledger.record_fill(
                fill_id=cid,
                client_id=cid,
                price=D(price),
                quantity=D(qty),
                fee=D(fee),
                fee_asset="TMN",
                timestamp=1001,
            )
        m = position_metrics(ledger, rules())
        self.assertEqual(m["closed_round_trips"], 1)
        self.assertEqual(m["sell_fills"], 2)
        self.assertEqual(m["round_trip_pnls"], ["25.7"])  # 230 - 200 - 2 - 1.2 - 1.1
        self.assertIsNone(m["profit_factor"])
        self.assertEqual(m["profit_factor_status"], "NO_LOSSES")
        self.assertEqual(ledger.get_balance("TMN").free, D("1025.7"))

    def test_no_trades_are_undefined_not_a_zero_percent_win_rate(self):
        from royin.evaluation import position_metrics

        m = position_metrics(Ledger(), rules())
        self.assertIsNone(m["profit_factor"])
        self.assertIsNone(m["win_rate_pct"])
        self.assertEqual(m["metric_sample_n"], 0)

    def test_final_fee_is_in_drawdown_and_fixed_path_costs_are_monotone(self):
        from royin.evaluation import buy_and_hold_decision, run_simulation
        from royin.risk import RiskPolicy

        candles = [
            Candle(100000 + i * 900, D("100"), D("101"), D("99"), D("100"), D("100"))
            for i in range(40)
        ]
        policy = RiskPolicy(D("100"), D("100"), D(".02"), D(".05"), 200000)
        base = run_simulation(
            candles,
            buy_and_hold_decision,
            rules(),
            policy,
            initial_capital=D("1000"),
            passive=True,
            slippage_pct=D(0),
        )
        stress = run_simulation(
            candles,
            buy_and_hold_decision,
            rules(),
            policy,
            initial_capital=D("1000"),
            passive=True,
            slippage_pct=D(".01"),
        )
        self.assertEqual(D(base["max_drawdown_pct"]), D("0.0594"))
        self.assertEqual(D(base["net_return_pct"]), D("-0.0594"))
        self.assertLessEqual(D(stress["net_return_pct"]), D(base["net_return_pct"]))
        self.assertEqual(base["buy_fills"], 1)
        self.assertEqual(base["sell_fills"], 1)
        self.assertEqual(base["closed_round_trips"], 1)


class DatasetOracles(unittest.TestCase):
    def test_manifest_excludes_rejected_deduplicates_and_binds_hash(self):
        from royin.datasets import accepted_datasets

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            data = {
                "symbol": "USDTTMN",
                "base_asset": "USDT",
                "quote_asset": "TMN",
                "interval_seconds": 900,
                "cutoff": 1900,
                "candles": [
                    {
                        "open_time": 1000,
                        "open": "100",
                        "high": "101",
                        "low": "99",
                        "close": "100",
                        "volume": "10",
                    }
                ],
            }
            raw = json.dumps(data).encode()
            (root / "d.json").write_bytes(raw)
            row = {
                "path": "d.json",
                "sha256": hashlib.sha256(raw).hexdigest(),
                "symbol": "USDTTMN",
                "interval_seconds": 900,
                "start": 1000,
                "end": 1900,
                "status": "ACCEPTED",
            }
            manifest = {
                "schema_version": 1,
                "datasets": [row, row, {"status": "REJECTED", "path": "missing.json"}],
            }
            (root / "m.json").write_text(json.dumps(manifest))
            self.assertEqual(len(accepted_datasets(root / "m.json")), 1)
            (root / "d.json").write_bytes(raw + b" ")
            with self.assertRaises(ValueError):
                accepted_datasets(root / "m.json")

    def test_invalid_ohlc_future_duplicate_gap_rejected(self):
        from royin.datasets import validate_candles

        for candles in (
            [bar(1000), bar(1000)],
            [bar(1000), bar(3000)],
            [Candle(1000, D("100"), D("99"), D("90"), D("100"), D("10"))],
            [bar(3000)],
        ):
            with self.assertRaises(ValueError):
                validate_candles(candles, 900, now=3000)


class AuditPathOracle(unittest.TestCase):
    def test_offline_causal_path_and_risk_rejection(self):
        from royin.decision import Decision
        from royin.evaluation import run_simulation
        from royin.logger import AuditLogger
        from royin.risk import RiskPolicy

        candles = [
            Candle(100000 + i * 900, D("100"), D("101"), D("99"), D("100"), D("100"))
            for i in range(40)
        ]
        count = 0

        def producer(snap):
            nonlocal count
            count += 1
            return Decision(
                decision_id=f"d{count}",
                symbol=snap.symbol,
                cutoff=snap.cutoff,
                snapshot_sha256="f" * 64 if count == 1 else snap.snapshot_sha256,
                action="ENTER" if count <= 2 else "WAIT",
                evidence_ids=("EV_DATA_FRESH",),
                reason="synthetic path test",
                invalidation="next closed bar",
            )

        with (
            tempfile.TemporaryDirectory() as tmp,
            AuditLogger(Path(tmp), False, source="SYNTHETIC") as audit,
        ):
            run_simulation(
                candles,
                producer,
                rules(),
                RiskPolicy(D("100"), D("100"), D(".02"), D(".05"), 200000),
                audit=audit,
            )
            events = [json.loads(s) for s in audit.audit_path.read_text().splitlines()]
            types = {e["event_type"] for e in events}
            self.assertTrue(
                {
                    "DATA_ACCEPTED",
                    "SNAPSHOT",
                    "HOST_DECISION",
                    "RISK_REJECTED",
                    "RISK_APPROVED",
                    "INTENT",
                    "FILL",
                    "LEDGER_RECONCILIATION",
                    "FINALIZATION",
                    "RESIDUAL",
                }
                <= types
            )
            buy_fill = next(
                e for e in events if e["event_type"] == "FILL" and e["payload"]["side"] == "BUY"
            )
            self.assertEqual(buy_fill["context"]["decision_id"], "d2")
            self.assertEqual(len({e["run_id"] for e in events}), 1)


class RecordedAIOracle(unittest.TestCase):
    def test_snapshot_from_another_cash_path_is_never_reused(self):
        from dataclasses import asdict

        from royin.agent import SYSTEM_INSTRUCTIONS
        from royin.evaluation import evaluate_strategy_suite
        from royin.features import extract_features
        from royin.market_data import CandleSeries
        from royin.risk import RiskPolicy

        candles = [
            Candle(100000 + i * 900, D("100"), D("101"), D("99"), D("100"), D("100"))
            for i in range(40)
        ]
        policy = RiskPolicy(D("100"), D("100"), D(".02"), D(".05"), 200000)
        # A deliberately synthetic fixture pretending to be an imported record must still fail state matching.
        snap = extract_features(
            CandleSeries(tuple(candles[:31]), 900),
            "USDTTMN",
            cutoff=candles[30].open_time + 900,
            available_tmn_cash=D("4000000"),
        )
        record = {
            "source": "REAL_MODEL",
            "snapshot_sha256": snap.snapshot_sha256,
            "snapshot": snap.to_canonical_dict(),
            "manifest": {
                "prompt_sha256": hashlib.sha256(SYSTEM_INSTRUCTIONS.encode()).hexdigest(),
                "model": "gpt-6-luna",
                "data_sha256": hashlib.sha256(
                    json.dumps([asdict(c) for c in candles], default=str, sort_keys=True).encode()
                ).hexdigest(),
                "config_sha256": hashlib.sha256(
                    repr((rules(), policy, D("5000000"), 900)).encode()
                ).hexdigest(),
            },
        }
        with self.assertRaisesRegex(ValueError, "exact position/cash"):
            evaluate_strategy_suite(candles, rules(), policy, ai_records=[record])


if __name__ == "__main__":
    unittest.main()

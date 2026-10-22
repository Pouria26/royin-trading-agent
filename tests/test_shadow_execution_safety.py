"""Closed-candidate and durable paper recovery checks; no strategy approval."""

import contextlib
import io
import json
import tempfile
import unittest
from decimal import Decimal as D
from pathlib import Path
from unittest.mock import patch

import httpx
import test_historical_validation as fixtures

from royin.broker import PaperBroker
from royin.ledger import Ledger
from royin.market_data import Candle
from scripts.run_shadow import PublicMarketFeed, main, run_shadow_loop


class ShadowExecutionSafetyTests(unittest.TestCase):
    def test_any_approval_artifact_still_cannot_open_candidate_before_io(self):
        fields = ["code", "config", "plan", "source", "dataset", "prompt", "model"]
        approval = {
            "status": "APPROVED",
            "bindings": {k: "a" * 64 for k in fields},
            "symbol": "USDTTMN",
            "timeframe_seconds": 3600,
            "valid_until_utc": "2026-10-23T20:20:00Z",
            "acceptance": "ACCEPTED",
        }
        # Universal deny is intentional. This does not claim an accepting hash validator exists.
        with tempfile.TemporaryDirectory() as temp:
            artifact = Path(temp) / "approval.json"
            for field in [*fields, "expired", "symbol", "timeframe_seconds"]:
                candidate = json.loads(json.dumps(approval))
                if field in fields:
                    candidate["bindings"][field] = "b" * 64
                elif field == "expired":
                    candidate["valid_until_utc"] = "2000-01-01T00:00:00Z"
                else:
                    candidate[field] = "tampered"
                artifact.write_text(json.dumps(candidate))
                feed = PublicMarketFeed(
                    custom_candle_fetcher=lambda *_: self.fail("Feed must not run")
                )
                output = Path(temp) / "must-not-exist"
                with (
                    self.subTest(field=field),
                    self.assertRaisesRegex(ValueError, "BLOCKED_CANDIDATE"),
                ):
                    run_shadow_loop("CANDIDATE_SHADOW", feed, run_dir=output)
                self.assertEqual(feed.request_count, 0)
                self.assertFalse(output.exists())
        with (
            patch("scripts.run_shadow.PublicMarketFeed") as constructor,
            contextlib.redirect_stderr(io.StringIO()),
            self.assertRaises(SystemExit),
        ):
            main(["--mode", "CANDIDATE_SHADOW"])
        constructor.assert_not_called()

    def test_paper_restart_disconnect_stop_and_finalization_without_model_or_network(self):
        with (
            tempfile.TemporaryDirectory() as temp,
            patch("httpx.Client.request", side_effect=AssertionError("No real writes/reads")),
            patch(
                "royin.agent.decide", side_effect=AssertionError("Stop must not depend on model")
            ),
        ):
            path = Path(temp) / "paper.sqlite"
            ledger = Ledger(path)
            ledger.set_balance("TMN", D("1000"))
            with ledger.worker():
                broker = PaperBroker(ledger, fixtures.rules())
                broker.submit_order(fixtures.intent(stop="95"), client_id="durable", timestamp=1000)
                broker.process_candle(Candle(2000, D("100"), D("101"), D("99"), D("100"), D("100")))
            self.assertEqual(ledger.get_balance("USDT").free, D(1))
            before = ledger.get_all_balances()
            # A failed feed supplies no bar to execution and therefore changes no money.
            feed = PublicMarketFeed(
                custom_candle_fetcher=lambda *_: (_ for _ in ()).throw(
                    httpx.ConnectError("fixture disconnect")
                )
            )
            with self.assertRaises(httpx.ConnectError):
                feed.fetch_latest_candles()
            self.assertEqual(ledger.get_all_balances(), before)
            restarted = Ledger(path)
            with restarted.worker():
                recovered = PaperBroker(restarted, fixtures.rules())
                self.assertEqual(recovered.active_stop_prices["USDTTMN"], D("95"))
                recovered.process_candle(
                    Candle(3000, D("100"), D("101"), D("90"), D("92"), D("100"))
                )
                self.assertEqual(restarted.get_balance("USDT").total, D(0))
                # 1000 -100 -.3 +90*.9995*(1-.003) = 989.385135.
                self.assertEqual(restarted.get_balance("TMN").free, D("989.385135"))
                settled = recovered.finalize_portfolio(
                    D("92"), timestamp=4000, initial_capital=D(1000)
                )
            again = Ledger(path)
            with again.worker():
                repeat = PaperBroker(again, fixtures.rules()).finalize_portfolio(
                    D("92"), timestamp=4000, initial_capital=D(1000)
                )
            self.assertEqual(settled["final_tmn_cash"], repeat["final_tmn_cash"])
            self.assertEqual(again.get_balance("TMN").free, D("989.385135"))

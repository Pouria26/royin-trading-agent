"""Validate the supplied restriction snapshot; no runtime trading gate exists yet."""

import json
import re
import unittest
from pathlib import Path

POLICY_PATH = Path(__file__).resolve().parents[1] / "config" / "wallex-credit-market-policy.json"


class MarketPolicySnapshotTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.policy = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
        cls.pairs = cls.policy["unavailable_markets"]

    def test_snapshot_shape_and_spot_constraint(self):
        self.assertEqual(self.policy["market_type"], "SPOT")
        self.assertIs(self.policy["leverage_allowed"], False)
        self.assertEqual(len(self.pairs), 345)
        self.assertEqual(len(set(self.pairs)), 345)
        self.assertEqual(sum(p.endswith("/TMN") for p in self.pairs), 171)
        self.assertEqual(sum(p.endswith("/USDT") for p in self.pairs), 174)
        for pair in self.pairs:
            self.assertIsNotNone(re.fullmatch(r"[A-Z0-9]+/(TMN|USDT)", pair), pair)

    def test_pair_specific_restrictions_are_preserved(self):
        for pair in ("PAXG/TMN", "PAXG/USDT", "OP/TMN", "OP/USDT", "AAPLX/TMN", "AAPLX/USDT"):
            self.assertIn(pair, self.pairs)
        self.assertIn("YFI/USDT", self.pairs)
        self.assertNotIn("YFI/TMN", self.pairs)  # Absence does not assert account eligibility.

    def test_api_spelling_keeps_numeric_bases_and_does_not_collide(self):
        api_spellings = {pair.replace("/", "") for pair in self.pairs}
        self.assertEqual(len(api_spellings), len(self.pairs))
        for symbol in ("1BBABYDOGETMN", "1BBABYDOGEUSDT", "2ZTMN", "2ZUSDT", "PAXGTMN"):
            self.assertIn(symbol, api_spellings)

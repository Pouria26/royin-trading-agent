import unittest

from pydantic import ValidationError

from royin.decision import Decision, DecisionProposal, bind_decision


class DecisionContractTests(unittest.TestCase):
    def setUp(self):
        self.valid_hash = "a" * 64
        self.valid_kwargs = {
            "decision_id": "dec_001",
            "symbol": "USDTTMN",
            "action": "ENTER",
            "cutoff": 1790812800,
            "snapshot_sha256": self.valid_hash,
            "evidence_ids": ("EV_MOMENTUM_1", "EV_SPREAD_OK"),
            "reason": "Clear momentum breakout above resistance with strong volume",
            "invalidation": "Hourly close drops below 60500 TMN",
        }

    def test_valid_decision_instantiation_and_immutability(self):
        decision = Decision(**self.valid_kwargs)
        self.assertEqual(decision.decision_id, "dec_001")
        self.assertEqual(decision.symbol, "USDTTMN")
        self.assertEqual(decision.action, "ENTER")
        self.assertEqual(decision.cutoff, 1790812800)
        self.assertEqual(decision.snapshot_sha256, self.valid_hash)
        self.assertEqual(decision.evidence_ids, ("EV_MOMENTUM_1", "EV_SPREAD_OK"))
        self.assertEqual(decision.reason, "Clear momentum breakout above resistance with strong volume")
        self.assertEqual(decision.invalidation, "Hourly close drops below 60500 TMN")

        with self.assertRaises(ValidationError):
            decision.action = "WAIT"

    def test_forbid_extra_fields(self):
        with self.assertRaises(ValidationError):
            Decision(**self.valid_kwargs, confidence=0.95)

    def test_actions_must_be_strictly_wait_enter_or_exit(self):
        for act in ("WAIT", "ENTER", "EXIT"):
            d = Decision(**{**self.valid_kwargs, "action": act})
            self.assertEqual(d.action, act)

        for invalid in ("BUY", "SELL", "HOLD", "NONE", ""):
            with self.assertRaises(ValidationError):
                Decision(**{**self.valid_kwargs, "action": invalid})

    def test_cutoff_must_be_nonnegative_integer_never_bool_or_float(self):
        with self.assertRaises(ValidationError):
            Decision(**{**self.valid_kwargs, "cutoff": True})
        with self.assertRaises(ValidationError):
            Decision(**{**self.valid_kwargs, "cutoff": -1})
        with self.assertRaises(ValidationError):
            Decision(**{**self.valid_kwargs, "cutoff": 1790812800.5})
        with self.assertRaises(ValidationError):
            Decision(**{**self.valid_kwargs, "cutoff": "1790812800"})

    def test_snapshot_sha256_must_be_exact_64_lowercase_hex(self):
        # 63 characters
        with self.assertRaises(ValidationError):
            Decision(**{**self.valid_kwargs, "snapshot_sha256": "a" * 63})
        # 65 characters
        with self.assertRaises(ValidationError):
            Decision(**{**self.valid_kwargs, "snapshot_sha256": "a" * 65})
        # Uppercase
        with self.assertRaises(ValidationError):
            Decision(**{**self.valid_kwargs, "snapshot_sha256": "A" * 64})
        # Non-hex
        with self.assertRaises(ValidationError):
            Decision(**{**self.valid_kwargs, "snapshot_sha256": "g" * 64})

    def test_evidence_ids_cannot_be_empty_or_have_duplicates_or_blank(self):
        with self.assertRaises(ValidationError):
            Decision(**{**self.valid_kwargs, "evidence_ids": ()})
        with self.assertRaises(ValidationError):
            Decision(**{**self.valid_kwargs, "evidence_ids": ("EV_1", "EV_1")})
        with self.assertRaises(ValidationError):
            Decision(**{**self.valid_kwargs, "evidence_ids": ("EV_1", "")})
        with self.assertRaises(ValidationError):
            Decision(**{**self.valid_kwargs, "evidence_ids": ("   ",)})

    def test_reason_and_invalidation_must_be_nonempty(self):
        with self.assertRaises(ValidationError):
            Decision(**{**self.valid_kwargs, "reason": ""})
        with self.assertRaises(ValidationError):
            Decision(**{**self.valid_kwargs, "reason": "   "})
        with self.assertRaises(ValidationError):
            Decision(**{**self.valid_kwargs, "invalidation": ""})

    def test_bind_decision_success(self):
        proposal = DecisionProposal(
            action="ENTER",
            evidence_ids=("EV_MOM_1", "EV_VOL_1"),
            reason="Volume confirms upward momentum",
            invalidation="Drop below 50 MA",
        )
        decision = bind_decision(
            proposal,
            decision_id="dec_42",
            symbol="USDTTMN",
            cutoff=1790812800,
            snapshot_sha256=self.valid_hash,
            available_evidence_ids=("EV_MOM_1", "EV_VOL_1", "EV_OTHER"),
            allowed_symbols=("USDTTMN", "BTCTMN"),
        )
        self.assertEqual(decision.decision_id, "dec_42")
        self.assertEqual(decision.action, "ENTER")
        self.assertEqual(decision.cutoff, 1790812800)

    def test_bind_decision_rejects_unresolvable_evidence(self):
        proposal = DecisionProposal(
            action="ENTER",
            evidence_ids=("EV_FABRICATED",),
            reason="Fake evidence cited",
            invalidation="Never",
        )
        with self.assertRaises(ValueError) as ctx:
            bind_decision(
                proposal,
                decision_id="dec_43",
                symbol="USDTTMN",
                cutoff=1790812800,
                snapshot_sha256=self.valid_hash,
                available_evidence_ids=("EV_REAL_1", "EV_REAL_2"),
            )
        self.assertIn("fabricated", str(ctx.exception).lower())

    def test_bind_decision_rejects_ineligible_symbol(self):
        proposal = DecisionProposal(
            action="ENTER",
            evidence_ids=("EV_REAL_1",),
            reason="Opportunity in PAXG",
            invalidation="Never",
        )
        with self.assertRaises(ValueError) as ctx:
            bind_decision(
                proposal,
                decision_id="dec_44",
                symbol="PAXGTMN",
                cutoff=1790812800,
                snapshot_sha256=self.valid_hash,
                available_evidence_ids=("EV_REAL_1",),
                allowed_symbols=("USDTTMN", "BTCTMN"),
            )
        self.assertIn("not in the allowed universe", str(ctx.exception).lower())


if __name__ == "__main__":
    unittest.main()

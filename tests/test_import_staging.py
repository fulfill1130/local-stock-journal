from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from import_staging import create_import_staging_batch, validate_import_payload


class ImportStagingTests(unittest.TestCase):
    def test_valid_buy_creates_staging_batch_with_truncated_consideration_only(self) -> None:
        payload = {
            "source_type": "ai_json",
            "broker": "demo",
            "transactions": [
                {
                    "date": "2026-01-01",
                    "action": "BUY",
                    "ticker": "2330",
                    "shares": 34,
                    "price": 29.73,
                    "fee": 1,
                    "tax": 0,
                }
            ],
        }

        batch = validate_import_payload(payload, profile="demo", batch_id="batch_buy", created_at="2026-01-02T00:00:00+08:00")

        row = batch["rows"][0]
        self.assertEqual(row["computed_amount"], 1010)
        self.assertEqual(row["normalized"]["computed_cash_amount"], 1011)
        self.assertEqual(row["errors"], [])
        self.assertEqual(row["review_status"], "pending")

    def test_valid_sell_uses_broker_style_truncated_consideration(self) -> None:
        payload = {
            "transactions": [
                {
                    "date": "2026-01-02",
                    "action": "SELL",
                    "ticker": "2330",
                    "shares": 34,
                    "price": 29.73,
                    "fee": 1,
                    "tax": 1,
                }
            ]
        }

        batch = validate_import_payload(payload, profile="demo")

        row = batch["rows"][0]
        self.assertEqual(row["computed_amount"], 1010)
        self.assertEqual(row["normalized"]["computed_cash_amount"], 1008)
        self.assertEqual(row["errors"], [])

    def test_invalid_shares_and_price_produce_row_errors(self) -> None:
        payload = {
            "transactions": [
                {
                    "date": "2026-01-01",
                    "action": "BUY",
                    "ticker": "2330",
                    "shares": 0,
                    "price": -1,
                    "fee": 0,
                    "tax": 0,
                }
            ]
        }

        batch = validate_import_payload(payload, profile="demo")

        row = batch["rows"][0]
        self.assertIn("shares must be greater than 0", row["errors"])
        self.assertIn("price must be greater than 0", row["errors"])
        self.assertEqual(row["review_status"], "error")

    def test_amount_mismatch_produces_warning(self) -> None:
        payload = {
            "transactions": [
                {
                    "date": "2026-01-01",
                    "action": "BUY",
                    "ticker": "2330",
                    "shares": 34,
                    "price": 29.73,
                    "fee": 1,
                    "tax": 0,
                    "amount": 1011,
                }
            ]
        }

        batch = validate_import_payload(payload, profile="demo")

        row = batch["rows"][0]
        self.assertEqual(row["computed_amount"], 1010)
        self.assertEqual(row["amount_difference"], 1)
        self.assertIn("source amount does not match broker-style truncated consideration", row["warnings"])
        self.assertEqual(row["review_status"], "warning")

    def test_duplicate_looking_transaction_adds_candidate_and_warning(self) -> None:
        existing = [
            {
                "id": "tx_existing",
                "time": "2026-01-01T09:30:00+08:00",
                "action": "BUY",
                "ticker": "2330",
                "shares": 34,
                "price": 29.73,
            }
        ]
        payload = {
            "transactions": [
                {
                    "date": "2026-01-01",
                    "action": "BUY",
                    "ticker": "2330",
                    "shares": 34,
                    "price": 29.73,
                    "fee": 1,
                    "tax": 0,
                }
            ]
        }

        batch = validate_import_payload(payload, profile="demo", existing_transactions=existing)

        row = batch["rows"][0]
        self.assertEqual(row["duplicate_candidates"][0]["id"], "tx_existing")
        self.assertIn("possible duplicate transaction", row["warnings"])
        self.assertEqual(row["review_status"], "warning")

    def test_batch_json_is_written_under_temporary_staging_root(self) -> None:
        payload = {
            "transactions": [
                {
                    "date": "2026-01-01",
                    "action": "BUY",
                    "ticker": "2330",
                    "shares": 34,
                    "price": 29.73,
                    "fee": 1,
                    "tax": 0,
                }
            ]
        }
        with tempfile.TemporaryDirectory() as tmp:
            batch = create_import_staging_batch(
                Path(tmp),
                profile="demo",
                payload=payload,
                batch_id="batch_file",
                created_at="2026-01-02T00:00:00+08:00",
            )
            batch_path = Path(batch["path"])

            self.assertEqual(batch_path, Path(tmp) / "demo" / "batch_file" / "batch.json")
            written = json.loads(batch_path.read_text(encoding="utf-8"))
            self.assertEqual(written["batch_id"], "batch_file")
            self.assertEqual(written["rows"][0]["computed_amount"], 1010)

    def test_profile_state_json_remains_unchanged(self) -> None:
        state = {"transactions": [], "holdings": [], "settings": {"cash_available": 1000}}
        payload = {
            "transactions": [
                {
                    "date": "2026-01-01",
                    "action": "BUY",
                    "ticker": "2330",
                    "shares": 34,
                    "price": 29.73,
                    "fee": 1,
                    "tax": 0,
                }
            ]
        }
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state_path = root / "state.json"
            state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
            before = state_path.read_text(encoding="utf-8")

            create_import_staging_batch(root / "staging", profile="demo", payload=payload)

            self.assertEqual(state_path.read_text(encoding="utf-8"), before)

    def test_final_ledger_write_functions_are_not_called(self) -> None:
        payload = {
            "transactions": [
                {
                    "date": "2026-01-01",
                    "action": "BUY",
                    "ticker": "2330",
                    "shares": 34,
                    "price": 29.73,
                    "fee": 1,
                    "tax": 0,
                }
            ]
        }
        with tempfile.TemporaryDirectory() as tmp:
            with patch("store.record_buy") as record_buy, patch("store.record_sell") as record_sell, patch(
                "server.record_transaction_from_payload"
            ) as record_transaction, patch("server.record_cash_deposit_from_payload") as record_cash, patch(
                "server.record_dividend_income_from_payload"
            ) as record_dividend:
                create_import_staging_batch(Path(tmp), profile="demo", payload=payload)

        record_buy.assert_not_called()
        record_sell.assert_not_called()
        record_transaction.assert_not_called()
        record_cash.assert_not_called()
        record_dividend.assert_not_called()

    def test_dividend_rows_are_kept_separate_and_marked_unsupported(self) -> None:
        payload = {
            "dividend_movements": [
                {
                    "date": "2026-01-10",
                    "ticker": "2330",
                    "amount": 25,
                }
            ]
        }

        batch = validate_import_payload(payload, profile="demo")

        row = batch["rows"][0]
        self.assertEqual(row["kind"], "dividend_movement")
        self.assertIn("dividend_movement rows are not supported by Import Staging v1", row["errors"])
        self.assertEqual(row["review_status"], "error")


if __name__ == "__main__":
    unittest.main()

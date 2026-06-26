from __future__ import annotations

import gc
import json
import sys
import tempfile
import unittest
import warnings
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
SCRIPTS = ROOT / "scripts"
for path in (SRC, SCRIPTS):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from prepare_demo_runtime import prepare_demo_runtime  # noqa: E402
from server import create_app  # noqa: E402
from store import load_state, save_state  # noqa: E402


class ImportStagingApiTests(unittest.TestCase):
    def setUp(self) -> None:
        warnings.filterwarnings("ignore", category=ResourceWarning)
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.project_root = Path(self.tmp.name)
        self.app = create_app(self.project_root)
        self.client = self.app.test_client()

    def tearDown(self) -> None:
        self.client = None
        self.app = None
        gc.collect()
        self.tmp.cleanup()

    def test_post_creates_batch_file_only(self) -> None:
        response = self.client.post("/son/api/import-staging", json=self._payload())

        self.assertEqual(response.status_code, 201)
        data = response.get_json()
        batch_id = data["batch"]["batch_id"]
        batch_path = self.project_root / "data" / "imports" / "staging" / "son" / batch_id / "batch.json"
        self.assertTrue(batch_path.exists())
        written = json.loads(batch_path.read_text(encoding="utf-8"))
        self.assertEqual(written["rows"][0]["computed_amount"], 1010)

        state = load_state(self.project_root / "data" / "profiles" / "son" / "state.json")
        self.assertEqual(state.get("transactions", []), [])

    def test_post_returns_row_warnings_and_errors(self) -> None:
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
                },
                {
                    "date": "2026-01-01",
                    "action": "BUY",
                    "ticker": "",
                    "shares": 0,
                    "price": 0,
                    "fee": 0,
                    "tax": 0,
                },
            ]
        }

        response = self.client.post("/son/api/import-staging", json=payload)

        self.assertEqual(response.status_code, 201)
        data = response.get_json()
        self.assertEqual(data["batch"]["warning_count"], 1)
        self.assertEqual(data["batch"]["error_count"], 1)
        self.assertIn("source amount does not match broker-style truncated consideration", data["rows"][0]["warnings"])
        self.assertIn("ticker is required", data["rows"][1]["errors"])

    def test_get_list_returns_created_batches(self) -> None:
        created = self.client.post("/son/api/import-staging", json=self._payload()).get_json()

        response = self.client.get("/son/api/import-staging")

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data["batches"][0]["batch_id"], created["batch"]["batch_id"])
        self.assertEqual(data["batches"][0]["row_count"], 1)

    def test_get_detail_returns_batch_json(self) -> None:
        created = self.client.post("/son/api/import-staging", json=self._payload()).get_json()
        batch_id = created["batch"]["batch_id"]

        response = self.client.get(f"/son/api/import-staging/{batch_id}")

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data["batch"]["batch_id"], batch_id)
        self.assertEqual(data["batch"]["rows"][0]["computed_amount"], 1010)

    def test_duplicate_existing_transaction_returns_warning_without_blocking(self) -> None:
        state_path = self.project_root / "data" / "profiles" / "son" / "state.json"
        state = load_state(state_path)
        state["transactions"] = [
            {
                "id": "tx_existing",
                "time": "2026-01-01T09:30:00+08:00",
                "action": "BUY",
                "ticker": "2330",
                "shares": 34,
                "price": 29.73,
            }
        ]
        save_state(state_path, state)

        response = self.client.post("/son/api/import-staging", json=self._payload())

        self.assertEqual(response.status_code, 201)
        row = response.get_json()["rows"][0]
        self.assertEqual(row["duplicate_candidates"][0]["id"], "tx_existing")
        self.assertIn("possible duplicate transaction", row["warnings"])

    def test_demo_mode_rejects_staging_write(self) -> None:
        runtime_root = self.project_root / "demo_runtime"
        prepare_demo_runtime(ROOT, runtime_root, reset=False)
        demo_app = create_app(ROOT, runtime_root=runtime_root, demo_mode=True)
        demo_client = demo_app.test_client()

        response = demo_client.post("/demo/api/import-staging", json=self._payload())

        self.assertEqual(response.status_code, 403)

    def test_final_ledger_write_functions_are_not_called(self) -> None:
        with patch("store.record_buy") as record_buy, patch("store.record_sell") as record_sell, patch(
            "server.record_transaction_from_payload"
        ) as record_transaction, patch("server.record_cash_deposit_from_payload") as record_cash, patch(
            "server.record_dividend_income_from_payload"
        ) as record_dividend:
            response = self.client.post("/son/api/import-staging", json=self._payload())

        self.assertEqual(response.status_code, 201)
        record_buy.assert_not_called()
        record_sell.assert_not_called()
        record_transaction.assert_not_called()
        record_cash.assert_not_called()
        record_dividend.assert_not_called()

    def test_invalid_json_returns_friendly_error(self) -> None:
        response = self.client.post(
            "/son/api/import-staging",
            data="{",
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("Invalid JSON payload", response.get_json()["error"])

    def _payload(self) -> dict:
        return {
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


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import gc
import json
import sqlite3
import sys
import tempfile
import unittest
import warnings
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from central_store import get_etf_holding_snapshot, upsert_etf_holding_snapshot  # noqa: E402
from server import create_app  # noqa: E402


class EtfHoldingsImportApiTests(unittest.TestCase):
    def setUp(self) -> None:
        warnings.filterwarnings("ignore", category=ResourceWarning)
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.project_root = Path(self.tmp.name)
        self.app = create_app(self.project_root)
        self.client = self.app.test_client()
        self.market_root = self.project_root / "data" / "market_data"

    def tearDown(self) -> None:
        self.client = None
        self.app = None
        gc.collect()
        self.tmp.cleanup()

    def test_preview_parses_valid_csv_and_does_not_write_database(self) -> None:
        response = self.client.post(
            "/api/database/etf-holdings/import-csv",
            json={"csv_text": _valid_csv(), "confirm": False},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["mode"], "preview")
        self.assertFalse(payload["imported"])
        self.assertEqual(payload["snapshot"]["etf_ticker"], "DEMOA")
        self.assertEqual(payload["summary"]["component_count"], 2)
        self.assertEqual(payload["components"][0]["constituent_ticker"], "DEMOX")
        self.assertEqual(_snapshot_count(self.market_root), 0)

    def test_confirm_imports_valid_csv_and_read_api_returns_it(self) -> None:
        response = self.client.post(
            "/api/database/etf-holdings/import-csv",
            json={"csv_text": _alias_csv(), "source": "manual_csv", "confirm": True},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertTrue(payload["ok"])
        self.assertTrue(payload["imported"])
        self.assertEqual(payload["snapshot"]["source"], "manual_csv")

        read_response = self.client.get("/api/database/DEMOA/etf-holdings")
        read_payload = read_response.get_json()

        self.assertEqual(read_response.status_code, 200)
        self.assertTrue(read_payload["ok"])
        self.assertEqual(read_payload["snapshot"]["as_of_date"], "2026-04-16")
        self.assertEqual(read_payload["summary"]["component_count"], 2)
        self.assertEqual([row["constituent_ticker"] for row in read_payload["components"]], ["DEMOX", "DEMOY"])

    def test_invalid_csv_returns_errors_and_does_not_write(self) -> None:
        response = self.client.post(
            "/api/database/etf-holdings/import-csv",
            json={"csv_text": "constituent_ticker,weight\nDEMOX,50\n", "confirm": True},
        )

        self.assertEqual(response.status_code, 400)
        payload = response.get_json()
        self.assertFalse(payload["ok"])
        self.assertIn("etf_ticker_required", {issue["code"] for issue in payload["errors"]})
        self.assertIn("as_of_date_required", {issue["code"] for issue in payload["errors"]})
        self.assertEqual(_snapshot_count(self.market_root), 0)

    def test_negative_weight_is_rejected(self) -> None:
        response = self.client.post(
            "/api/database/etf-holdings/import-csv",
            json={
                "csv_text": "etf_ticker,as_of_date,constituent_ticker,weight\nDEMOA,2026-04-16,BAD,-1\n",
                "confirm": True,
            },
        )

        self.assertEqual(response.status_code, 400)
        payload = response.get_json()
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["errors"][0]["code"], "negative_weight")
        self.assertEqual(_snapshot_count(self.market_root), 0)

    def test_missing_components_is_rejected(self) -> None:
        response = self.client.post(
            "/api/database/etf-holdings/import-csv",
            json={"csv_text": "etf_ticker,as_of_date,weight\nDEMOA,2026-04-16,50\n", "confirm": True},
        )

        self.assertEqual(response.status_code, 400)
        payload = response.get_json()
        self.assertFalse(payload["ok"])
        self.assertIn("components_required", {issue["code"] for issue in payload["errors"]})
        self.assertEqual(_snapshot_count(self.market_root), 0)

    def test_older_snapshot_is_rejected_without_override(self) -> None:
        upsert_etf_holding_snapshot(
            self.market_root,
            etf_ticker="DEMOA",
            as_of_date="2026-05-01",
            source="unit_test",
            rows=[{"constituent_ticker": "NEW", "constituent_name": "New", "weight": 100}],
        )

        response = self.client.post(
            "/api/database/etf-holdings/import-csv",
            json={"csv_text": _valid_csv(), "confirm": True},
        )

        self.assertEqual(response.status_code, 409)
        payload = response.get_json()
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["errors"][0]["code"], "older_snapshot_exists")
        current = get_etf_holding_snapshot(self.market_root, "DEMOA")
        self.assertEqual(current["snapshot"]["as_of_date"], "2026-05-01")
        self.assertEqual(current["components"][0]["constituent_ticker"], "NEW")

    def test_optional_fields_can_be_missing(self) -> None:
        response = self.client.post(
            "/api/database/etf-holdings/import-csv",
            json={
                "csv_text": "etf_ticker,as_of_date,constituent_name\nDEMOA,2026-04-16,Demo Component X\n",
                "confirm": True,
            },
        )

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertTrue(payload["ok"])
        self.assertIsNone(payload["components"][0]["weight"])
        self.assertEqual(payload["components"][0]["constituent_name"], "Demo Component X")

    def test_response_excludes_profile_private_state(self) -> None:
        state_path = self.project_root / "data" / "profiles" / "son" / "state.json"
        state_path.parent.mkdir(parents=True, exist_ok=True)
        state_path.write_text(
            json.dumps(
                {
                    "transactions": [{"ticker": "PRIVATE123", "note": "PRIVATE_TRANSACTION_NOTE"}],
                    "holdings": [{"ticker": "PRIVATE123", "lots": [{"note": "PRIVATE_LOT"}]}],
                    "settings": {"gmail_token": "SECRET_TOKEN"},
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        response_text = self.client.post(
            "/api/database/etf-holdings/import-csv",
            json={"csv_text": _valid_csv(), "confirm": False},
        ).get_data(as_text=True)

        self.assertNotIn("PRIVATE123", response_text)
        self.assertNotIn("PRIVATE_TRANSACTION_NOTE", response_text)
        self.assertNotIn("PRIVATE_LOT", response_text)
        self.assertNotIn("SECRET_TOKEN", response_text)
        self.assertNotIn("transactions", response_text)
        self.assertNotIn("lots", response_text)


def _valid_csv() -> str:
    return "\n".join(
        [
            "etf_ticker,as_of_date,constituent_ticker,constituent_name,weight,shares,market_value,industry,sort_order",
            "DEMOA,2026-04-16,DEMOX,Demo Component X,60,1000,60000,Demo Tech,1",
            "DEMOA,2026-04-16,DEMOY,Demo Component Y,40,800,40000,Demo Finance,2",
        ]
    )


def _alias_csv() -> str:
    return "\n".join(
        [
            "ETF,date,component_ticker,name,weight_percent",
            "DEMOA,2026-04-16,DEMOX,Demo Component X,60",
            "DEMOA,2026-04-16,DEMOY,Demo Component Y,40",
        ]
    )


def _snapshot_count(market_root: Path) -> int:
    db_path = market_root / "etf.sqlite"
    if not db_path.exists():
        return 0
    with sqlite3.connect(db_path) as conn:
        table = conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'etf_holding_snapshots'"
        ).fetchone()
        if table is None:
            return 0
        return int(conn.execute("SELECT COUNT(*) FROM etf_holding_snapshots").fetchone()[0])


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import gc
import json
import shutil
import sqlite3
import sys
import tempfile
import unittest
import warnings
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
SCRIPTS = ROOT / "scripts"
for path in (SRC, SCRIPTS):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from central_store import ensure_central_db, get_etf_holding_snapshot, upsert_etf_holding_snapshot  # noqa: E402
from prepare_demo_runtime import prepare_demo_runtime  # noqa: E402
from server import create_app  # noqa: E402


class EtfHoldingsApiTests(unittest.TestCase):
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

    def test_schema_creation_includes_etf_holdings_tables(self) -> None:
        market_root = self.project_root / "data" / "market_data"
        ensure_central_db(market_root)

        tables = _table_names(market_root / "etf.sqlite")

        self.assertIn("etf_holding_snapshots", tables)
        self.assertIn("etf_holding_components", tables)

    def test_api_returns_latest_components_and_as_of_date(self) -> None:
        market_root = self.project_root / "data" / "market_data"
        upsert_etf_holding_snapshot(
            market_root,
            etf_ticker="DEMOA",
            as_of_date="2026-04-01",
            source="unit_test",
            rows=[
                {"constituent_ticker": "OLD", "constituent_name": "Old Component", "weight": 100, "sort_order": 1},
            ],
        )
        upsert_etf_holding_snapshot(
            market_root,
            etf_ticker="DEMOA",
            as_of_date="2026-04-16",
            source="unit_test",
            rows=[
                {"constituent_ticker": "DEMOX", "constituent_name": "Demo Component X", "weight": 60, "sort_order": 1},
                {"constituent_ticker": "DEMOY", "constituent_name": "Demo Component Y", "weight": 40, "sort_order": 2},
            ],
        )

        response = self.client.get("/api/database/DEMOA/etf-holdings")

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["ticker"], "DEMOA")
        self.assertEqual(payload["snapshot"]["as_of_date"], "2026-04-16")
        self.assertEqual(payload["summary"]["component_count"], 2)
        self.assertEqual(payload["summary"]["weight_total"], 100)
        self.assertEqual([row["constituent_ticker"] for row in payload["components"]], ["DEMOX", "DEMOY"])

    def test_missing_etf_holdings_returns_safe_empty_payload(self) -> None:
        response = self.client.get("/api/database/NOHOLD/etf-holdings")

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertTrue(payload["ok"])
        self.assertIsNone(payload["snapshot"])
        self.assertEqual(payload["components"], [])
        self.assertEqual(payload["summary"]["component_count"], 0)
        self.assertIn("No local ETF holdings", payload["message"])

    def test_demo_runtime_seeds_synthetic_etf_holdings(self) -> None:
        runtime = self.project_root / "demo_runtime"
        prepare_demo_runtime(ROOT, runtime, reset=False)
        demo_app = create_app(ROOT, runtime_root=runtime, demo_mode=True)
        demo_client = demo_app.test_client()

        response = demo_client.get("/api/database/DEMOA/etf-holdings")

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["snapshot"]["source"], "synthetic_demo")
        self.assertEqual(payload["snapshot"]["as_of_date"], "2026-04-16")
        self.assertEqual(payload["summary"]["component_count"], 4)
        self.assertTrue(all(row["source"] == "synthetic_demo" for row in payload["components"]))
        shutil.rmtree(runtime.parent, ignore_errors=True)

    def test_read_helper_can_select_snapshot_by_as_of_date(self) -> None:
        market_root = self.project_root / "data" / "market_data"
        upsert_etf_holding_snapshot(
            market_root,
            etf_ticker="DEMOA",
            as_of_date="2026-04-01",
            source="unit_test",
            rows=[{"constituent_ticker": "A", "constituent_name": "A", "weight": 100}],
        )
        upsert_etf_holding_snapshot(
            market_root,
            etf_ticker="DEMOA",
            as_of_date="2026-04-16",
            source="unit_test",
            rows=[{"constituent_ticker": "B", "constituent_name": "B", "weight": 100}],
        )

        result = get_etf_holding_snapshot(market_root, "DEMOA", "2026-04-01")

        self.assertIsNotNone(result)
        self.assertEqual(result["snapshot"]["as_of_date"], "2026-04-01")
        self.assertEqual(result["components"][0]["constituent_ticker"], "A")

    def test_api_excludes_profile_account_data(self) -> None:
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
        upsert_etf_holding_snapshot(
            self.project_root / "data" / "market_data",
            etf_ticker="DEMOA",
            as_of_date="2026-04-16",
            source="unit_test",
            rows=[{"constituent_ticker": "DEMOX", "constituent_name": "Demo Component X", "weight": 100}],
        )

        response_text = self.client.get("/api/database/DEMOA/etf-holdings").get_data(as_text=True)

        self.assertNotIn("PRIVATE123", response_text)
        self.assertNotIn("PRIVATE_TRANSACTION_NOTE", response_text)
        self.assertNotIn("PRIVATE_LOT", response_text)
        self.assertNotIn("SECRET_TOKEN", response_text)
        self.assertNotIn("transactions", response_text)
        self.assertNotIn("holdings", response_text)


def _table_names(db_path: Path) -> set[str]:
    with sqlite3.connect(db_path) as conn:
        return {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}


if __name__ == "__main__":
    unittest.main()

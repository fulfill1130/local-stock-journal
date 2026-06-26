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
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
SCRIPTS = ROOT / "scripts"
for path in (SRC, SCRIPTS):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from prepare_demo_runtime import prepare_demo_runtime  # noqa: E402
from server import create_app  # noqa: E402


class MarketDataStatusApiTests(unittest.TestCase):
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

    def test_returns_ohlcv_max_dates_from_segmented_databases(self) -> None:
        self._insert_segment_status("etf", "ETF:DEMO", "2026-06-25")
        self._insert_segment_status("twse", "TWSE:2330", "2026-06-26")
        self._insert_segment_status("tpex", "TPEX:4126", "2026-06-24")

        response = self.client.get("/api/market-data-status")

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["ohlcv"]["updated_through"], "2026-06-26")
        self.assertEqual(payload["ohlcv"]["row_count"], 3)
        self.assertEqual(payload["ohlcv"]["segments"]["etf"]["last_date"], "2026-06-25")
        self.assertEqual(payload["ohlcv"]["segments"]["twse"]["last_date"], "2026-06-26")
        self.assertEqual(payload["ohlcv"]["segments"]["tpex"]["last_date"], "2026-06-24")
        self.assertEqual(payload["official_daily"]["status"], "success")

    def test_separates_quote_cache_freshness_from_official_ohlcv_date(self) -> None:
        self._insert_segment_status("twse", "TWSE:2330", "2026-06-26")
        self._write_quote_cache(
            {
                "2330.TW": {
                    "status": "ok",
                    "fetched_at": "2026-06-27T02:46:09+08:00",
                    "price_time": "2026-06-27 02:46:09",
                    "close": 100,
                }
            }
        )

        payload = self.client.get("/api/market-data-status").get_json()

        self.assertEqual(payload["ohlcv"]["updated_through"], "2026-06-26")
        self.assertEqual(payload["quotes"]["latest_cache_timestamp"], "2026-06-27T02:46:09+08:00")
        self.assertEqual(payload["quotes"]["latest_table_date"], "2026-06-26")
        self.assertEqual(payload["quotes"]["cache_count"], 1)

    def test_demo_mode_returns_local_fixture_status_without_refreshing(self) -> None:
        runtime_root = self.project_root / "demo_runtime"
        prepare_demo_runtime(ROOT, runtime_root, reset=False)
        demo_app = create_app(ROOT, runtime_root=runtime_root, demo_mode=True)
        demo_client = demo_app.test_client()

        with patch("server.sync_missing_official_daily_bars") as official_sync, patch("server.fetch_symbol_bundle") as fetch_bundle:
            response = demo_client.get("/api/market-data-status")

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertTrue(payload["demo_mode"])
        self.assertEqual(payload["official_daily"]["status"], "local_fixture")
        self.assertEqual(payload["official_daily"]["source"], "synthetic_demo")
        self.assertIn("refresh is disabled", payload["official_daily"]["message"])
        self.assertEqual(payload["ohlcv"]["updated_through"], "2026-04-16")
        official_sync.assert_not_called()
        fetch_bundle.assert_not_called()
        shutil.rmtree(runtime_root.parent, ignore_errors=True)

    def test_payload_excludes_profile_and_sensitive_refresh_details(self) -> None:
        state_path = self.project_root / "data" / "profiles" / "son" / "state.json"
        state_path.write_text(
            json.dumps(
                {
                    "transactions": [{"ticker": "PRIVATE123", "note": "PRIVATE_TRANSACTION_NOTE"}],
                    "holdings": [{"ticker": "PRIVATE123"}],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        refresh_log = self.project_root / "data" / "refresh_log.json"
        refresh_log.write_text(
            json.dumps(
                [
                    {
                        "time": "2026-06-27T01:00:00+08:00",
                        "source": "schedule:gmail-statements",
                        "status": "error",
                        "message": "gmail token SECRET_VALUE raw mail content",
                    },
                    {
                        "time": "2026-06-27T02:00:00+08:00",
                        "source": "schedule:official-daily",
                        "status": "ok",
                        "message": "rows_written=1",
                    },
                ],
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        response_text = self.client.get("/api/market-data-status").get_data(as_text=True)

        self.assertNotIn("PRIVATE123", response_text)
        self.assertNotIn("PRIVATE_TRANSACTION_NOTE", response_text)
        self.assertNotIn("SECRET_VALUE", response_text)
        self.assertNotIn("raw mail content", response_text)
        self.assertNotIn("transactions", response_text)
        self.assertNotIn("holdings", response_text)

    def test_missing_market_databases_return_empty_safe_status(self) -> None:
        market_root = self.project_root / "data" / "market_data"
        shutil.rmtree(market_root, ignore_errors=True)

        response = self.client.get("/api/market-data-status")

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertIsNone(payload["ohlcv"]["updated_through"])
        self.assertEqual(payload["ohlcv"]["row_count"], 0)
        self.assertEqual(payload["quotes"]["table_row_count"], 0)
        self.assertEqual(payload["after_close"]["row_count"], 0)
        self.assertEqual(payload["dividends"]["row_count"], 0)
        self.assertEqual(payload["health"]["instrument_count"], 0)

    def _insert_segment_status(self, segment: str, instrument_id: str, trade_date: str) -> None:
        db_path = self.project_root / "data" / "market_data" / f"{segment}.sqlite"
        with sqlite3.connect(db_path) as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO ohlcv_daily (
                    instrument_id, date, open, high, low, close, volume, source
                )
                VALUES (?, ?, 1, 1, 1, 1, 1000, 'test')
                """,
                (instrument_id, trade_date),
            )
            conn.execute(
                """
                INSERT OR REPLACE INTO quotes (
                    instrument_id, price, quote_date, quote_time, source, updated_at
                )
                VALUES (?, 1, ?, ?, 'test', ?)
                """,
                (instrument_id, trade_date, f"{trade_date}T13:30:00+08:00", f"{trade_date}T14:00:00+08:00"),
            )
            conn.execute(
                """
                INSERT OR REPLACE INTO after_close_quotes (
                    instrument_id, quote_date, price, source, created_at
                )
                VALUES (?, ?, 1, 'test', ?)
                """,
                (instrument_id, trade_date, f"{trade_date}T13:31:00+08:00"),
            )
            conn.execute(
                """
                INSERT OR REPLACE INTO instrument_health_summary (
                    instrument_id, daily_rows, last_daily_date, history_status, last_checked_at, last_success_at
                )
                VALUES (?, 1, ?, 'ok', ?, ?)
                """,
                (
                    instrument_id,
                    trade_date,
                    f"{trade_date}T15:00:00+08:00",
                    f"{trade_date}T15:00:00+08:00",
                ),
            )
            conn.execute(
                """
                INSERT OR REPLACE INTO update_status (
                    job_name, source, last_started_at, last_finished_at, next_run_at,
                    last_status, success_count, fail_count, message
                )
                VALUES (
                    'official_daily', 'twse_tpex', ?, ?, '2026-06-27T14:00:00+08:00',
                    'success', 1, 0, 'rows_written=1'
                )
                """,
                (f"{trade_date}T14:00:00+08:00", f"{trade_date}T14:01:00+08:00"),
            )

    def _write_quote_cache(self, payload: dict) -> None:
        path = self.project_root / "data" / "quotes_cache.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    unittest.main()

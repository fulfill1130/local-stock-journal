from __future__ import annotations

import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
SCRIPTS = ROOT / "scripts"
for path in (SRC, SCRIPTS):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from prepare_demo_runtime import SENTINEL_NAME, prepare_demo_runtime  # noqa: E402
from store import load_state  # noqa: E402


class PrepareDemoRuntimeTests(unittest.TestCase):
    def test_creates_isolated_demo_runtime_from_sample_data(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "demo_runtime"

            summary = prepare_demo_runtime(ROOT, target, reset=False)

            self.assertTrue((target / SENTINEL_NAME).exists())
            state = load_state(target / "profiles" / "demo" / "state.json")
            self.assertEqual(state["settings"]["app_title"], "Synthetic Demo Account")
            self.assertEqual({item["ticker"] for item in state["holdings"]}, {"DEMOA"})
            self.assertEqual({item["ticker"] for item in state["watchlist"]}, {"DEMOB"})
            self.assertFalse((target / "profiles" / "son").exists())
            self.assertFalse((target / "profiles" / "mom").exists())

            central_db_path = target / "market_data"
            self.assertEqual(_scalar(central_db_path / "etf.sqlite", "SELECT COUNT(*) FROM instruments WHERE ticker = 'DEMOA'"), 1)
            self.assertEqual(_scalar(central_db_path / "twse.sqlite", "SELECT COUNT(*) FROM instruments WHERE ticker = 'DEMOB'"), 1)
            self.assertGreaterEqual(
                _scalar(central_db_path / "etf.sqlite", "SELECT COUNT(*) FROM ohlcv_daily WHERE instrument_id = 'ETF:DEMOA'"),
                60,
            )
            self.assertGreaterEqual(
                _scalar(central_db_path / "twse.sqlite", "SELECT COUNT(*) FROM ohlcv_daily WHERE instrument_id = 'TWSE:DEMOB'"),
                60,
            )
            self.assertGreaterEqual(
                _scalar(central_db_path / "etf.sqlite", "SELECT COUNT(*) FROM etf_dividends WHERE ticker = 'DEMOA'"),
                1,
            )
            self.assertGreaterEqual(
                _scalar(central_db_path / "etf.sqlite", "SELECT COUNT(*) FROM etf_holding_components WHERE etf_ticker = 'DEMOA'"),
                4,
            )
            self.assertGreaterEqual(summary["history_rows"], 120)
            self.assertEqual(summary["quote_rows"], 2)
            self.assertEqual(summary["etf_holding_rows"], 4)

    def test_reset_recreates_target_only_with_sentinel(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "demo_runtime"
            prepare_demo_runtime(ROOT, target, reset=False)
            marker = target / "extra.txt"
            marker.write_text("remove me", encoding="utf-8")

            prepare_demo_runtime(ROOT, target, reset=True)

            self.assertFalse(marker.exists())
            self.assertTrue((target / SENTINEL_NAME).exists())

    def test_reset_refuses_target_without_sentinel(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "demo_runtime"
            target.mkdir()
            (target / "not-demo.txt").write_text("private data", encoding="utf-8")

            with self.assertRaises(RuntimeError):
                prepare_demo_runtime(ROOT, target, reset=True)

    def test_refuses_data_or_sample_data_targets(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            temp_root = Path(tmp)
            for name in ("data", "sample_data"):
                with self.subTest(name=name):
                    target = temp_root / name
                    with self.assertRaises(ValueError):
                        prepare_demo_runtime(ROOT, target, reset=False)

    def test_sentinel_marks_generated_demo_runtime(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "demo_runtime"
            prepare_demo_runtime(ROOT, target, reset=False)

            payload = json.loads((target / SENTINEL_NAME).read_text(encoding="utf-8"))

            self.assertTrue(payload["generated"])
            self.assertEqual(payload["source"], "sample_data")
            self.assertTrue(payload["safe_to_delete"])


def _scalar(db_path: Path, sql: str) -> int:
    conn = sqlite3.connect(db_path)
    try:
        row = conn.execute(sql).fetchone()
        return int(row[0] or 0)
    finally:
        conn.close()


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import csv
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from store import load_state, public_state_copy


class DemoDataGeneratorTests(unittest.TestCase):
    def test_generated_demo_profile_matches_current_state_shape(self) -> None:
        state = load_state(ROOT / "sample_data" / "profiles" / "demo" / "state.json")
        public_state = public_state_copy(state)

        self.assertEqual(public_state["settings"]["app_title"], "Synthetic Demo Account")
        self.assertEqual(len(public_state["holdings"]), 1)
        self.assertEqual(len(public_state["watchlist"]), 1)
        self.assertEqual(len(public_state["transactions"]), 3)
        self.assertEqual(len(public_state["dividend_movements"]), 1)

        holding = public_state["holdings"][0]
        self.assertEqual(holding["ticker"], "DEMOA")
        self.assertEqual(holding["shares"], 110)
        self.assertEqual(len(holding["lots"]), 2)
        self.assertEqual(holding["lots"][0]["remaining_shares"], 60)
        self.assertEqual(holding["lots"][1]["remaining_shares"], 50)

        sell = public_state["transactions"][-1]
        self.assertEqual(sell["action"], "SELL")
        self.assertGreater(sell["realized_pnl"], 0)
        self.assertEqual(len(sell["lots"]), 1)

    def test_generated_market_csv_has_enough_ohlcv_rows_for_demo_tickers(self) -> None:
        history_path = ROOT / "sample_data" / "market" / "ohlcv_daily.csv"
        quote_path = ROOT / "sample_data" / "market" / "quotes.csv"

        with history_path.open(newline="", encoding="utf-8") as file:
            history_rows = list(csv.DictReader(file))
        with quote_path.open(newline="", encoding="utf-8") as file:
            quote_rows = list(csv.DictReader(file))

        by_ticker: dict[str, int] = {}
        for row in history_rows:
            by_ticker[row["instrument_id"]] = by_ticker.get(row["instrument_id"], 0) + 1

        self.assertGreaterEqual(by_ticker.get("DEMOA", 0), 60)
        self.assertGreaterEqual(by_ticker.get("DEMOB", 0), 60)
        self.assertEqual({row["instrument_id"] for row in quote_rows}, {"DEMOA", "DEMOB"})
        self.assertTrue(all(row["source"] == "synthetic_demo" for row in history_rows + quote_rows))


if __name__ == "__main__":
    unittest.main()

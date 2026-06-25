from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from analyzer import build_dashboard_state
from server import find_duplicate_transaction
from store import rebuild_holdings_from_transactions, record_buy, record_sell


def empty_state() -> dict:
    return {
        "settings": {},
        "holdings": [],
        "watchlist": [],
        "transactions": [],
        "dividend_movements": [],
        "price_overrides": {},
    }


class AccountingRegressionTests(unittest.TestCase):
    def test_fifo_sell_consumes_oldest_lots_first(self) -> None:
        state = empty_state()
        record_buy(state, "2330", 10, 100, fee=10, trade_date="2026-01-01")
        record_buy(state, "2330", 10, 120, fee=20, trade_date="2026-01-02")

        record_sell(state, "2330", 15, 150, fee=15, tax=5, trade_date="2026-01-03")

        holding = state["holdings"][0]
        lots = holding["lots"]
        sell = state["transactions"][-1]

        self.assertEqual(lots[0]["remaining_shares"], 0)
        self.assertEqual(lots[1]["remaining_shares"], 5)
        self.assertEqual(
            sell["lots"],
            [
                {"date": "2026-01-01", "shares": 10, "cost_per_share": 101},
                {"date": "2026-01-02", "shares": 5, "cost_per_share": 122},
            ],
        )
        self.assertEqual(holding["shares"], 5)
        self.assertEqual(holding["avg_cost"], 122)

    def test_realized_profit_uses_fifo_cost_fee_and_tax(self) -> None:
        state = empty_state()
        record_buy(state, "2330", 10, 100, fee=10, trade_date="2026-01-01")
        record_buy(state, "2330", 10, 120, fee=20, trade_date="2026-01-02")

        record_sell(state, "2330", 15, 150, fee=15, tax=5, trade_date="2026-01-03")

        sell = state["transactions"][-1]
        self.assertEqual(sell["amount"], 2230)
        self.assertEqual(sell["realized_pnl"], 610)

    def test_manual_dividend_income_is_separate_from_market_calendar_data(self) -> None:
        raw_state = empty_state()
        raw_state["settings"] = {"cash_available": 0}
        raw_state["transactions"] = [
            {
                "time": "2026-01-03",
                "action": "SELL",
                "ticker": "2330",
                "shares": 5,
                "price": 150,
                "fee": 1,
                "tax": 1,
                "realized_pnl": 100,
            }
        ]
        raw_state["dividend_movements"] = [
            {"ticker": "2330", "received_date": "2026-01-10", "amount": 25}
        ]
        holdings = [
            {
                "ticker": "2330",
                "name": "Calendar Data Should Not Count As Income",
                "type": "ETF",
                "shares": 10,
                "avg_cost": 100,
                "monthly_dividend_est": 999,
                "annual_dividend_est": 9999,
                "ex_dividend_date": "2026-02-01",
                "payout_date": "2026-03-01",
                "quote": {"close": 110, "prev_close": 100},
            }
        ]

        dashboard = build_dashboard_state(raw_state, holdings, [], [])

        self.assertEqual(dashboard["summary"]["realized_trade_pnl_total"], 100)
        self.assertEqual(dashboard["summary"]["dividend_income_total"], 25)
        self.assertEqual(dashboard["summary"]["realized_pnl_total"], 125)

    def test_split_adjustment_rebuilds_remaining_shares_and_cost_basis(self) -> None:
        state = empty_state()
        state["transactions"] = [
            {
                "time": "2026-01-01",
                "action": "BUY",
                "ticker": "2330",
                "shares": 100,
                "price": 50,
                "fee": 0,
                "tax": 0,
            }
        ]

        rebuild_holdings_from_transactions(
            state,
            [
                {
                    "action_type": "split",
                    "ticker": "2330",
                    "effective_date": "2026-02-01",
                    "ratio_from": 1,
                    "ratio_to": 2,
                    "note": "2-for-1 split",
                }
            ],
        )

        holding = state["holdings"][0]
        lot = holding["lots"][0]
        self.assertEqual(holding["shares"], 200)
        self.assertEqual(holding["avg_cost"], 25)
        self.assertEqual(lot["shares"], 200)
        self.assertEqual(lot["remaining_shares"], 200)
        self.assertEqual(lot["price"], 25)
        self.assertEqual(lot["cost_per_share"], 25)
        self.assertEqual(holding["corporate_actions"][0]["ratio"], 2)

    def test_duplicate_transaction_detection_matches_normalized_transaction_key(self) -> None:
        state = {
            "transactions": [
                {
                    "time": "2026-01-03T09:30:00",
                    "action": "buy",
                    "ticker": "2330",
                    "shares": 100.00001,
                    "price": 50.00001,
                    "fee": 1.00001,
                    "tax": 0,
                }
            ]
        }

        duplicate = find_duplicate_transaction(
            state,
            action="BUY",
            ticker="2330",
            trade_date="2026-01-03",
            shares=100,
            price=50,
            fee=1,
            tax=0,
        )
        different_fee = find_duplicate_transaction(
            state,
            action="BUY",
            ticker="2330",
            trade_date="2026-01-03",
            shares=100,
            price=50,
            fee=2,
            tax=0,
        )

        self.assertIs(duplicate, state["transactions"][0])
        self.assertIsNone(different_fee)


if __name__ == "__main__":
    unittest.main()

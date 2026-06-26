from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from analyzer import build_dashboard_state
from server import find_duplicate_transaction, record_transaction_from_payload
from store import rebuild_holdings_from_transactions, record_buy, record_sell, trade_consideration_twd


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
    def test_trade_consideration_truncates_fractional_twd_like_broker_statement(self) -> None:
        self.assertEqual(trade_consideration_twd(34, 29.73), 1010)

    def test_buy_uses_truncated_twd_consideration_and_keeps_fee_separate(self) -> None:
        state = empty_state()

        record_buy(state, "2330", 34, 29.73, fee=1, trade_date="2026-01-01")

        transaction = state["transactions"][0]
        lot = state["holdings"][0]["lots"][0]
        self.assertEqual(transaction["gross_amount"], 1010)
        self.assertEqual(transaction["amount"], 1011)
        self.assertAlmostEqual(lot["cost_per_share"], 1011 / 34)

    def test_sell_uses_truncated_twd_consideration_and_keeps_fee_tax_separate(self) -> None:
        state = empty_state()
        record_buy(state, "2330", 34, 20, fee=0, trade_date="2026-01-01")

        record_sell(state, "2330", 34, 29.73, fee=1, tax=1, trade_date="2026-01-02")

        transaction = state["transactions"][-1]
        self.assertEqual(transaction["gross_amount"], 1010)
        self.assertEqual(transaction["amount"], 1008)

    def test_fifo_realized_profit_uses_truncated_buy_and_sell_consideration(self) -> None:
        state = empty_state()
        record_buy(state, "2330", 34, 29.73, fee=1, trade_date="2026-01-01")

        record_sell(state, "2330", 10, 30.25, fee=1, tax=0, trade_date="2026-01-02")

        sell = state["transactions"][-1]
        self.assertEqual(sell["gross_amount"], 302)
        self.assertAlmostEqual(sell["realized_pnl"], 302 - 1 - (10 * (1011 / 34)))

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

    def test_server_transaction_fee_estimate_uses_truncated_consideration(self) -> None:
        state = empty_state()
        state["settings"] = {"cash_available": 2000, "broker_fee_rate": 0.001485}
        with tempfile.TemporaryDirectory() as tmp:
            state_path = Path(tmp) / "state.json"
            state_path.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")

            result = record_transaction_from_payload(
                state_path,
                {
                    "action": "BUY",
                    "date": "2026-01-01",
                    "ticker": "2330",
                    "shares": 34,
                    "price": 29.73,
                },
            )

            updated = json.loads(state_path.read_text(encoding="utf-8"))

        transaction = updated["transactions"][0]
        self.assertEqual(result["gross_amount"], 1010)
        self.assertEqual(result["fee"], 1)
        self.assertEqual(result["cash_delta"], -1011)
        self.assertEqual(transaction["amount"], 1011)

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

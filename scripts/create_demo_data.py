from __future__ import annotations

import csv
import json
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from store import ensure_transaction_ids, record_buy, record_sell, upsert_watch


HELD_TICKER = "DEMOA"
WATCH_TICKER = "DEMOB"
SOURCE = "synthetic_demo"
START_DATE = date(2026, 1, 2)
ROW_COUNT = 75


def main() -> None:
    create_demo_data(ROOT)


def create_demo_data(root: Path) -> None:
    sample_root = root / "sample_data"
    profile_path = sample_root / "profiles" / "demo" / "state.json"
    market_dir = sample_root / "market"
    market_dir.mkdir(parents=True, exist_ok=True)
    profile_path.parent.mkdir(parents=True, exist_ok=True)

    state = demo_profile_state()
    profile_path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_quotes(market_dir / "quotes.csv")
    write_ohlcv(market_dir / "ohlcv_daily.csv")
    write_etf_holdings(market_dir / "etf_holdings.csv")


def demo_profile_state() -> dict:
    state: dict = {
        "settings": {
            "app_title": "Synthetic Demo Account",
            "currency": "USD",
            "cash_available": 25000,
            "refresh_seconds": 900,
            "scheduled_refresh_minutes": 15,
            "tw_refresh_window": "09:01-13:01",
            "us_refresh_window": "21:30-05:00",
            "important_signal_limit": 6,
            "broker_fee_rate": 0.001,
            "transaction_tax_rate": 0.001,
            "demo_data_notice": "Synthetic sample data only. Not investment advice.",
        },
        "holdings": [],
        "watchlist": [],
        "transactions": [],
        "cash_movements": [
            {
                "time": "2026-01-02",
                "action": "CASH_IN",
                "amount": 25000,
                "note": "Synthetic opening cash for demo account.",
            }
        ],
        "dividend_movements": [
            {
                "id": "demo_dividend_20260315_demoa",
                "ticker": HELD_TICKER,
                "time": "2026-03-15",
                "amount": 33.0,
                "note": "Synthetic received dividend for demo only.",
                "created_at": "2026-03-15T09:00:00+00:00",
            }
        ],
        "price_overrides": {},
    }

    record_buy(
        state,
        HELD_TICKER,
        shares=100,
        price=40.0,
        name="Demo Core ETF",
        asset_type="ETF",
        suffix=".DEMO",
        fee=4.0,
        trade_date="2026-01-05",
        note="Synthetic first buy.",
    )
    record_buy(
        state,
        HELD_TICKER,
        shares=50,
        price=44.0,
        name="Demo Core ETF",
        asset_type="ETF",
        suffix=".DEMO",
        fee=2.2,
        trade_date="2026-01-20",
        note="Synthetic second buy.",
    )
    record_sell(
        state,
        HELD_TICKER,
        shares=40,
        price=48.0,
        fee=1.92,
        tax=1.92,
        trade_date="2026-02-10",
        note="Synthetic partial sell to demonstrate FIFO realized profit.",
    )
    upsert_watch(
        state,
        WATCH_TICKER,
        name="Demo Watch Stock",
        suffix=".DEMO",
        target_buy_price=21.5,
        alert_price=27.0,
        reason="Synthetic watchlist item for demo.",
        note="No account position.",
    )
    state["watchlist"][0]["type"] = "STOCK"

    holding = state["holdings"][0]
    holding["monthly_dividend_est"] = 11.0
    holding["annual_dividend_est"] = 132.0
    holding["ex_dividend_date"] = "2026-03-10"
    holding["payout_date"] = "2026-03-15"
    holding["role"] = "demo"
    holding["note"] = "Synthetic holding. Not based on a real account."

    ensure_transaction_ids(state)
    return state


def write_quotes(path: Path) -> None:
    rows = [
        {
            "instrument_id": HELD_TICKER,
            "price": "49.20",
            "previous_close": "48.70",
            "change": "0.50",
            "change_pct": "1.0267",
            "source_timestamp": "2026-04-17T16:00:00+00:00",
            "freshness": "manual",
            "source": SOURCE,
            "currency": "USD",
        },
        {
            "instrument_id": WATCH_TICKER,
            "price": "24.35",
            "previous_close": "24.80",
            "change": "-0.45",
            "change_pct": "-1.8145",
            "source_timestamp": "2026-04-17T16:00:00+00:00",
            "freshness": "manual",
            "source": SOURCE,
            "currency": "USD",
        },
    ]
    write_csv(path, rows)


def write_ohlcv(path: Path) -> None:
    rows = price_series(HELD_TICKER, 40.0, 0.13, 110000) + price_series(WATCH_TICKER, 21.0, 0.045, 85000)
    write_csv(path, rows)


def write_etf_holdings(path: Path) -> None:
    rows = [
        {
            "etf_ticker": HELD_TICKER,
            "as_of_date": "2026-04-16",
            "source": SOURCE,
            "source_url": "",
            "status": "ok",
            "notes": "Synthetic demo ETF component snapshot.",
            "constituent_ticker": "DEMOX",
            "constituent_name": "Demo Component X",
            "weight": "35.50",
            "shares": "120000",
            "market_value": "4260000",
            "industry": "Demo Technology",
            "sort_order": "1",
        },
        {
            "etf_ticker": HELD_TICKER,
            "as_of_date": "2026-04-16",
            "source": SOURCE,
            "source_url": "",
            "status": "ok",
            "notes": "Synthetic demo ETF component snapshot.",
            "constituent_ticker": "DEMOY",
            "constituent_name": "Demo Component Y",
            "weight": "27.25",
            "shares": "90000",
            "market_value": "3270000",
            "industry": "Demo Finance",
            "sort_order": "2",
        },
        {
            "etf_ticker": HELD_TICKER,
            "as_of_date": "2026-04-16",
            "source": SOURCE,
            "source_url": "",
            "status": "ok",
            "notes": "Synthetic demo ETF component snapshot.",
            "constituent_ticker": "DEMOZ",
            "constituent_name": "Demo Component Z",
            "weight": "22.75",
            "shares": "75000",
            "market_value": "2730000",
            "industry": "Demo Industry",
            "sort_order": "3",
        },
        {
            "etf_ticker": HELD_TICKER,
            "as_of_date": "2026-04-16",
            "source": SOURCE,
            "source_url": "",
            "status": "ok",
            "notes": "Synthetic demo ETF component snapshot.",
            "constituent_ticker": "DEMOCASH",
            "constituent_name": "Demo Cash Position",
            "weight": "14.50",
            "shares": "",
            "market_value": "1740000",
            "industry": "Cash",
            "sort_order": "4",
        },
    ]
    write_csv(path, rows)


def price_series(instrument_id: str, base: float, slope: float, base_volume: int) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for index, day in enumerate(trading_days(START_DATE, ROW_COUNT)):
        wave = ((index % 9) - 4) * 0.08
        close = round(base + index * slope + wave, 2)
        open_price = round(close - 0.18 + ((index % 5) * 0.04), 2)
        high = round(max(open_price, close) + 0.42 + ((index % 3) * 0.03), 2)
        low = round(min(open_price, close) - 0.38 - ((index % 4) * 0.02), 2)
        volume = base_volume + index * 900 + (index % 7) * 450
        rows.append(
            {
                "instrument_id": instrument_id,
                "date": day.isoformat(),
                "open": f"{open_price:.2f}",
                "high": f"{high:.2f}",
                "low": f"{low:.2f}",
                "close": f"{close:.2f}",
                "volume": str(volume),
                "value": f"{close * volume:.2f}",
                "source_timestamp": datetime.combine(day, datetime.min.time(), tzinfo=timezone.utc)
                .replace(hour=16)
                .isoformat(),
                "freshness": "end_of_day",
                "source": SOURCE,
                "adjusted": "false",
            }
        )
    return rows


def trading_days(start: date, count: int) -> list[date]:
    days: list[date] = []
    current = start
    while len(days) < count:
        if current.weekday() < 5:
            days.append(current)
        current += timedelta(days=1)
    return days


def write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    if not rows:
        raise ValueError(f"No rows to write: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0].keys()), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


if __name__ == "__main__":
    main()

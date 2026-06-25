from __future__ import annotations

from datetime import date
from typing import Any

import pandas as pd

from utils import as_float, pct, safe_subtract


IMPORTANT_KEYWORDS = ("可賣", "部分獲利", "停損", "不追高", "到達", "觸發")


def build_dashboard_state(
    raw_state: dict[str, Any],
    holdings: list[dict[str, Any]],
    watchlist: list[dict[str, Any]],
    markets: list[dict[str, Any]],
) -> dict[str, Any]:
    today = date.today()
    settings = raw_state.get("settings", {})
    analyzed_holdings = [_analyze_holding(item, today, settings) for item in holdings]
    analyzed_watchlist = [_analyze_watch(item) for item in watchlist]
    important = _important_signals(analyzed_holdings, analyzed_watchlist)

    total_market_value = sum(item.get("market_value") or 0 for item in analyzed_holdings)
    total_cost_value = sum(item.get("cost_value") or 0 for item in analyzed_holdings)
    total_pnl = sum(item.get("unrealized_pnl") or 0 for item in analyzed_holdings)
    total_pnl_pct = pct(total_pnl, total_cost_value)
    realized_trade_pnl_total = _realized_pnl_total(raw_state.get("transactions", []))
    dividend_movements = raw_state.get("dividend_movements", [])
    dividend_income_total = sum(
        as_float(item.get("amount"), 0) or 0
        for item in dividend_movements
        if isinstance(item, dict)
    )
    if not dividend_movements:
        dividend_income_total = as_float(settings.get("dividend_income_total"), 0) or 0
    realized_pnl_total = realized_trade_pnl_total + dividend_income_total

    return {
        "settings": raw_state.get("settings", {}),
        "summary": {
            "total_market_value": total_market_value,
            "total_cost_value": total_cost_value,
            "total_pnl": total_pnl,
            "total_pnl_pct": total_pnl_pct,
            "realized_pnl_total": realized_pnl_total,
            "realized_trade_pnl_total": realized_trade_pnl_total,
            "dividend_income_total": dividend_income_total,
            "cash_available": raw_state.get("settings", {}).get("cash_available", 0),
            "important_count": len(important),
        },
        "markets": _analyze_markets(markets),
        "holdings": sorted(analyzed_holdings, key=lambda row: row["priority"], reverse=True),
        "watchlist": sorted(analyzed_watchlist, key=lambda row: row["priority"], reverse=True),
        "important": important,
        "transactions": list(reversed(raw_state.get("transactions", [])[-8:])),
        "dividend_movements": list(reversed(dividend_movements)),
    }


def _realized_pnl_total(transactions: list[dict[str, Any]]) -> float:
    total = 0.0
    for item in transactions:
        if str(item.get("action", "")).strip().upper() != "SELL":
            continue
        realized = as_float(item.get("realized_pnl"))
        if realized is not None:
            total += realized
    return total


def _analyze_markets(markets: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for item in markets:
        quote = item["quote"]
        rows.append(
            {
                "key": item["key"],
                "label": item["label"],
                "symbol": item["symbol"],
                "close": quote.get("display_close", quote.get("close")),
                "change_pct": quote.get("change_pct"),
                "status": quote.get("status", ""),
                "source": quote.get("source", ""),
            }
        )
    return rows


def _analyze_holding(item: dict[str, Any], today: date, settings: dict[str, Any]) -> dict[str, Any]:
    quote = item.get("quote", {})
    broker = item.get("broker", {}) if isinstance(item.get("broker"), dict) else {}
    shares = as_float(item.get("shares"), 0) or 0
    avg_cost = as_float(item.get("avg_cost"), 0) or 0
    close = as_float(quote.get("close"))
    prev_close = as_float(quote.get("prev_close"))
    change = safe_subtract(close, prev_close)
    change_pct = pct(change, prev_close)
    market_value = close * shares if close is not None else None
    cost_value = shares * avg_cost

    calculated_pnl = safe_subtract(market_value, cost_value)
    unrealized_pnl = as_float(broker.get("pnl"), calculated_pnl)
    pnl_pct = as_float(broker.get("pnl_pct"), pct(unrealized_pnl, cost_value))
    breakeven_price = as_float(broker.get("breakeven_price"))
    if breakeven_price is None and shares > 0 and avg_cost > 0:
        fee_rate = as_float(settings.get("broker_fee_rate"), 0) or 0
        tax_rate = as_float(settings.get("transaction_tax_rate"), 0) or 0
        sell_rate = fee_rate + tax_rate
        breakeven_price = avg_cost / (1 - sell_rate) if sell_rate < 1 else avg_cost
    monthly_dividend = as_float(item.get("monthly_dividend_est"), 0) or 0
    dividend_months = unrealized_pnl / monthly_dividend if unrealized_pnl is not None and monthly_dividend > 0 else None
    days_to_ex = _days_to(item.get("ex_dividend_date"), today)
    signals = _holding_signals(item, shares, pnl_pct, dividend_months, days_to_ex)
    source_badges = _holding_source_badges(item, quote)

    return {
        **item,
        "quote": quote,
        "broker": broker,
        "shares": shares,
        "avg_cost": avg_cost,
        "close": close,
        "change_pct": change_pct,
        "market_value": market_value,
        "cost_value": cost_value,
        "calculated_unrealized_pnl": calculated_pnl,
        "unrealized_pnl": unrealized_pnl,
        "pnl_pct": pnl_pct,
        "breakeven_price": breakeven_price,
        "dividend_months": dividend_months,
        "days_to_ex_dividend": days_to_ex,
        "signals": signals,
        "source_badges": source_badges,
        "priority": _priority(signals),
    }


def _analyze_watch(item: dict[str, Any]) -> dict[str, Any]:
    quote = item.get("quote", {})
    close = as_float(quote.get("close"))
    prev_close = as_float(quote.get("prev_close"))
    change = safe_subtract(close, prev_close)
    change_pct = pct(change, prev_close)
    signals = []

    target_buy = as_float(item.get("target_buy_price"))
    alert = as_float(item.get("alert_price"))
    stop_loss = as_float(item.get("stop_loss_price"))
    target_sell = as_float(item.get("target_sell_price"))

    if close is None:
        signals.append("價格 N/A")
    else:
        if target_buy is not None and close <= target_buy:
            signals.append("到達買價")
        if alert is not None and close >= alert:
            signals.append("觸發提醒")
        if stop_loss is not None and close <= stop_loss:
            signals.append("跌破停損")
        if target_sell is not None and close >= target_sell:
            signals.append("到達賣價")

    if not signals:
        signals.append("未觸發" if any(value is not None for value in [target_buy, alert, stop_loss, target_sell]) else "僅觀察")

    return {
        **item,
        "quote": quote,
        "close": close,
        "change_pct": change_pct,
        "target_buy_price": target_buy,
        "alert_price": alert,
        "stop_loss_price": stop_loss,
        "target_sell_price": target_sell,
        "signals": signals,
        "priority": _priority(signals),
    }


def _holding_signals(
    item: dict[str, Any],
    shares: float,
    pnl_pct: float | None,
    dividend_months: float | None,
    days_to_ex: int | None,
) -> list[str]:
    asset_type = str(item.get("type", "")).upper()
    if asset_type == "ETF":
        if dividend_months is None:
            signals = ["人工判斷"]
        elif dividend_months < 12:
            signals = ["續抱"]
        elif dividend_months < 24:
            signals = ["觀察獲利"]
        elif dividend_months < 36:
            signals = ["可賣30%"]
        else:
            signals = ["可賣40-50%"]

        if days_to_ex is not None and 0 <= days_to_ex <= 14:
            signals.append("近除息不追高")
        return signals

    if shares <= 0:
        return ["觀察"]
    if pnl_pct is not None and pnl_pct >= 10:
        return ["可部分獲利"]
    if pnl_pct is not None and pnl_pct <= -5:
        return ["檢查停損"]
    return ["續抱"]


def _important_signals(holdings: list[dict[str, Any]], watchlist: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for source, items in [("持股", holdings), ("觀察", watchlist)]:
        for item in items:
            important_signals = [signal for signal in item["signals"] if _is_important(signal)]
            if important_signals:
                rows.append(
                    {
                        "source": source,
                        "ticker": item.get("ticker"),
                        "name": item.get("name"),
                        "signals": important_signals,
                        "priority": _priority(important_signals),
                    }
                )
    return sorted(rows, key=lambda row: row["priority"], reverse=True)


def _priority(signals: list[str]) -> int:
    return sum(1 for signal in signals if _is_important(signal))


def _is_important(signal: str) -> bool:
    return any(word in signal for word in IMPORTANT_KEYWORDS)


def _days_to(value: object, today: date) -> int | None:
    if value in (None, ""):
        return None
    parsed = pd.to_datetime(str(value), errors="coerce")
    if pd.isna(parsed):
        return None
    return (parsed.date() - today).days


def _holding_source_badges(item: dict[str, Any], quote: dict[str, Any]) -> list[dict[str, str]]:
    badges: list[dict[str, str]] = []
    source_market = str(quote.get("source_market", "") or "").upper()
    quote_source = str(quote.get("source", "") or "").lower()
    if source_market == "TWSE":
        badges.append({"label": "收盤 證交所", "tone": "official"})
    elif source_market == "TPEX":
        badges.append({"label": "收盤 櫃買", "tone": "official"})
    elif quote_source == "yfinance":
        badges.append({"label": "收盤 Yahoo", "tone": "yahoo"})

    after_close = item.get("after_close_quote") if isinstance(item.get("after_close_quote"), dict) else {}
    after_close_source = str(after_close.get("source", "") or "").lower()
    if after_close_source == "yfinance":
        badges.append({"label": "盤後 Yahoo", "tone": "yahoo"})

    has_dividend_fields = any(
        item.get(field) not in (None, "", 0)
        for field in ("monthly_dividend_est", "annual_dividend_est", "ex_dividend_date", "payout_date")
    )
    if has_dividend_fields:
        dividend_source = str(item.get("dividend_source", "") or "").strip().lower()
        if dividend_source in {"twse", "tpex"}:
            source_label = "股利 證交所" if dividend_source == "twse" else "股利 櫃買"
            badges.append({"label": source_label, "tone": "official"})
        elif dividend_source == "yahoo":
            badges.append({"label": "股利 Yahoo", "tone": "yahoo"})
        else:
            badges.append({"label": "股利 手填", "tone": "manual"})

    return badges

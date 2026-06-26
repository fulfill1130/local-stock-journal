from __future__ import annotations

import json
import os
import tempfile
from copy import deepcopy
from decimal import Decimal, ROUND_DOWN
from hashlib import sha1
from pathlib import Path
from typing import Any, Callable

from utils import as_float, now_iso


def load_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"State file not found: {path}")
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def save_state(path: Path, state: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        delete=False,
        dir=str(path.parent),
        suffix=".tmp",
    ) as tmp:
        json.dump(state, tmp, ensure_ascii=False, indent=2)
        tmp.write("\n")
        tmp_path = Path(tmp.name)
    os.replace(tmp_path, path)


def update_state(path: Path, mutator: Callable[[dict[str, Any]], None]) -> dict[str, Any]:
    state = load_state(path)
    mutator(state)
    save_state(path, state)
    return state


def trade_consideration_twd(shares: Any, price: Any) -> int:
    """Taiwan broker statements truncate fractional TWD after price times shares."""
    consideration = Decimal(str(price)) * Decimal(str(shares))
    return int(consideration.to_integral_value(rounding=ROUND_DOWN))


def record_buy(
    state: dict[str, Any],
    ticker: str,
    shares: float,
    price: float,
    name: str | None = None,
    asset_type: str = "STOCK",
    suffix: str = ".TW",
    fee: float = 0.0,
    trade_date: str | None = None,
    note: str = "",
) -> None:
    if shares <= 0 or price <= 0:
        raise ValueError("Buy shares and price must be greater than 0.")
    if fee < 0:
        raise ValueError("Fee cannot be negative.")

    holding = _find_item(state.setdefault("holdings", []), ticker)
    if holding is None:
        holding = {
            "ticker": ticker,
            "name": name or ticker,
            "type": asset_type.upper(),
            "exchange_suffix": suffix,
            "shares": 0,
            "avg_cost": 0,
            "monthly_dividend_est": 0,
            "annual_dividend_est": 0,
            "ex_dividend_date": "",
            "payout_date": "",
            "role": "",
            "note": note,
        }
        state["holdings"].append(holding)
    else:
        _ensure_lots_for_holding(state, holding, ticker)

    holding.setdefault("lots", []).append(
        {
            "date": trade_date or now_iso(),
            "shares": shares,
            "remaining_shares": shares,
            "price": price,
            "fee": fee,
            "cost_per_share": (trade_consideration_twd(shares, price) + fee) / shares,
        }
    )
    _recalculate_holding_from_lots(holding)
    holding.pop("broker", None)
    if name:
        holding["name"] = name
    if note:
        holding["note"] = note

    _append_transaction(state, "BUY", ticker, shares, price, fee, 0.0, None, note, trade_date)


def record_sell(
    state: dict[str, Any],
    ticker: str,
    shares: float,
    price: float,
    fee: float = 0.0,
    tax: float = 0.0,
    trade_date: str | None = None,
    note: str = "",
) -> None:
    if shares <= 0 or price <= 0:
        raise ValueError("Sell shares and price must be greater than 0.")
    if fee < 0:
        raise ValueError("Fee cannot be negative.")
    if tax < 0:
        raise ValueError("Tax cannot be negative.")

    holding = _find_item(state.setdefault("holdings", []), ticker)
    if holding is None:
        raise ValueError(f"Holding not found: {ticker}")

    old_shares = as_float(holding.get("shares"), 0) or 0
    if shares > old_shares:
        raise ValueError(f"{ticker} has only {old_shares:g} shares; cannot sell {shares:g}.")

    consumed = _consume_fifo_lots(state, holding, ticker, shares)
    realized_cost = sum(item["shares"] * item["cost_per_share"] for item in consumed)
    gross_amount = trade_consideration_twd(shares, price)
    net_amount = gross_amount - fee - tax
    realized_pnl = net_amount - realized_cost
    _recalculate_holding_from_lots(holding)
    holding.pop("broker", None)
    _append_transaction(
        state,
        "SELL",
        ticker,
        shares,
        price,
        fee,
        tax,
        realized_pnl,
        note,
        trade_date,
        consumed,
    )


def upsert_watch(
    state: dict[str, Any],
    ticker: str,
    name: str | None = None,
    suffix: str = ".TW",
    target_buy_price: float | None = None,
    alert_price: float | None = None,
    stop_loss_price: float | None = None,
    target_sell_price: float | None = None,
    reason: str = "",
    note: str = "",
) -> None:
    watchlist = state.setdefault("watchlist", [])
    item = _find_item(watchlist, ticker)
    if item is None:
        item = {
            "ticker": ticker,
            "name": name or ticker,
            "type": "STOCK",
            "exchange_suffix": suffix,
            "target_buy_price": None,
            "alert_price": None,
            "stop_loss_price": None,
            "target_sell_price": None,
            "reason": reason,
            "note": note,
        }
        watchlist.append(item)

    updates = {
        "name": name,
        "exchange_suffix": suffix,
        "target_buy_price": target_buy_price,
        "alert_price": alert_price,
        "stop_loss_price": stop_loss_price,
        "target_sell_price": target_sell_price,
        "reason": reason,
        "note": note,
    }
    for key, value in updates.items():
        if value not in (None, ""):
            item[key] = value


def remove_watch(state: dict[str, Any], ticker: str) -> None:
    ticker = str(ticker).strip().upper()
    state["watchlist"] = [
        item for item in state.get("watchlist", [])
        if str(item.get("ticker", "")).strip().upper() != ticker
    ]


def set_price_override(
    state: dict[str, Any],
    symbol: str,
    close: float,
    prev_close: float | None = None,
    note: str = "",
) -> None:
    if close <= 0:
        raise ValueError("Manual close price must be greater than 0.")
    if prev_close is not None and prev_close <= 0:
        raise ValueError("Manual previous close must be greater than 0.")

    override = {
        "close": close,
        "updated_at": now_iso(),
        "note": note,
    }
    if prev_close is not None:
        override["prev_close"] = prev_close
    state.setdefault("price_overrides", {})[symbol] = override


def set_cash(state: dict[str, Any], amount: float) -> None:
    if amount < 0:
        raise ValueError("Cash cannot be negative.")
    state.setdefault("settings", {})["cash_available"] = amount


def _append_transaction(
    state: dict[str, Any],
    action: str,
    ticker: str,
    shares: float,
    price: float,
    fee: float,
    tax: float,
    realized_pnl: float | None,
    note: str,
    trade_date: str | None = None,
    lots: list[dict[str, Any]] | None = None,
) -> None:
    gross_amount = trade_consideration_twd(shares, price)
    amount = gross_amount + fee if action == "BUY" else gross_amount - fee - tax
    state.setdefault("transactions", []).append(
        {
            "time": trade_date or now_iso(),
            "action": action,
            "ticker": ticker,
            "shares": shares,
            "price": price,
            "gross_amount": gross_amount,
            "fee": fee,
            "tax": tax,
            "amount": amount,
            "realized_pnl": realized_pnl,
            "lots": lots or [],
            "note": note,
        }
    )


def public_state_copy(state: dict[str, Any]) -> dict[str, Any]:
    copied = deepcopy(state)
    ensure_transaction_ids(copied)
    for holding in copied.get("holdings", []):
        ticker = str(holding.get("ticker", "")).strip()
        if ticker:
            _ensure_lots_for_holding(copied, holding, ticker)
    return copied


def ensure_transaction_ids(state: dict[str, Any]) -> bool:
    changed = False
    seen: set[str] = set()
    for index, transaction in enumerate(state.setdefault("transactions", [])):
        current = str(transaction.get("id", "")).strip()
        if current and current not in seen:
            seen.add(current)
            continue
        seed = json.dumps(
            {
                "index": index,
                "time": transaction.get("time", ""),
                "action": transaction.get("action", ""),
                "ticker": transaction.get("ticker", ""),
                "shares": transaction.get("shares", ""),
                "price": transaction.get("price", ""),
                "fee": transaction.get("fee", ""),
                "tax": transaction.get("tax", ""),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
        new_id = "tx_" + sha1(seed.encode("utf-8")).hexdigest()[:16]
        suffix = 1
        unique_id = new_id
        while unique_id in seen:
            suffix += 1
            unique_id = f"{new_id}_{suffix}"
        transaction["id"] = unique_id
        seen.add(unique_id)
        changed = True
    return changed


def rebuild_holdings_from_transactions(
    state: dict[str, Any],
    corporate_actions: list[dict[str, Any]] | None = None,
) -> None:
    ensure_transaction_ids(state)
    split_actions = _split_actions_by_ticker(corporate_actions or [])
    metadata = {
        str(item.get("ticker", "")).strip().upper(): deepcopy(item)
        for item in state.get("holdings", [])
        if str(item.get("ticker", "")).strip()
    }
    rebuilt: dict[str, dict[str, Any]] = {}

    def holding_for(ticker: str) -> dict[str, Any]:
        normalized = str(ticker).strip().upper()
        if normalized in rebuilt:
            return rebuilt[normalized]
        meta = metadata.get(normalized, {})
        holding = {
            "ticker": normalized,
            "name": meta.get("name") or normalized,
            "type": meta.get("type") or "STOCK",
            "exchange_suffix": meta.get("exchange_suffix") or ".TW",
            "shares": 0,
            "avg_cost": 0,
            "monthly_dividend_est": meta.get("monthly_dividend_est", 0),
            "annual_dividend_est": meta.get("annual_dividend_est", 0),
            "ex_dividend_date": meta.get("ex_dividend_date", ""),
            "payout_date": meta.get("payout_date", ""),
            "role": meta.get("role", ""),
            "note": meta.get("note", ""),
            "no_dividend": bool(meta.get("no_dividend", False)),
            "dividend_policy": meta.get("dividend_policy", ""),
            "lots": [],
            "corporate_actions": [],
        }
        rebuilt[normalized] = holding
        return holding

    applied_actions: dict[str, set[str]] = {}
    ordered_transactions = sorted(
        enumerate(state.get("transactions", [])),
        key=lambda item: (str(item[1].get("time", ""))[:10], item[0]),
    )
    for _, transaction in ordered_transactions:
        ticker = str(transaction.get("ticker", "")).strip().upper()
        action = str(transaction.get("action", "")).strip().upper()
        shares = as_float(transaction.get("shares"), 0) or 0
        price = as_float(transaction.get("price"), 0) or 0
        fee = as_float(transaction.get("fee"), 0) or 0
        tax = as_float(transaction.get("tax"), 0) or 0
        if not ticker or shares <= 0 or price <= 0:
            continue
        holding = holding_for(ticker)
        _apply_due_split_actions(
            holding,
            split_actions.get(ticker, []),
            applied_actions.setdefault(ticker, set()),
            str(transaction.get("time", ""))[:10],
        )
        if action == "BUY":
            holding.setdefault("lots", []).append(
                {
                    "date": transaction.get("time", ""),
                    "shares": shares,
                    "remaining_shares": shares,
                    "price": price,
                    "fee": fee,
                    "cost_per_share": (trade_consideration_twd(shares, price) + fee) / shares,
                }
            )
            _recalculate_holding_from_lots(holding)
        elif action == "SELL":
            try:
                consumed = _consume_fifo_lot_list(holding.setdefault("lots", []), shares)
            except ValueError:
                if bool(transaction.get("conflict_acknowledged", False)):
                    transaction.pop("conflict", None)
                    continue
                transaction["conflict"] = "庫存不足，請檢查前面買入或賣出紀錄"
                continue
            realized_cost = sum(item["shares"] * item["cost_per_share"] for item in consumed)
            transaction["lots"] = consumed
            transaction["realized_pnl"] = trade_consideration_twd(shares, price) - fee - tax - realized_cost
            transaction.pop("conflict", None)
            _recalculate_holding_from_lots(holding)

    today_text = now_iso()[:10]
    for ticker, holding in rebuilt.items():
        _apply_due_split_actions(
            holding,
            split_actions.get(ticker, []),
            applied_actions.setdefault(ticker, set()),
            today_text,
        )
        _recalculate_holding_from_lots(holding)

    state["holdings"] = [
        holding for holding in rebuilt.values()
        if (as_float(holding.get("shares"), 0) or 0) > 0
    ]


def _find_item(items: list[dict[str, Any]], ticker: str) -> dict[str, Any] | None:
    ticker = str(ticker).strip().upper()
    for item in items:
        if str(item.get("ticker", "")).strip().upper() == ticker:
            return item
    return None


def _split_actions_by_ticker(actions: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for action in actions:
        if str(action.get("action_type", "")).strip().lower() != "split":
            continue
        ticker = str(action.get("ticker", "")).strip().upper()
        effective_date = str(action.get("effective_date", "")).strip()[:10]
        ratio_from = as_float(action.get("ratio_from"), 0) or 0
        ratio_to = as_float(action.get("ratio_to"), 0) or 0
        if not ticker or not effective_date or ratio_from <= 0 or ratio_to <= 0:
            continue
        normalized = dict(action)
        normalized["effective_date"] = effective_date
        normalized["ratio_from"] = ratio_from
        normalized["ratio_to"] = ratio_to
        normalized["ratio"] = ratio_to / ratio_from
        grouped.setdefault(ticker, []).append(normalized)
    for rows in grouped.values():
        rows.sort(key=lambda row: str(row.get("effective_date", "")))
    return grouped


def _apply_due_split_actions(
    holding: dict[str, Any],
    actions: list[dict[str, Any]],
    applied: set[str],
    trade_date: str,
) -> None:
    trade_date = str(trade_date or "")[:10]
    if not trade_date:
        return
    for action in actions:
        effective_date = str(action.get("effective_date", ""))[:10]
        action_key = f"{action.get('action_type', 'split')}:{effective_date}"
        if not effective_date or action_key in applied or effective_date > trade_date:
            continue
        ratio = as_float(action.get("ratio"), 0) or 0
        if ratio <= 0:
            continue
        changed = False
        for lot in holding.setdefault("lots", []):
            lot_date = str(lot.get("date", ""))[:10]
            if lot_date and lot_date >= effective_date:
                continue
            shares = as_float(lot.get("shares"), 0) or 0
            remaining = as_float(lot.get("remaining_shares"), 0) or 0
            price = as_float(lot.get("price"), 0) or 0
            cost_per_share = as_float(lot.get("cost_per_share"), 0) or 0
            lot["shares"] = shares * ratio
            lot["remaining_shares"] = remaining * ratio
            if price:
                lot["price"] = price / ratio
            if cost_per_share:
                lot["cost_per_share"] = cost_per_share / ratio
            lot.setdefault("split_adjustments", []).append(
                {
                    "effective_date": effective_date,
                    "ratio_from": action.get("ratio_from"),
                    "ratio_to": action.get("ratio_to"),
                    "ratio": ratio,
                    "note": action.get("note", ""),
                }
            )
            changed = True
        if changed:
            holding.setdefault("corporate_actions", []).append(
                {
                    "action_type": "split",
                    "effective_date": effective_date,
                    "ratio_from": action.get("ratio_from"),
                    "ratio_to": action.get("ratio_to"),
                    "ratio": ratio,
                    "note": action.get("note", ""),
                }
            )
            _recalculate_holding_from_lots(holding)
        applied.add(action_key)


def _consume_fifo_lots(
    state: dict[str, Any],
    holding: dict[str, Any],
    ticker: str,
    sell_shares: float,
) -> list[dict[str, Any]]:
    _ensure_lots_for_holding(state, holding, ticker)
    lots = holding.setdefault("lots", [])

    remaining_to_sell = sell_shares
    consumed = []
    for lot in lots:
        available = as_float(lot.get("remaining_shares"), 0) or 0
        if available <= 0:
            continue
        used = min(available, remaining_to_sell)
        lot["remaining_shares"] = available - used
        consumed.append(
            {
                "date": lot.get("date", ""),
                "shares": used,
                "cost_per_share": as_float(lot.get("cost_per_share"), 0) or 0,
            }
        )
        remaining_to_sell -= used
        if remaining_to_sell <= 0:
            break

    if remaining_to_sell > 0:
        raise ValueError("Not enough FIFO lots to complete sell.")
    return consumed


def _ensure_lots_for_holding(state: dict[str, Any], holding: dict[str, Any], ticker: str) -> None:
    lots = holding.setdefault("lots", [])
    if lots:
        return

    rebuilt = _rebuild_lots_from_transactions(state, ticker)
    holding_shares = as_float(holding.get("shares"), 0) or 0
    rebuilt_shares = sum(as_float(lot.get("remaining_shares"), 0) or 0 for lot in rebuilt)
    if rebuilt and abs(rebuilt_shares - holding_shares) < 0.000001:
        holding["lots"] = rebuilt
        return

    _ensure_legacy_lot_if_needed(holding)


def _rebuild_lots_from_transactions(state: dict[str, Any], ticker: str) -> list[dict[str, Any]]:
    normalized = str(ticker).strip().upper()
    lots: list[dict[str, Any]] = []
    for tx in state.get("transactions", []):
        if str(tx.get("ticker", "")).strip().upper() != normalized:
            continue
        action = str(tx.get("action", "")).upper()
        shares = as_float(tx.get("shares"), 0) or 0
        price = as_float(tx.get("price"), 0) or 0
        fee = as_float(tx.get("fee"), 0) or 0
        if shares <= 0:
            continue

        if action == "BUY":
            lots.append(
                {
                    "date": tx.get("time", ""),
                    "shares": shares,
                    "remaining_shares": shares,
                    "price": price,
                    "fee": fee,
                    "cost_per_share": (trade_consideration_twd(shares, price) + fee) / shares if shares else 0,
                }
            )
        elif action == "SELL":
            _consume_lot_list(lots, shares)
    return lots


def _consume_lot_list(lots: list[dict[str, Any]], sell_shares: float) -> None:
    remaining_to_sell = sell_shares
    for lot in lots:
        available = as_float(lot.get("remaining_shares"), 0) or 0
        if available <= 0:
            continue
        used = min(available, remaining_to_sell)
        lot["remaining_shares"] = available - used
        remaining_to_sell -= used
        if remaining_to_sell <= 0:
            return


def _consume_fifo_lot_list(lots: list[dict[str, Any]], sell_shares: float) -> list[dict[str, Any]]:
    remaining_to_sell = sell_shares
    consumed = []
    for lot in lots:
        available = as_float(lot.get("remaining_shares"), 0) or 0
        if available <= 0:
            continue
        used = min(available, remaining_to_sell)
        lot["remaining_shares"] = available - used
        consumed.append(
            {
                "date": lot.get("date", ""),
                "shares": used,
                "cost_per_share": as_float(lot.get("cost_per_share"), 0) or 0,
            }
        )
        remaining_to_sell -= used
        if remaining_to_sell <= 0:
            return consumed
    raise ValueError("Not enough FIFO lots to complete sell.")


def _ensure_legacy_lot_if_needed(holding: dict[str, Any]) -> None:
    lots = holding.setdefault("lots", [])
    if lots:
        return
    shares = as_float(holding.get("shares"), 0) or 0
    if shares <= 0:
        return
    avg_cost = as_float(holding.get("avg_cost"), 0) or 0
    lots.append(
        {
            "date": "legacy",
            "shares": shares,
            "remaining_shares": shares,
            "price": avg_cost,
            "fee": 0,
            "cost_per_share": avg_cost,
        }
    )


def _recalculate_holding_from_lots(holding: dict[str, Any]) -> None:
    lots = holding.get("lots", [])
    remaining_shares = sum(as_float(lot.get("remaining_shares"), 0) or 0 for lot in lots)
    remaining_cost = sum(
        (as_float(lot.get("remaining_shares"), 0) or 0)
        * (as_float(lot.get("cost_per_share"), 0) or 0)
        for lot in lots
    )
    holding["shares"] = remaining_shares
    holding["avg_cost"] = remaining_cost / remaining_shares if remaining_shares else 0

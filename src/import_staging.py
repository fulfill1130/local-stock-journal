from __future__ import annotations

import json
import uuid
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Any

from store import trade_consideration_twd
from utils import as_float, now_iso


SUPPORTED_TRANSACTION_ACTIONS = {"BUY", "SELL"}


def validate_import_payload(
    payload: dict[str, Any] | list[dict[str, Any]],
    *,
    profile: str,
    existing_transactions: list[dict[str, Any]] | None = None,
    batch_id: str | None = None,
    created_at: str | None = None,
) -> dict[str, Any]:
    timestamp = created_at or now_iso()
    normalized_batch_id = batch_id or f"import_{datetime.now().astimezone():%Y%m%d_%H%M%S}_{uuid.uuid4().hex[:8]}"
    source_payload, transaction_rows, dividend_rows, cash_rows = _split_payload(payload)

    rows: list[dict[str, Any]] = []
    for index, row in enumerate(transaction_rows):
        rows.append(
            _validate_transaction_row(
                row,
                index=index,
                existing_transactions=existing_transactions or [],
            )
        )
    for index, row in enumerate(dividend_rows):
        rows.append(_unsupported_row(row, kind="dividend_movement", index=index))
    for index, row in enumerate(cash_rows):
        rows.append(_unsupported_row(row, kind="cash_movement", index=index))

    return {
        "batch_id": normalized_batch_id,
        "profile": str(profile or "").strip(),
        "status": "draft",
        "created_at": timestamp,
        "updated_at": timestamp,
        "source": _source_summary(source_payload),
        "raw_payload": deepcopy(payload),
        "rows": rows,
    }


def create_import_staging_batch(
    staging_root: Path,
    *,
    profile: str,
    payload: dict[str, Any] | list[dict[str, Any]],
    existing_transactions: list[dict[str, Any]] | None = None,
    batch_id: str | None = None,
    created_at: str | None = None,
) -> dict[str, Any]:
    batch = validate_import_payload(
        payload,
        profile=profile,
        existing_transactions=existing_transactions,
        batch_id=batch_id,
        created_at=created_at,
    )
    target = Path(staging_root) / str(profile).strip() / batch["batch_id"]
    target.mkdir(parents=True, exist_ok=False)
    batch_path = target / "batch.json"
    batch_path.write_text(json.dumps(batch, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    result = deepcopy(batch)
    result["path"] = str(batch_path)
    return result


def _split_payload(
    payload: dict[str, Any] | list[dict[str, Any]],
) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    if isinstance(payload, list):
        return {}, [row for row in payload if isinstance(row, dict)], [], []
    if not isinstance(payload, dict):
        raise ValueError("Import payload must be a JSON object or an array of transaction rows.")
    transactions = payload.get("transactions", [])
    if not isinstance(transactions, list):
        transactions = []
    dividends = payload.get("dividend_movements", [])
    if not isinstance(dividends, list):
        dividends = []
    cash_movements = payload.get("cash_movements", [])
    if not isinstance(cash_movements, list):
        cash_movements = []
    return (
        payload,
        [row for row in transactions if isinstance(row, dict)],
        [row for row in dividends if isinstance(row, dict)],
        [row for row in cash_movements if isinstance(row, dict)],
    )


def _validate_transaction_row(
    row: dict[str, Any],
    *,
    index: int,
    existing_transactions: list[dict[str, Any]],
) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []

    action = str(row.get("action") or row.get("type") or row.get("side") or "").strip().upper()
    if action not in SUPPORTED_TRANSACTION_ACTIONS:
        errors.append("action must be BUY or SELL")

    ticker = str(row.get("ticker") or row.get("stock") or row.get("code") or "").strip().upper()
    if not ticker:
        errors.append("ticker is required")

    trade_date = _normalize_date(row.get("date") or row.get("time") or row.get("trade_date"))
    if not trade_date:
        errors.append("date or time is required")

    shares = as_float(row.get("shares") if "shares" in row else row.get("qty") or row.get("quantity"))
    if shares is None or shares <= 0:
        errors.append("shares must be greater than 0")

    price = as_float(row.get("price"))
    if price is None or price <= 0:
        errors.append("price must be greater than 0")

    fee = as_float(row.get("fee"), 0)
    if fee is None or fee < 0:
        errors.append("fee must be greater than or equal to 0")
        fee = None

    tax = as_float(row.get("tax"), 0)
    if tax is None or tax < 0:
        errors.append("tax must be greater than or equal to 0")
        tax = None

    computed_amount: int | None = None
    computed_cash_amount: float | None = None
    amount_difference: float | None = None
    if shares is not None and shares > 0 and price is not None and price > 0:
        computed_amount = trade_consideration_twd(shares, price)
        if fee is not None and tax is not None and action in SUPPORTED_TRANSACTION_ACTIONS:
            computed_cash_amount = computed_amount + fee if action == "BUY" else computed_amount - fee - tax
        source_amount = _source_amount(row)
        if source_amount is not None and abs(source_amount - computed_amount) > 0.0001:
            amount_difference = source_amount - computed_amount
            warnings.append("source amount does not match broker-style truncated consideration")

    duplicate_candidates = _duplicate_candidates(
        existing_transactions,
        action=action,
        ticker=ticker,
        trade_date=trade_date,
        shares=shares,
        price=price,
    )
    if duplicate_candidates:
        warnings.append("possible duplicate transaction")

    normalized = {
        "action": action,
        "ticker": ticker,
        "date": trade_date,
        "time": str(row.get("time") or "").strip(),
        "name": str(row.get("name") or "").strip(),
        "shares": shares,
        "price": price,
        "fee": fee,
        "tax": tax,
        "amount": _source_amount(row),
        "computed_cash_amount": computed_cash_amount,
        "note": str(row.get("note") or "").strip(),
    }
    return {
        "row_id": f"transaction_{index + 1:04d}",
        "kind": "transaction",
        "original": deepcopy(row),
        "normalized": normalized,
        "warnings": warnings,
        "errors": errors,
        "duplicate_candidates": duplicate_candidates,
        "computed_amount": computed_amount,
        "amount_difference": amount_difference,
        "review_status": "error" if errors else ("warning" if warnings else "pending"),
    }


def _unsupported_row(row: dict[str, Any], *, kind: str, index: int) -> dict[str, Any]:
    return {
        "row_id": f"{kind}_{index + 1:04d}",
        "kind": kind,
        "original": deepcopy(row),
        "normalized": {},
        "warnings": [],
        "errors": [f"{kind} rows are not supported by Import Staging v1"],
        "duplicate_candidates": [],
        "computed_amount": None,
        "amount_difference": None,
        "review_status": "error",
    }


def _source_summary(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "source_type": str(payload.get("source_type") or "").strip(),
        "broker": str(payload.get("broker") or "").strip(),
        "account_label": str(payload.get("account_label") or "").strip(),
        "needs_review": bool(payload.get("needs_review", True)),
        "warnings": payload.get("warnings", []) if isinstance(payload.get("warnings"), list) else [],
    }


def _source_amount(row: dict[str, Any]) -> float | None:
    for key in ("consideration", "gross_amount", "amount"):
        if key in row:
            return as_float(row.get(key))
    return None


def _normalize_date(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    candidate = text[:10].replace("/", "-")
    try:
        return datetime.strptime(candidate, "%Y-%m-%d").date().isoformat()
    except ValueError:
        return ""


def _duplicate_candidates(
    transactions: list[dict[str, Any]],
    *,
    action: str,
    ticker: str,
    trade_date: str,
    shares: float | None,
    price: float | None,
) -> list[dict[str, Any]]:
    if not action or not ticker or not trade_date or shares is None or price is None:
        return []
    matches: list[dict[str, Any]] = []
    for transaction in transactions:
        if (
            str(transaction.get("action") or "").strip().upper() == action
            and str(transaction.get("ticker") or "").strip().upper() == ticker
            and _normalize_date(transaction.get("time") or transaction.get("date")) == trade_date
            and round(as_float(transaction.get("shares"), 0) or 0, 4) == round(shares, 4)
            and round(as_float(transaction.get("price"), 0) or 0, 4) == round(price, 4)
        ):
            matches.append(
                {
                    "id": str(transaction.get("id") or ""),
                    "action": action,
                    "ticker": ticker,
                    "date": trade_date,
                    "shares": as_float(transaction.get("shares"), 0),
                    "price": as_float(transaction.get("price"), 0),
                }
            )
    return matches

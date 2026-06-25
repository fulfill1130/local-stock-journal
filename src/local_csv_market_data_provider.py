from __future__ import annotations

import csv
from datetime import date, datetime
from pathlib import Path
from typing import Any

from market_data_types import OhlcvBar, ProviderIssue, ProviderResult, Quote


class LocalCsvMarketDataProvider:
    provider_id = "local_csv"

    def __init__(self, quote_path: Path | None = None, history_path: Path | None = None):
        self.quote_path = Path(quote_path) if quote_path else None
        self.history_path = Path(history_path) if history_path else None

    def supports(self, instrument_id: str, interval: str = "1d") -> bool:
        return bool(str(instrument_id or "").strip()) and interval == "1d"

    def get_quotes(self, instrument_ids: list[str]) -> ProviderResult[Quote]:
        fetched_at = datetime.now().astimezone()
        rows, issues = _read_csv_rows(self.quote_path, "quote")
        by_instrument = {str(row.get("instrument_id") or "").strip(): row for row in rows}
        quotes: list[Quote] = []

        for instrument_id in instrument_ids:
            row = by_instrument.get(str(instrument_id or "").strip())
            if row is None:
                issues.append(_missing_issue("quote_not_found", instrument_id, "No local quote row found."))
                continue
            issue = _row_issue(row, instrument_id)
            quote = Quote(
                instrument_id=instrument_id,
                provider_id=self.provider_id,
                price=_float_or_none(row.get("price")),
                previous_close=_float_or_none(row.get("previous_close")),
                change=_float_or_none(row.get("change")),
                change_pct=_float_or_none(row.get("change_pct")),
                source_timestamp=_parse_datetime(row.get("source_timestamp")),
                fetched_at=fetched_at,
                freshness=str(row.get("freshness") or "manual"),  # type: ignore[arg-type]
                source=str(row.get("source") or "local_csv"),
                currency=str(row.get("currency") or ""),
                issues=(issue,) if issue else (),
            )
            quotes.append(quote)
            if issue:
                issues.append(issue)

        return ProviderResult(
            provider_id=self.provider_id,
            items=tuple(quotes),
            issues=tuple(issues),
            fetched_at=fetched_at,
            source="local_csv",
        )

    def get_daily_bars(self, instrument_id: str, start: date, end: date) -> ProviderResult[OhlcvBar]:
        fetched_at = datetime.now().astimezone()
        rows, issues = _read_csv_rows(self.history_path, "history")
        bars: list[OhlcvBar] = []
        normalized_id = str(instrument_id or "").strip()

        for row in rows:
            if str(row.get("instrument_id") or "").strip() != normalized_id:
                continue
            bar_date = _parse_date(row.get("date"))
            if bar_date is None or bar_date < start or bar_date > end:
                continue
            issue = _row_issue(row, instrument_id)
            bar = OhlcvBar(
                instrument_id=instrument_id,
                provider_id=self.provider_id,
                date=bar_date,
                open=_float_or_none(row.get("open")),
                high=_float_or_none(row.get("high")),
                low=_float_or_none(row.get("low")),
                close=_float_or_none(row.get("close")),
                volume=_int_or_none(row.get("volume")),
                value=_float_or_none(row.get("value")),
                source_timestamp=_parse_datetime(row.get("source_timestamp")),
                fetched_at=fetched_at,
                freshness=str(row.get("freshness") or "end_of_day"),  # type: ignore[arg-type]
                source=str(row.get("source") or "local_csv"),
                adjusted=_bool_value(row.get("adjusted")),
                issues=(issue,) if issue else (),
            )
            bars.append(bar)
            if issue:
                issues.append(issue)

        if not bars:
            issues.append(_missing_issue("history_not_found", instrument_id, "No local history rows found."))

        return ProviderResult(
            provider_id=self.provider_id,
            items=tuple(sorted(bars, key=lambda bar: bar.date)),
            issues=tuple(issues),
            fetched_at=fetched_at,
            source="local_csv",
        )


def _read_csv_rows(path: Path | None, data_kind: str) -> tuple[list[dict[str, str]], list[ProviderIssue]]:
    if path is None:
        return [], [_provider_issue(f"{data_kind}_path_missing", f"No local {data_kind} CSV path configured.")]
    if not path.exists():
        return [], [_provider_issue(f"{data_kind}_file_missing", f"Local {data_kind} CSV file not found: {path}")]
    with path.open("r", encoding="utf-8", newline="") as file:
        return list(csv.DictReader(file)), []


def _missing_issue(code: str, instrument_id: str, message: str) -> ProviderIssue:
    return _provider_issue(code, message, instrument_id=instrument_id, retryable=False)


def _row_issue(row: dict[str, str], instrument_id: str) -> ProviderIssue | None:
    message = str(row.get("issue_message") or "").strip()
    if not message:
        return None
    return _provider_issue(
        str(row.get("issue_code") or "row_issue"),
        message,
        severity="warning",
        retryable=False,
        instrument_id=instrument_id,
    )


def _provider_issue(
    code: str,
    message: str,
    *,
    instrument_id: str = "",
    severity: str = "error",
    retryable: bool = False,
) -> ProviderIssue:
    return ProviderIssue(
        provider_id=LocalCsvMarketDataProvider.provider_id,
        code=code,
        message=message,
        severity=severity,  # type: ignore[arg-type]
        retryable=retryable,
        instrument_id=instrument_id,
        source="local_csv",
        observed_at=datetime.now().astimezone(),
    )


def _parse_datetime(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


def _parse_date(value: Any) -> date | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


def _float_or_none(value: Any) -> float | None:
    text = str(value or "").strip()
    return float(text) if text else None


def _int_or_none(value: Any) -> int | None:
    text = str(value or "").strip()
    return int(float(text)) if text else None


def _bool_value(value: Any) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "y"}

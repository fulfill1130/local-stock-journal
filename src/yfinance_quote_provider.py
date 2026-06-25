from __future__ import annotations

from collections.abc import Callable
from datetime import date, datetime
from typing import Any

import market
from market_data_types import Freshness, ProviderIssue, ProviderResult, Quote


class YFinanceQuoteProvider:
    provider_id = "yfinance"

    def __init__(self, symbol_for_instrument: Callable[[str], str] | None = None):
        self.symbol_for_instrument = symbol_for_instrument or (lambda instrument_id: instrument_id)

    def supports(self, instrument_id: str) -> bool:
        return bool(str(instrument_id or "").strip())

    def get_quotes(self, instrument_ids: list[str]) -> ProviderResult[Quote]:
        quotes: list[Quote] = []
        issues: list[ProviderIssue] = []
        fetched_at: datetime | None = None

        for instrument_id in instrument_ids:
            if not self.supports(instrument_id):
                issues.append(
                    ProviderIssue(
                        provider_id=self.provider_id,
                        code="unsupported_instrument",
                        message="Instrument id is empty.",
                        severity="error",
                        instrument_id=instrument_id,
                    )
                )
                continue

            symbol = self.symbol_for_instrument(instrument_id)
            try:
                raw_quote, _intraday_rows = market.fetch_symbol_bundle(symbol)
            except Exception as exc:
                issues.append(
                    ProviderIssue(
                        provider_id=self.provider_id,
                        code="fetch_failed",
                        message=str(exc),
                        severity="error",
                        retryable=True,
                        instrument_id=instrument_id,
                        source="yfinance",
                        observed_at=datetime.now().astimezone(),
                        details={"symbol": symbol, "exception_type": type(exc).__name__},
                    )
                )
                continue

            quote = quote_from_yfinance_dict(
                instrument_id=instrument_id,
                raw=raw_quote,
                provider_id=self.provider_id,
            )
            quotes.append(quote)
            fetched_at = fetched_at or quote.fetched_at
            issues.extend(quote.issues)

        return ProviderResult(
            provider_id=self.provider_id,
            items=tuple(quotes),
            issues=tuple(issues),
            fetched_at=fetched_at,
            source="yfinance",
        )


def quote_from_yfinance_dict(instrument_id: str, raw: dict[str, Any], provider_id: str = "yfinance") -> Quote:
    source = str(raw.get("source") or "yfinance")
    status = str(raw.get("status") or "").strip().lower()
    error = str(raw.get("error") or "").strip()
    issue = (
        ProviderIssue(
            provider_id=provider_id,
            code=status or "quote_issue",
            message=error,
            severity="error" if status in {"error", "failed"} else "warning",
            retryable=status not in {"manual"},
            instrument_id=instrument_id,
            source=source,
        )
        if error
        else None
    )
    return Quote(
        instrument_id=instrument_id,
        provider_id=provider_id,
        price=_float_or_none(raw.get("close")),
        previous_close=_float_or_none(raw.get("prev_close")),
        change=_float_or_none(raw.get("change")),
        change_pct=_float_or_none(raw.get("change_pct")),
        source_timestamp=_parse_datetime(raw.get("price_time")),
        fetched_at=_parse_fetched_at(raw),
        freshness=_freshness_for_status(status),
        source=source,
        issues=(issue,) if issue else (),
    )


def _freshness_for_status(status: str) -> Freshness:
    if status == "manual":
        return "manual"
    if status in {"stale", "market-closed"}:
        return "stale"
    if status in {"error", "failed"}:
        return "unavailable"
    if status == "ok":
        return "realtime"
    return "unknown"


def _parse_fetched_at(raw: dict[str, Any]) -> datetime | None:
    fetched_at_ts = raw.get("fetched_at_ts")
    if fetched_at_ts not in (None, ""):
        try:
            return datetime.fromtimestamp(float(fetched_at_ts)).astimezone()
        except (TypeError, ValueError, OSError):
            pass
    return _parse_datetime(raw.get("fetched_at"))


def _parse_datetime(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    normalized = text.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(normalized)
    except ValueError:
        pass
    try:
        return datetime.fromisoformat(normalized.replace(" ", "T", 1))
    except ValueError:
        pass
    try:
        return datetime.combine(date.fromisoformat(normalized[:10]), datetime.min.time())
    except ValueError:
        return None


def _float_or_none(value: Any) -> float | None:
    if value in (None, ""):
        return None
    return float(value)

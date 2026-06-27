from __future__ import annotations

import csv
import hashlib
from datetime import datetime
from pathlib import Path
from typing import Any

from market_data_types import ProviderIssue, ProviderResult


class LocalCsvEtfHoldingsProvider:
    provider_id = "local_csv_etf_holdings"
    parser_version = "1"

    def __init__(self, holdings_path: Path):
        self.holdings_path = Path(holdings_path)

    def supports(self, ticker: str) -> bool:
        normalized = _ticker(ticker)
        if not normalized:
            return False
        rows, _issues, _checksum = self._read_raw_rows()
        return any(_ticker(row.get("etf_ticker")) == normalized for row in rows)

    def load(self, ticker: str) -> ProviderResult[dict[str, Any]]:
        fetched_at = datetime.now().astimezone()
        rows, issues, checksum = self._read_raw_rows()
        if issues:
            return ProviderResult(
                provider_id=self.provider_id,
                issues=tuple(issues),
                fetched_at=fetched_at,
                source="local_csv",
            )

        normalized_ticker = _ticker(ticker)
        selected_rows = [row for row in rows if _ticker(row.get("etf_ticker")) == normalized_ticker]
        if not selected_rows:
            return ProviderResult(
                provider_id=self.provider_id,
                issues=(
                    self._issue(
                        "etf_holdings_not_found",
                        "No local ETF holdings rows found for ticker.",
                        instrument_id=normalized_ticker,
                        severity="warning",
                    ),
                ),
                fetched_at=fetched_at,
                source="local_csv",
            )

        parsed = self.parse(selected_rows)
        snapshot = self.normalize(parsed)
        snapshot["fetched_at"] = fetched_at.isoformat()
        snapshot["parser_version"] = self.parser_version
        snapshot["checksum"] = checksum
        validation_issues = self.validate(snapshot)

        return ProviderResult(
            provider_id=self.provider_id,
            items=() if any(issue.severity == "error" for issue in validation_issues) else (snapshot,),
            issues=validation_issues,
            fetched_at=fetched_at,
            source=str(snapshot.get("source") or "local_csv"),
        )

    def parse(self, raw: Any) -> list[dict[str, str]]:
        return [dict(row) for row in (raw or [])]

    def normalize(self, parsed: Any) -> dict[str, Any]:
        rows = [dict(row) for row in (parsed or [])]
        first = rows[0] if rows else {}
        etf_ticker = _ticker(first.get("etf_ticker"))
        as_of_date = str(first.get("as_of_date") or "").strip()[:10]
        source = str(first.get("source") or "local_csv").strip() or "local_csv"
        components = [
            {
                "constituent_ticker": _ticker(row.get("constituent_ticker")),
                "constituent_name": str(row.get("constituent_name") or "").strip(),
                "weight": _float_or_none(row.get("weight")),
                "shares": _float_or_none(row.get("shares")),
                "market_value": _float_or_none(row.get("market_value")),
                "industry": str(row.get("industry") or "").strip(),
                "sort_order": _int_or_none(row.get("sort_order")) or index,
            }
            for index, row in enumerate(rows, 1)
        ]

        return {
            "etf_ticker": etf_ticker,
            "as_of_date": as_of_date,
            "source": source,
            "source_url": str(first.get("source_url") or "").strip(),
            "status": str(first.get("status") or "ok").strip() or "ok",
            "row_count": len(components),
            "notes": str(first.get("notes") or "").strip(),
            "components": components,
            "message": "",
        }

    def validate(self, snapshot: dict[str, Any]) -> tuple[ProviderIssue, ...]:
        issues: list[ProviderIssue] = []
        etf_ticker = _ticker(snapshot.get("etf_ticker"))
        components = list(snapshot.get("components") or [])

        if not etf_ticker:
            issues.append(self._issue("etf_ticker_required", "etf_ticker is required."))
        if not str(snapshot.get("as_of_date") or "").strip():
            issues.append(self._issue("as_of_date_required", "as_of_date is required.", instrument_id=etf_ticker))
        if not str(snapshot.get("source") or "").strip():
            issues.append(self._issue("source_required", "source is required.", instrument_id=etf_ticker))
        if not any(_ticker(row.get("constituent_ticker")) or str(row.get("constituent_name") or "").strip() for row in components):
            issues.append(
                self._issue(
                    "components_required",
                    "At least one component with ticker or name is required.",
                    instrument_id=etf_ticker,
                )
            )

        for index, row in enumerate(components, 1):
            weight = _float_or_none(row.get("weight"))
            if weight is not None and weight < 0:
                issues.append(
                    self._issue(
                        "negative_weight",
                        "ETF holding component weight must not be negative.",
                        instrument_id=etf_ticker,
                        details={"sort_order": row.get("sort_order") or index},
                    )
                )

        return tuple(issues)

    def _read_raw_rows(self) -> tuple[list[dict[str, str]], list[ProviderIssue], str]:
        if not self.holdings_path.exists():
            return [], [self._issue("holdings_file_missing", f"Local ETF holdings CSV file not found: {self.holdings_path}")], ""
        content = self.holdings_path.read_bytes()
        checksum = hashlib.sha256(content).hexdigest()
        text = content.decode("utf-8-sig")
        rows = list(csv.DictReader(text.splitlines()))
        return rows, [], checksum

    def _issue(
        self,
        code: str,
        message: str,
        *,
        instrument_id: str = "",
        severity: str = "error",
        details: dict[str, Any] | None = None,
    ) -> ProviderIssue:
        return ProviderIssue(
            provider_id=self.provider_id,
            code=code,
            message=message,
            severity=severity,  # type: ignore[arg-type]
            retryable=False,
            instrument_id=instrument_id,
            source="local_csv",
            observed_at=datetime.now().astimezone(),
            details=details or {},
        )


def _ticker(value: Any) -> str:
    return str(value or "").strip().upper()


def _float_or_none(value: Any) -> float | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return float(text)
    except (TypeError, ValueError):
        return None


def _int_or_none(value: Any) -> int | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return int(float(text))
    except (TypeError, ValueError):
        return None

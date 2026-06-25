from __future__ import annotations

import sys
import unittest
from datetime import date, datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from market_data_types import OhlcvBar, ProviderIssue, ProviderResult, Quote


class MarketDataTypesTests(unittest.TestCase):
    def test_quote_carries_provider_timestamps_freshness_and_structured_issues(self) -> None:
        fetched_at = datetime(2026, 6, 24, 10, 1, tzinfo=timezone.utc)
        source_timestamp = datetime(2026, 6, 24, 10, 0, tzinfo=timezone.utc)
        issue = ProviderIssue(
            provider_id="example",
            code="stale_cache",
            message="Using cached quote.",
            severity="warning",
            retryable=True,
            instrument_id="TWSE:2330",
            observed_at=fetched_at,
        )
        quote = Quote(
            instrument_id="TWSE:2330",
            provider_id="example",
            price=100.0,
            previous_close=99.0,
            source_timestamp=source_timestamp,
            fetched_at=fetched_at,
            freshness="stale",
            source="EXAMPLE_QUOTE",
            currency="TWD",
            issues=(issue,),
        )

        payload = quote.to_dict()

        self.assertEqual(payload["provider_id"], "example")
        self.assertEqual(payload["source_timestamp"], "2026-06-24T10:00:00+00:00")
        self.assertEqual(payload["fetched_at"], "2026-06-24T10:01:00+00:00")
        self.assertEqual(payload["freshness"], "stale")
        self.assertEqual(payload["issues"][0]["code"], "stale_cache")
        self.assertTrue(payload["issues"][0]["retryable"])

    def test_ohlcv_bar_supports_source_quality_and_adjustment_metadata(self) -> None:
        bar = OhlcvBar(
            instrument_id="TWSE:2330",
            provider_id="twse_official",
            date=date(2026, 6, 24),
            open=100.0,
            high=110.0,
            low=99.0,
            close=108.0,
            volume=12345,
            value=1234500.0,
            fetched_at=datetime(2026, 6, 24, 7, 0, tzinfo=timezone.utc),
            freshness="end_of_day",
            source="TWSE_STOCK_DAY",
            adjusted=False,
        )

        payload = bar.to_dict()

        self.assertEqual(payload["date"], "2026-06-24")
        self.assertEqual(payload["provider_id"], "twse_official")
        self.assertEqual(payload["freshness"], "end_of_day")
        self.assertFalse(payload["adjusted"])

    def test_provider_result_reports_error_status_without_throwing(self) -> None:
        result: ProviderResult[Quote] = ProviderResult(provider_id="example")
        issue = ProviderIssue(
            provider_id="example",
            code="rate_limited",
            message="Provider rate limited the request.",
            severity="error",
            retryable=True,
        )

        failed = result.with_issue(issue)
        payload = failed.to_dict()

        self.assertFalse(failed.ok)
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["issues"][0]["severity"], "error")
        self.assertEqual(payload["issues"][0]["code"], "rate_limited")


if __name__ == "__main__":
    unittest.main()

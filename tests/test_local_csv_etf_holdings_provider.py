from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from central_store import get_etf_holding_snapshot, upsert_etf_holding_snapshot  # noqa: E402
from local_csv_etf_holdings_provider import LocalCsvEtfHoldingsProvider  # noqa: E402
from server import etf_holdings_payload  # noqa: E402


class LocalCsvEtfHoldingsProviderTests(unittest.TestCase):
    def test_loads_synthetic_sample_holdings_for_demoa(self) -> None:
        provider = LocalCsvEtfHoldingsProvider(ROOT / "sample_data" / "market" / "etf_holdings.csv")

        result = provider.load("DEMOA")

        self.assertTrue(result.ok)
        self.assertEqual(len(result.items), 1)
        snapshot = result.items[0]
        self.assertEqual(snapshot["etf_ticker"], "DEMOA")
        self.assertEqual(snapshot["as_of_date"], "2026-04-16")
        self.assertEqual(snapshot["source"], "synthetic_demo")
        self.assertEqual(snapshot["status"], "ok")
        self.assertEqual(snapshot["row_count"], 4)
        self.assertEqual(snapshot["parser_version"], "1")
        self.assertEqual(len(snapshot["checksum"]), 64)
        self.assertEqual([row["constituent_ticker"] for row in snapshot["components"]], ["DEMOX", "DEMOY", "DEMOZ", "DEMOCASH"])
        self.assertEqual(snapshot["components"][0]["weight"], 35.5)
        self.assertEqual(snapshot["components"][0]["shares"], 120000)
        self.assertEqual(snapshot["components"][0]["market_value"], 4260000)

    def test_supports_demoa_and_unknown_ticker_returns_no_rows_safely(self) -> None:
        provider = LocalCsvEtfHoldingsProvider(ROOT / "sample_data" / "market" / "etf_holdings.csv")

        missing = provider.load("NOHOLD")

        self.assertTrue(provider.supports("DEMOA"))
        self.assertFalse(provider.supports("NOHOLD"))
        self.assertTrue(missing.ok)
        self.assertEqual(missing.items, ())
        self.assertEqual(missing.issues[0].code, "etf_holdings_not_found")
        self.assertEqual(missing.issues[0].severity, "warning")

    def test_normalized_output_matches_snapshot_and_component_schema(self) -> None:
        provider = LocalCsvEtfHoldingsProvider(ROOT / "sample_data" / "market" / "etf_holdings.csv")
        snapshot = provider.load("DEMOA").items[0]

        self.assertEqual(
            set(snapshot),
            {
                "etf_ticker",
                "as_of_date",
                "source",
                "source_url",
                "status",
                "row_count",
                "notes",
                "components",
                "message",
                "fetched_at",
                "parser_version",
                "checksum",
            },
        )
        self.assertEqual(
            set(snapshot["components"][0]),
            {
                "constituent_ticker",
                "constituent_name",
                "weight",
                "shares",
                "market_value",
                "industry",
                "sort_order",
            },
        )

    def test_validation_catches_empty_components(self) -> None:
        provider = LocalCsvEtfHoldingsProvider(ROOT / "sample_data" / "market" / "etf_holdings.csv")

        issues = provider.validate(
            {
                "etf_ticker": "DEMOA",
                "as_of_date": "2026-04-16",
                "source": "unit_test",
                "components": [],
            }
        )

        self.assertEqual([issue.code for issue in issues], ["components_required"])

    def test_validation_catches_negative_weights(self) -> None:
        provider = LocalCsvEtfHoldingsProvider(ROOT / "sample_data" / "market" / "etf_holdings.csv")

        issues = provider.validate(
            {
                "etf_ticker": "DEMOA",
                "as_of_date": "2026-04-16",
                "source": "unit_test",
                "components": [{"constituent_ticker": "BAD", "weight": -1, "sort_order": 1}],
            }
        )

        self.assertEqual([issue.code for issue in issues], ["negative_weight"])

    def test_provider_does_not_write_database_directly(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            provider = LocalCsvEtfHoldingsProvider(ROOT / "sample_data" / "market" / "etf_holdings.csv")

            result = provider.load("DEMOA")

            self.assertTrue(result.ok)
            self.assertEqual(list(temp_root.rglob("*.sqlite")), [])

    def test_normalized_output_can_persist_through_existing_helper_and_api_payload(self) -> None:
        provider = LocalCsvEtfHoldingsProvider(ROOT / "sample_data" / "market" / "etf_holdings.csv")
        snapshot = provider.load("DEMOA").items[0]

        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp_dir:
            market_root = Path(temp_dir) / "market_data"
            upsert_etf_holding_snapshot(
                market_root,
                etf_ticker=snapshot["etf_ticker"],
                as_of_date=snapshot["as_of_date"],
                source=snapshot["source"],
                source_url=snapshot["source_url"],
                status=snapshot["status"],
                notes=snapshot["notes"],
                rows=snapshot["components"],
            )

            helper_result = get_etf_holding_snapshot(market_root, "DEMOA", "2026-04-16")
            api_payload = etf_holdings_payload(market_root, "DEMOA")

        self.assertIsNotNone(helper_result)
        self.assertEqual(helper_result["snapshot"]["row_count"], 4)
        self.assertEqual(helper_result["components"][0]["constituent_ticker"], "DEMOX")
        self.assertTrue(api_payload["ok"])
        self.assertEqual(api_payload["summary"]["component_count"], 4)
        self.assertEqual(api_payload["summary"]["weight_total"], 100)


if __name__ == "__main__":
    unittest.main()

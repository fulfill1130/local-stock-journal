from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from http_etf_holdings_provider import ConfiguredHttpEtfHoldingsProvider  # noqa: E402


class ConfiguredHttpEtfHoldingsProviderTests(unittest.TestCase):
    def test_loads_fake_csv_http_response_and_normalizes(self) -> None:
        provider = ConfiguredHttpEtfHoldingsProvider(
            provider_id="fake_live",
            endpoint_url="https://provider.invalid/{ticker}.csv",
            tickers=("DEMOA",),
            source="fake_live_source",
            public_source_url="https://provider.example/holdings",
            fetcher=lambda _url, _headers, _timeout: _valid_csv(),
        )

        result = provider.load("DEMOA")

        self.assertTrue(result.ok)
        snapshot = result.items[0]
        self.assertEqual(snapshot["etf_ticker"], "DEMOA")
        self.assertEqual(snapshot["as_of_date"], "2026-04-16")
        self.assertEqual(snapshot["source"], "fake_live_source")
        self.assertEqual(snapshot["source_url"], "https://provider.example/holdings")
        self.assertEqual(snapshot["parser_version"], "1")
        self.assertEqual(len(snapshot["checksum"]), 64)
        self.assertEqual([row["constituent_ticker"] for row in snapshot["components"]], ["DEMOX", "DEMOY"])

    def test_loads_simple_json_response(self) -> None:
        provider = ConfiguredHttpEtfHoldingsProvider(
            provider_id="fake_json",
            endpoint_url="https://provider.invalid/{ticker}.json",
            response_format="json",
            fetcher=lambda _url, _headers, _timeout: (
                '{"etf_ticker":"DEMOA","as_of_date":"2026-04-16","components":'
                '[{"constituent_ticker":"DEMOX","constituent_name":"Demo X","weight":60}]}'
            ),
        )

        result = provider.load("DEMOA")

        self.assertTrue(result.ok)
        self.assertEqual(result.items[0]["components"][0]["constituent_ticker"], "DEMOX")

    def test_validates_required_fields(self) -> None:
        provider = ConfiguredHttpEtfHoldingsProvider(
            provider_id="fake_live",
            endpoint_url="https://provider.invalid/{ticker}.csv",
        )

        issues = provider.validate({"components": []})

        codes = {issue.code for issue in issues}
        self.assertIn("etf_ticker_required", codes)
        self.assertIn("as_of_date_required", codes)
        self.assertIn("components_required", codes)

    def test_rejects_negative_weights(self) -> None:
        provider = ConfiguredHttpEtfHoldingsProvider(
            provider_id="fake_live",
            endpoint_url="https://provider.invalid/{ticker}.csv",
            fetcher=lambda _url, _headers, _timeout: (
                "etf_ticker,as_of_date,constituent_ticker,weight\nDEMOA,2026-04-16,BAD,-1\n"
            ),
        )

        result = provider.load("DEMOA")

        self.assertFalse(result.ok)
        self.assertEqual([issue.code for issue in result.issues], ["negative_weight"])


def _valid_csv() -> str:
    return "\n".join(
        [
            "etf_ticker,as_of_date,constituent_ticker,constituent_name,weight,shares,market_value,industry,sort_order",
            "DEMOA,2026-04-16,DEMOX,Demo Component X,60,1000,60000,Demo Tech,1",
            "DEMOA,2026-04-16,DEMOY,Demo Component Y,40,800,40000,Demo Finance,2",
        ]
    )


if __name__ == "__main__":
    unittest.main()

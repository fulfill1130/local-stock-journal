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
from fubon_etf_holdings_provider import FubonEtfHoldingsProvider  # noqa: E402
from server import etf_holdings_payload  # noqa: E402


class FubonEtfHoldingsProviderTests(unittest.TestCase):
    def test_parse_fubon_like_fixture_with_date_and_stock_rows(self) -> None:
        provider = FubonEtfHoldingsProvider(fetcher=lambda _url, _timeout: _fubon_fixture())

        parsed = provider.parse(_fubon_fixture())

        self.assertEqual(parsed["as_of_date"], "2026-06-26")
        self.assertEqual(len(parsed["stock_rows"]), 2)
        self.assertEqual(parsed["stock_rows"][0]["constituent_ticker"], "2303")
        self.assertEqual(parsed["stock_rows"][0]["constituent_name"], "聯電")
        self.assertEqual(parsed["stock_rows"][0]["shares"], "19,558,000")
        self.assertEqual(parsed["stock_rows"][0]["market_value"], "3,207,512,000")
        self.assertEqual(parsed["stock_rows"][0]["weight"], "10.1825")
        self.assertEqual(parsed["stock_total_weight"], 19.3219)
        self.assertEqual(parsed["non_stock_row_count"], 3)

    def test_normalizes_rows_to_snapshot_shape(self) -> None:
        provider = FubonEtfHoldingsProvider(fetcher=lambda _url, _timeout: _fubon_fixture())

        result = provider.load("00900")

        self.assertTrue(result.ok)
        snapshot = result.items[0]
        self.assertEqual(snapshot["etf_ticker"], "00900")
        self.assertEqual(snapshot["as_of_date"], "2026-06-26")
        self.assertEqual(snapshot["source"], "fubon_assets_html")
        self.assertEqual(snapshot["status"], "ok")
        self.assertEqual(snapshot["row_count"], 2)
        self.assertEqual(snapshot["parser_version"], "1")
        self.assertEqual(len(snapshot["checksum"]), 64)
        self.assertIn("Non-stock asset rows", snapshot["notes"])
        self.assertEqual(snapshot["components"][0]["constituent_ticker"], "2303")
        self.assertEqual(snapshot["components"][0]["constituent_name"], "聯電")
        self.assertEqual(snapshot["components"][0]["shares"], 19558000)
        self.assertEqual(snapshot["components"][0]["market_value"], 3207512000)
        self.assertEqual(snapshot["components"][0]["weight"], 10.1825)
        self.assertEqual(snapshot["components"][0]["sort_order"], 1)

    def test_rejects_missing_date(self) -> None:
        provider = FubonEtfHoldingsProvider(fetcher=lambda _url, _timeout: _fubon_fixture(include_date=False))

        result = provider.load("00900")

        self.assertFalse(result.ok)
        self.assertIn("as_of_date_required", {issue.code for issue in result.issues})

    def test_rejects_missing_components(self) -> None:
        provider = FubonEtfHoldingsProvider(fetcher=lambda _url, _timeout: _fubon_fixture(include_stock_rows=False))

        result = provider.load("00900")

        self.assertFalse(result.ok)
        self.assertIn("components_required", {issue.code for issue in result.issues})

    def test_rejects_negative_weights(self) -> None:
        provider = FubonEtfHoldingsProvider(fetcher=lambda _url, _timeout: _fubon_fixture(weight="-1.25"))

        result = provider.load("00900")

        self.assertFalse(result.ok)
        self.assertEqual([issue.code for issue in result.issues], ["negative_weight"])

    def test_provider_does_not_write_database_directly(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            provider = FubonEtfHoldingsProvider(fetcher=lambda _url, _timeout: _fubon_fixture())

            result = provider.load("00900")

            self.assertTrue(result.ok)
            self.assertEqual(list(temp_root.rglob("*.sqlite")), [])

    def test_output_can_persist_through_existing_helper_and_api_payload(self) -> None:
        provider = FubonEtfHoldingsProvider(fetcher=lambda _url, _timeout: _fubon_fixture())
        snapshot = provider.load("00900").items[0]

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

            helper_result = get_etf_holding_snapshot(market_root, "00900", "2026-06-26")
            api_payload = etf_holdings_payload(market_root, "00900")

        self.assertIsNotNone(helper_result)
        self.assertEqual(helper_result["snapshot"]["row_count"], 2)
        self.assertEqual(helper_result["components"][0]["constituent_ticker"], "2303")
        self.assertTrue(api_payload["ok"])
        self.assertEqual(api_payload["summary"]["component_count"], 2)


def _fubon_fixture(*, include_date: bool = True, include_stock_rows: bool = True, weight: str = "10.1825") -> str:
    date_html = "<div>資料日期：2026/06/26</div>" if include_date else ""
    stock_rows = ""
    if include_stock_rows:
        stock_rows = f"""
          <tr><td>2303</td><td>聯電</td><td>19,558,000</td><td>3,207,512,000</td><td>{weight}</td></tr>
          <tr><td>2454</td><td>聯發科</td><td>742,000</td><td>2,878,960,000</td><td>9.1394</td></tr>
          <tr><td>股票合計</td><td></td><td></td><td>6,086,472,000</td><td>19.3219</td></tr>
        """
    return f"""
    <html>
      <body>
        <h1>00900 富邦特選高股息30</h1>
        {date_html}
        <table>
          <tr><th>期貨代碼</th><th>期貨名稱</th><th>口數</th><th>金額</th><th>權重(%)</th></tr>
          <tr><td>WTXN6F</td><td>台股指數期貨</td><td>58</td><td>515,643,200</td><td>1.6369</td></tr>
          <tr><td>期貨合計</td><td></td><td></td><td>515,643,200</td><td>1.6369</td></tr>
        </table>
        <table>
          <tr><th>股票代碼</th><th>股票名稱</th><th>股數</th><th>金額</th><th>權重(%)</th></tr>
          {stock_rows}
        </table>
        <table>
          <tr><th>項目</th><th>金額</th></tr>
          <tr><td>現金 (TWD)</td><td>141,734,871</td></tr>
        </table>
      </body>
    </html>
    """


if __name__ == "__main__":
    unittest.main()

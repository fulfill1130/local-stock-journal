from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from central_store import get_etf_holding_snapshot, upsert_etf_holding_snapshot  # noqa: E402
from server import etf_holdings_payload  # noqa: E402
from yuanta_etf_holdings_provider import YuantaEtfHoldingsProvider  # noqa: E402


class YuantaEtfHoldingsProviderTests(unittest.TestCase):
    def test_parse_yuanta_like_fixture_with_date_and_rows(self) -> None:
        provider = YuantaEtfHoldingsProvider(fetcher=lambda _url, _timeout: _yuanta_fixture())

        parsed = provider.parse(_yuanta_fixture())

        self.assertEqual(parsed["as_of_date"], "2026-06-26")
        self.assertEqual(len(parsed["rows"]), 2)
        self.assertEqual(parsed["rows"][0]["constituent_ticker"], "2330")
        self.assertEqual(parsed["rows"][0]["constituent_name"], "台積電")
        self.assertEqual(parsed["rows"][0]["shares"], "520,512,559")
        self.assertEqual(parsed["rows"][0]["weight"], "57.72")

    def test_normalizes_0050_like_rows_to_snapshot_shape(self) -> None:
        provider = YuantaEtfHoldingsProvider(fetcher=lambda _url, _timeout: _yuanta_fixture())

        result = provider.load("0050")

        self.assertTrue(result.ok)
        snapshot = result.items[0]
        self.assertEqual(snapshot["etf_ticker"], "0050")
        self.assertEqual(snapshot["as_of_date"], "2026-06-26")
        self.assertEqual(snapshot["source"], "yuanta_etfs_html")
        self.assertEqual(snapshot["status"], "ok")
        self.assertEqual(snapshot["row_count"], 2)
        self.assertEqual(snapshot["parser_version"], "1")
        self.assertEqual(len(snapshot["checksum"]), 64)
        self.assertEqual(snapshot["components"][0]["constituent_ticker"], "2330")
        self.assertEqual(snapshot["components"][0]["constituent_name"], "台積電")
        self.assertEqual(snapshot["components"][0]["shares"], 520512559)
        self.assertEqual(snapshot["components"][0]["weight"], 57.72)
        self.assertIsNone(snapshot["components"][0]["market_value"])
        self.assertEqual(snapshot["components"][0]["industry"], "")

    def test_rejects_missing_date(self) -> None:
        provider = YuantaEtfHoldingsProvider(fetcher=lambda _url, _timeout: _yuanta_fixture(include_date=False))

        result = provider.load("0050")

        self.assertFalse(result.ok)
        self.assertIn("as_of_date_required", {issue.code for issue in result.issues})

    def test_rejects_missing_components(self) -> None:
        provider = YuantaEtfHoldingsProvider(fetcher=lambda _url, _timeout: _yuanta_fixture(include_rows=False))

        result = provider.load("0050")

        self.assertFalse(result.ok)
        self.assertIn("components_required", {issue.code for issue in result.issues})

    def test_rejects_negative_weights(self) -> None:
        provider = YuantaEtfHoldingsProvider(fetcher=lambda _url, _timeout: _yuanta_fixture(weight="-1.25"))

        result = provider.load("0050")

        self.assertFalse(result.ok)
        self.assertEqual([issue.code for issue in result.issues], ["negative_weight"])

    def test_provider_does_not_write_database_directly(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            provider = YuantaEtfHoldingsProvider(fetcher=lambda _url, _timeout: _yuanta_fixture())

            result = provider.load("0050")

            self.assertTrue(result.ok)
            self.assertEqual(list(temp_root.rglob("*.sqlite")), [])

    def test_output_can_persist_through_existing_helper_and_api_payload(self) -> None:
        provider = YuantaEtfHoldingsProvider(fetcher=lambda _url, _timeout: _yuanta_fixture())
        snapshot = provider.load("0050").items[0]

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

            helper_result = get_etf_holding_snapshot(market_root, "0050", "2026-06-26")
            api_payload = etf_holdings_payload(market_root, "0050")

        self.assertIsNotNone(helper_result)
        self.assertEqual(helper_result["snapshot"]["row_count"], 2)
        self.assertEqual(helper_result["components"][0]["constituent_ticker"], "2330")
        self.assertTrue(api_payload["ok"])
        self.assertEqual(api_payload["summary"]["component_count"], 2)

    def test_default_fetch_uses_tls_context_without_network_fixture(self) -> None:
        provider = YuantaEtfHoldingsProvider()
        with patch("yuanta_etf_holdings_provider.urlopen", return_value=_FakeResponse(_yuanta_fixture())) as mocked:
            raw = provider.fetch("0056")

        self.assertIn("2026/06/26", raw)
        self.assertIn("context", mocked.call_args.kwargs)
        context = mocked.call_args.kwargs["context"]
        self.assertTrue(context.check_hostname)
        self.assertEqual(context.verify_mode, 2)


def _yuanta_fixture(*, include_date: bool = True, include_rows: bool = True, weight: str = "57.72") -> str:
    date_html = '<div class="trandate">交易日期: <br>2026/06/26</div>' if include_date else ""
    rows_html = ""
    if include_rows:
        rows_html = f"""
        <div class="tbody">
          <div class="tr">
            <div class="td"><span class="d-md-none">商品代碼</span> <span>2330</span></div>
            <div class="td"><span class="d-md-none">商品名稱</span> <span>台積電</span></div>
            <div class="td"><span class="d-md-none">商品數量</span> <span>520,512,559</span></div>
            <div class="td"><span class="d-md-none">商品權重</span> <span>{weight}</span></div>
          </div>
          <div class="tr">
            <div class="td"><span class="d-md-none">商品代碼</span> <span>2317</span></div>
            <div class="td"><span class="d-md-none">商品名稱</span> <span>鴻海</span></div>
            <div class="td"><span class="d-md-none">商品數量</span> <span>1000</span></div>
            <div class="td"><span class="d-md-none">商品權重</span> <span>3.50</span></div>
          </div>
        </div>
        """
    return f"""
    <html>
      <body>
        <h3>詳細基金成分</h3>
        <section>
          <h3>基金權重-股票</h3>
          {date_html}
          <div class="thead">
            <div class="tr">
              <div class="td">商品代碼</div><div class="td">商品名稱</div>
              <div class="td">商品數量</div><div class="td">商品權重</div>
            </div>
          </div>
          {rows_html}
        </section>
      </body>
    </html>
    """


class _FakeResponse:
    def __init__(self, text: str):
        self.text = text

    def __enter__(self) -> "_FakeResponse":
        return self

    def __exit__(self, _exc_type: object, _exc: object, _traceback: object) -> None:
        return None

    def read(self) -> bytes:
        return self.text.encode("utf-8")


if __name__ == "__main__":
    unittest.main()

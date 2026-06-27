from __future__ import annotations

import gc
import json
import sqlite3
import sys
import tempfile
import unittest
import warnings
from pathlib import Path
from unittest.mock import patch
from urllib.error import URLError


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from central_store import get_etf_holding_snapshot, upsert_etf_holding_snapshot  # noqa: E402
from server import create_app  # noqa: E402


class EtfHoldingsProviderApiTests(unittest.TestCase):
    def setUp(self) -> None:
        warnings.filterwarnings("ignore", category=ResourceWarning)
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.project_root = Path(self.tmp.name)
        self.app = create_app(self.project_root)
        self.client = self.app.test_client()
        self.market_root = self.project_root / "data" / "market_data"

    def tearDown(self) -> None:
        self.client = None
        self.app = None
        gc.collect()
        self.tmp.cleanup()

    def test_preview_endpoint_fetches_provider_and_does_not_write(self) -> None:
        self._write_provider_config()
        with patch("http_etf_holdings_provider.urlopen", return_value=_FakeResponse(_valid_csv())):
            response = self.client.post(
                "/api/database/etf-holdings/fetch-provider",
                json={"ticker": "DEMOA", "provider_id": "fake_live", "confirm": False},
            )

        payload = response.get_json()
        self.assertEqual(response.status_code, 200)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["mode"], "preview")
        self.assertFalse(payload["imported"])
        self.assertEqual(payload["provider"]["provider_id"], "fake_live")
        self.assertEqual(payload["summary"]["component_count"], 2)
        self.assertEqual(_snapshot_count(self.market_root), 0)

    def test_provider_list_returns_safe_empty_response_when_config_missing(self) -> None:
        response = self.client.get("/api/database/etf-holdings/providers?ticker=DEMOA")

        payload = response.get_json()
        self.assertEqual(response.status_code, 200)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["providers"], [])
        self.assertIn("CSV", payload["message"])

    def test_provider_list_returns_only_safe_metadata_from_local_config(self) -> None:
        self._write_provider_config(url="https://private.example.invalid/secret/{ticker}?token=SECRET_URL_TOKEN")
        with patch.dict("os.environ", {"ETF_TEST_SECRET": "SECRET_HEADER_TOKEN"}):
            response = self.client.get("/api/database/etf-holdings/providers?ticker=DEMOA")

        payload = response.get_json()
        response_text = response.get_data(as_text=True)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(payload["ok"])
        self.assertEqual(len(payload["providers"]), 1)
        self.assertEqual(payload["providers"][0]["provider_id"], "fake_live")
        self.assertEqual(payload["providers"][0]["display_name"], "Fake ETF source")
        self.assertEqual(payload["providers"][0]["type"], "http")
        self.assertEqual(payload["providers"][0]["status"], "available")
        self.assertEqual(payload["providers"][0]["ticker_match"]["tickers"], ["DEMOA"])
        self.assertNotIn("url", payload["providers"][0])
        self.assertNotIn("headers", payload["providers"][0])
        self.assertNotIn("cache", response_text.lower())
        self.assertNotIn("SECRET_URL_TOKEN", response_text)
        self.assertNotIn("SECRET_HEADER_TOKEN", response_text)
        self.assertNotIn("private.example.invalid", response_text)

    def test_provider_list_filters_by_ticker_support(self) -> None:
        self._write_two_provider_config()

        supported = self.client.get("/api/database/etf-holdings/providers?ticker=0050").get_json()
        unsupported = self.client.get("/api/database/etf-holdings/providers?ticker=00919").get_json()

        self.assertEqual([row["provider_id"] for row in supported["providers"]], ["yuanta_test"])
        self.assertEqual(unsupported["providers"], [])
        self.assertIn("CSV", unsupported["message"])

    def test_fetch_provider_with_unsupported_provider_id_remains_friendly(self) -> None:
        self._write_provider_config()
        response = self.client.post(
            "/api/database/etf-holdings/fetch-provider",
            json={"ticker": "OTHER", "provider_id": "fake_live", "confirm": False},
        )

        payload = response.get_json()
        self.assertEqual(response.status_code, 400)
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["errors"][0]["code"], "provider_unsupported_ticker")

    def test_confirm_endpoint_writes_valid_provider_snapshot(self) -> None:
        self._write_provider_config()
        with patch("http_etf_holdings_provider.urlopen", return_value=_FakeResponse(_valid_csv())):
            response = self.client.post(
                "/api/database/etf-holdings/fetch-provider",
                json={"ticker": "DEMOA", "confirm": True},
            )

        payload = response.get_json()
        self.assertEqual(response.status_code, 200)
        self.assertTrue(payload["imported"])
        self.assertEqual(payload["snapshot"]["source"], "fake_live_source")

        read_payload = self.client.get("/api/database/DEMOA/etf-holdings").get_json()
        self.assertTrue(read_payload["ok"])
        self.assertEqual(read_payload["snapshot"]["as_of_date"], "2026-04-16")
        self.assertEqual([row["constituent_ticker"] for row in read_payload["components"]], ["DEMOX", "DEMOY"])

    def test_older_provider_snapshot_rejected_unless_override_true(self) -> None:
        self._write_provider_config()
        upsert_etf_holding_snapshot(
            self.market_root,
            etf_ticker="DEMOA",
            as_of_date="2026-05-01",
            source="unit_test",
            rows=[{"constituent_ticker": "NEW", "constituent_name": "New", "weight": 100}],
        )

        with patch("http_etf_holdings_provider.urlopen", return_value=_FakeResponse(_valid_csv())):
            rejected = self.client.post(
                "/api/database/etf-holdings/fetch-provider",
                json={"ticker": "DEMOA", "confirm": True},
            )
        self.assertEqual(rejected.status_code, 409)
        self.assertEqual(rejected.get_json()["errors"][0]["code"], "older_snapshot_exists")
        self.assertEqual(get_etf_holding_snapshot(self.market_root, "DEMOA")["snapshot"]["as_of_date"], "2026-05-01")

        with patch("http_etf_holdings_provider.urlopen", return_value=_FakeResponse(_valid_csv())):
            imported = self.client.post(
                "/api/database/etf-holdings/fetch-provider",
                json={"ticker": "DEMOA", "confirm": True, "override": True},
            )
        self.assertEqual(imported.status_code, 200)
        self.assertEqual(get_etf_holding_snapshot(self.market_root, "DEMOA")["snapshot"]["as_of_date"], "2026-05-01")
        self.assertIsNotNone(get_etf_holding_snapshot(self.market_root, "DEMOA", "2026-04-16"))

    def test_failed_provider_fetch_does_not_overwrite_latest_good_snapshot(self) -> None:
        self._write_provider_config()
        upsert_etf_holding_snapshot(
            self.market_root,
            etf_ticker="DEMOA",
            as_of_date="2026-05-01",
            source="unit_test",
            rows=[{"constituent_ticker": "NEW", "constituent_name": "New", "weight": 100}],
        )

        with patch("http_etf_holdings_provider.urlopen", side_effect=URLError("PRIVATE_URL_SHOULD_NOT_LEAK")):
            response = self.client.post(
                "/api/database/etf-holdings/fetch-provider",
                json={"ticker": "DEMOA", "confirm": True},
            )

        response_text = response.get_data(as_text=True)
        self.assertEqual(response.status_code, 400)
        self.assertIn("provider_fetch_failed", {issue["code"] for issue in response.get_json()["errors"]})
        self.assertNotIn("PRIVATE_URL_SHOULD_NOT_LEAK", response_text)
        current = get_etf_holding_snapshot(self.market_root, "DEMOA")
        self.assertEqual(current["snapshot"]["as_of_date"], "2026-05-01")
        self.assertEqual(current["components"][0]["constituent_ticker"], "NEW")

    def test_no_secrets_private_config_or_raw_response_are_returned(self) -> None:
        self._write_provider_config(url="https://private.example.invalid/secret/{ticker}?token=SECRET_URL_TOKEN")
        with patch.dict("os.environ", {"ETF_TEST_SECRET": "SECRET_HEADER_TOKEN"}):
            with patch("http_etf_holdings_provider.urlopen", return_value=_FakeResponse("PRIVATE_RAW_RESPONSE_MARKER")):
                response_text = self.client.post(
                    "/api/database/etf-holdings/fetch-provider",
                    json={"ticker": "DEMOA", "confirm": False},
                ).get_data(as_text=True)

        self.assertNotIn("SECRET_URL_TOKEN", response_text)
        self.assertNotIn("SECRET_HEADER_TOKEN", response_text)
        self.assertNotIn("PRIVATE_RAW_RESPONSE_MARKER", response_text)
        self.assertNotIn("private.example.invalid", response_text)

    def test_missing_provider_config_returns_friendly_error(self) -> None:
        response = self.client.post(
            "/api/database/etf-holdings/fetch-provider",
            json={"ticker": "DEMOA", "confirm": False},
        )

        payload = response.get_json()
        self.assertEqual(response.status_code, 400)
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["errors"][0]["code"], "provider_config_missing")
        self.assertEqual(_snapshot_count(self.market_root), 0)

    def test_yuanta_provider_config_previews_without_writing(self) -> None:
        self._write_yuanta_provider_config()
        with patch("yuanta_etf_holdings_provider.urlopen", return_value=_FakeResponse(_yuanta_fixture())):
            response = self.client.post(
                "/api/database/etf-holdings/fetch-provider",
                json={"ticker": "0050", "provider_id": "yuanta_test", "confirm": False},
            )

        payload = response.get_json()
        self.assertEqual(response.status_code, 200)
        self.assertTrue(payload["ok"])
        self.assertFalse(payload["imported"])
        self.assertEqual(payload["provider"]["provider_id"], "yuanta_test")
        self.assertEqual(payload["snapshot"]["as_of_date"], "2026-06-26")
        self.assertEqual(payload["components"][0]["constituent_ticker"], "2330")
        self.assertEqual(_snapshot_count(self.market_root), 0)

    def test_fubon_provider_config_previews_without_writing(self) -> None:
        self._write_fubon_provider_config()
        with patch("fubon_etf_holdings_provider.urlopen", return_value=_FakeResponse(_fubon_fixture())):
            response = self.client.post(
                "/api/database/etf-holdings/fetch-provider",
                json={"ticker": "00900", "provider_id": "fubon_test", "confirm": False},
            )

        payload = response.get_json()
        self.assertEqual(response.status_code, 200)
        self.assertTrue(payload["ok"])
        self.assertFalse(payload["imported"])
        self.assertEqual(payload["provider"]["provider_id"], "fubon_test")
        self.assertEqual(payload["snapshot"]["as_of_date"], "2026-06-26")
        self.assertEqual(payload["snapshot"]["source"], "fubon_assets_html")
        self.assertEqual(payload["components"][0]["constituent_ticker"], "2303")
        self.assertEqual(payload["components"][0]["shares"], 19558000)
        self.assertEqual(payload["components"][0]["market_value"], 3207512000)
        self.assertEqual(_snapshot_count(self.market_root), 0)

    def test_fubon_provider_list_returns_safe_metadata_without_url_leak(self) -> None:
        self._write_fubon_provider_config(
            url_template="https://private.example.invalid/fubon/{ticker}?token=SECRET_URL_TOKEN"
        )

        response = self.client.get("/api/database/etf-holdings/providers?ticker=00900")
        response_text = response.get_data(as_text=True)
        payload = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(payload["providers"]), 1)
        self.assertEqual(payload["providers"][0]["provider_id"], "fubon_test")
        self.assertEqual(payload["providers"][0]["display_name"], "Fubon 00900")
        self.assertEqual(payload["providers"][0]["issuer"], "Fubon")
        self.assertEqual(payload["providers"][0]["type"], "fubon")
        self.assertEqual(payload["providers"][0]["status"], "available")
        self.assertNotIn("url", payload["providers"][0])
        self.assertNotIn("SECRET_URL_TOKEN", response_text)
        self.assertNotIn("private.example.invalid", response_text)

    def _write_provider_config(self, *, url: str = "https://provider.invalid/{ticker}.csv") -> None:
        config_path = self.project_root / "config" / "providers.local.json"
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(
            json.dumps(
                {
                    "etf_holdings": {
                        "providers": [
                            {
                                "provider_id": "fake_live",
                                "display_name": "Fake ETF source",
                                "issuer": "Synthetic Issuer",
                                "type": "http",
                                "url": url,
                                "format": "csv",
                                "tickers": ["DEMOA"],
                                "source": "fake_live_source",
                                "public_source_url": "https://provider.example/holdings",
                                "api_key_env": "ETF_TEST_SECRET",
                            }
                        ]
                    }
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

    def _write_two_provider_config(self) -> None:
        config_path = self.project_root / "config" / "providers.local.json"
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(
            json.dumps(
                {
                    "etf_holdings": {
                        "providers": [
                            {
                                "provider_id": "fake_live",
                                "display_name": "Fake ETF source",
                                "type": "http",
                                "url": "https://private.example.invalid/{ticker}.csv",
                                "format": "csv",
                                "tickers": ["DEMOA"],
                                "source": "fake_live_source",
                            },
                            {
                                "provider_id": "yuanta_test",
                                "display_name": "Yuanta 0050",
                                "issuer": "Yuanta",
                                "type": "yuanta",
                                "tickers": ["0050"],
                            },
                        ]
                    }
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

    def _write_yuanta_provider_config(self) -> None:
        config_path = self.project_root / "config" / "providers.local.json"
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(
            json.dumps(
                {
                    "etf_holdings": {
                        "providers": [
                            {
                                "provider_id": "yuanta_test",
                                "type": "yuanta",
                                "tickers": ["0050"],
                            }
                        ]
                    }
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

    def _write_fubon_provider_config(
        self,
        *,
        url_template: str = "https://provider.invalid/fubon/{ticker}",
    ) -> None:
        config_path = self.project_root / "config" / "providers.local.json"
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(
            json.dumps(
                {
                    "etf_holdings": {
                        "providers": [
                            {
                                "provider_id": "fubon_test",
                                "display_name": "Fubon 00900",
                                "issuer": "Fubon",
                                "type": "fubon",
                                "tickers": ["00900"],
                                "url_template": url_template,
                            }
                        ]
                    }
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )


class _FakeResponse:
    def __init__(self, text: str):
        self.text = text
        self.headers = _FakeHeaders()

    def __enter__(self) -> _FakeResponse:
        return self

    def __exit__(self, _exc_type: object, _exc: object, _traceback: object) -> None:
        return None

    def read(self) -> bytes:
        return self.text.encode("utf-8")


class _FakeHeaders:
    def get_content_charset(self) -> str:
        return "utf-8"


def _valid_csv() -> str:
    return "\n".join(
        [
            "etf_ticker,as_of_date,constituent_ticker,constituent_name,weight,shares,market_value,industry,sort_order",
            "DEMOA,2026-04-16,DEMOX,Demo Component X,60,1000,60000,Demo Tech,1",
            "DEMOA,2026-04-16,DEMOY,Demo Component Y,40,800,40000,Demo Finance,2",
        ]
    )


def _yuanta_fixture() -> str:
    return """
    <html><body>
      <h3>基金權重-股票</h3>
      <div>交易日期: <br>2026/06/26</div>
      <div class="tbody">
        <div class="tr">
          <div class="td"><span>商品代碼</span> <span>2330</span></div>
          <div class="td"><span>商品名稱</span> <span>台積電</span></div>
          <div class="td"><span>商品數量</span> <span>520,512,559</span></div>
          <div class="td"><span>商品權重</span> <span>57.72</span></div>
        </div>
      </div>
    </body></html>
    """


def _fubon_fixture() -> str:
    return """
    <html><body>
      <h1>00900 Fubon sample ETF</h1>
      <div>資料日期：2026/06/26</div>
      <table>
        <tr><th>期貨代碼</th><th>期貨名稱</th><th>口數</th><th>金額</th><th>權重(%)</th></tr>
        <tr><td>WTXN6F</td><td>Sample future</td><td>58</td><td>515,643,200</td><td>1.6369</td></tr>
        <tr><td>期貨合計</td><td></td><td></td><td>515,643,200</td><td>1.6369</td></tr>
      </table>
      <table>
        <tr><th>股票代碼</th><th>股票名稱</th><th>股數</th><th>金額</th><th>權重(%)</th></tr>
        <tr><td>2303</td><td>聯電</td><td>19,558,000</td><td>3,207,512,000</td><td>10.1825</td></tr>
        <tr><td>2454</td><td>聯發科</td><td>742,000</td><td>2,878,960,000</td><td>9.1394</td></tr>
        <tr><td>股票合計</td><td></td><td></td><td>6,086,472,000</td><td>19.3219</td></tr>
      </table>
      <table>
        <tr><th>項目</th><th>金額</th></tr>
        <tr><td>現金 (TWD)</td><td>141,734,871</td></tr>
      </table>
    </body></html>
    """


def _snapshot_count(market_root: Path) -> int:
    db_path = market_root / "etf.sqlite"
    if not db_path.exists():
        return 0
    with sqlite3.connect(db_path) as conn:
        table = conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'etf_holding_snapshots'"
        ).fetchone()
        if table is None:
            return 0
        return int(conn.execute("SELECT COUNT(*) FROM etf_holding_snapshots").fetchone()[0])


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import central_store
import cli
import gmail_reader
import market
import server
from settings import load_app_settings


class SettingsDefaultsTests(unittest.TestCase):
    def test_settings_mirror_current_runtime_defaults(self) -> None:
        settings = load_app_settings(ROOT)

        self.assertEqual(settings.server.host, "127.0.0.1")
        self.assertEqual(settings.server.port, 8787)
        self.assertEqual(settings.profiles.default, server.DEFAULT_PROFILE)
        self.assertEqual(settings.profiles.labels, server.PROFILES)
        self.assertEqual(settings.profiles.currency, "TWD")
        self.assertEqual(settings.profiles.broker_fee_rate, 0.001425)
        self.assertEqual(settings.profiles.transaction_tax_rate, 0.003)

        self.assertEqual(settings.paths.market_data_dir, ROOT / "data" / "market_data")
        self.assertEqual(settings.paths.legacy_central_db, ROOT / "data" / "central.sqlite")
        self.assertEqual(settings.paths.quote_cache, ROOT / "data" / "quotes_cache.json")
        self.assertEqual(settings.paths.gmail_credentials, ROOT / "config" / "gmail_credentials.json")
        self.assertEqual(settings.paths.gmail_token, ROOT / "config" / "gmail_token.json")

        self.assertEqual(settings.markets.segment_files, central_store.SEGMENT_FILES)
        self.assertEqual(settings.markets.market_segments, central_store.MARKET_SEGMENTS)
        self.assertEqual(settings.markets.tw_market_window, market.TW_MARKET_WINDOW)
        self.assertEqual(settings.markets.us_market_window, market.US_MARKET_WINDOW)
        self.assertEqual(settings.markets.dashboard_market_context, market.US_MARKETS)

        self.assertEqual(settings.providers.quote_provider, "yfinance")
        self.assertEqual(settings.providers.official_history_source, "twse_tpex")
        self.assertEqual(settings.schedules.quote_refresh_minutes, 15)
        self.assertEqual(settings.schedules.quote_refresh_offset_minutes, 1)
        self.assertEqual(settings.schedules.after_close_time, "13:31")
        self.assertEqual(settings.schedules.official_daily_time, "14:00")
        self.assertEqual(settings.schedules.gmail_statements_time, "23:30")
        self.assertEqual(settings.schedules.history_backfill_minutes, 30)
        self.assertEqual(settings.schedules.history_backfill_offset_minutes, 7)
        self.assertEqual(settings.schedules.profile_refresh_seconds, 900)
        self.assertEqual(settings.gmail.broker_statement_subject_pattern, gmail_reader.BROKER_STATEMENT_SUBJECT.pattern)

        parser = cli.build_parser()
        subparsers = parser._subparsers._group_actions[0].choices
        gmail_check_query = subparsers["gmail-check"]._option_string_actions["--query"].default
        gmail_download_query = subparsers["gmail-download"]._option_string_actions["--query"].default
        self.assertEqual(settings.gmail.check_query, gmail_check_query)
        self.assertEqual(settings.gmail.download_query, gmail_download_query)

    def test_demo_sample_mode_defaults_to_local_sample_market_data(self) -> None:
        settings = load_app_settings(ROOT)

        self.assertFalse(settings.demo.enabled)
        self.assertEqual(settings.demo.quote_provider, "local_csv")
        self.assertEqual(settings.demo.history_provider, "local_csv")
        self.assertEqual(settings.demo.market_quote_csv, ROOT / "sample_data" / "market" / "quotes.csv")
        self.assertEqual(settings.demo.market_history_csv, ROOT / "sample_data" / "market" / "ohlcv_daily.csv")


if __name__ == "__main__":
    unittest.main()

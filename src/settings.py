from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class ServerDefaults:
    host: str = "127.0.0.1"
    port: int = 8787
    debug: bool = False
    share_token: str = ""
    refresh_on_start: bool = False


@dataclass(frozen=True)
class ProfileDefaults:
    default: str = "son"
    labels: dict[str, str] = field(
        default_factory=lambda: {
            "son": "\u5152\u5b50\u5e33\u6236",
            "mom": "\u6bcd\u89aa\u5e33\u6236",
        }
    )
    currency: str = "TWD"
    cash_available: int = 0
    important_signal_limit: int = 6
    broker_fee_rate: float = 0.001425
    transaction_tax_rate: float = 0.003


@dataclass(frozen=True)
class PathDefaults:
    project_root: Path
    data_dir: Path
    market_data_dir: Path
    legacy_central_db: Path
    profiles_dir: Path
    uploads_dir: Path
    quote_cache: Path
    refresh_log: Path
    cleanup_market_data_log: Path
    config_dir: Path
    gmail_credentials: Path
    gmail_token: Path
    templates_dir: Path
    static_dir: Path


@dataclass(frozen=True)
class MarketDefaults:
    segment_files: dict[str, str] = field(
        default_factory=lambda: {
            "etf": "etf.sqlite",
            "twse": "twse.sqlite",
            "tpex": "tpex.sqlite",
        }
    )
    market_segments: dict[str, str] = field(
        default_factory=lambda: {
            "ETF": "etf",
            "TWSE": "twse",
            "TPEX": "tpex",
        }
    )
    default_exchange_suffix: str = ".TW"
    tpex_exchange_suffix: str = ".TWO"
    tw_market_window: tuple[str, str] = ("09:01", "13:01")
    us_market_window: tuple[str, str] = ("21:30", "05:00")
    dashboard_market_context: list[dict[str, str]] = field(
        default_factory=lambda: [
            {"key": "nasdaq", "label": "Nasdaq", "symbol": "^IXIC"},
            {"key": "sp500", "label": "S&P 500", "symbol": "^GSPC"},
            {"key": "sox", "label": "\u8cbb\u534a", "symbol": "^SOX"},
            {"key": "nvda", "label": "NVDA", "symbol": "NVDA"},
            {"key": "amd", "label": "AMD", "symbol": "AMD"},
            {"key": "tsm", "label": "TSM ADR", "symbol": "TSM"},
            {"key": "us10y", "label": "\u7f8e\u50b510\u5e74", "symbol": "^TNX"},
            {"key": "dxy", "label": "\u7f8e\u5143\u6307\u6578", "symbol": "DX-Y.NYB"},
        ]
    )


@dataclass(frozen=True)
class ProviderDefaults:
    quote_provider: str = "yfinance"
    official_history_source: str = "twse_tpex"
    gmail_source: str = "gmail"
    manual_source: str = "manual"
    twse_daily_source: str = "TWSE_STOCK_DAY"
    tpex_daily_source: str = "TPEX_TRADING_STOCK"
    twse_profile_source: str = "TWSE_T187AP03_L"
    yfinance_history_source: str = "YFINANCE_HISTORY"
    twse_etf_dividend_source: str = "twse_etfortune"
    yahoo_dividend_source: str = "yahoo_historical"


@dataclass(frozen=True)
class ScheduleDefaults:
    quote_refresh_minutes: int = 15
    quote_refresh_offset_minutes: int = 1
    after_close_time: str = "13:31"
    official_daily_time: str = "14:00"
    gmail_statements_time: str = "23:30"
    history_backfill_minutes: int = 30
    history_backfill_offset_minutes: int = 7
    history_backfill_second_slot_minute: int = 37
    profile_refresh_seconds: int = 900


@dataclass(frozen=True)
class GmailDefaults:
    readonly_scope: str = "https://www.googleapis.com/auth/gmail.readonly"
    check_query: str = "from:service@billu.tssco.com.tw has:attachment filename:pdf newer_than:14d"
    download_query: str = (
        'from:service@billu.tssco.com.tw has:attachment filename:pdf '
        'subject:"\u53f0\u65b0\u8b49\u5238" "\u4ea4\u5272\u6191\u55ae" newer_than:30d'
    )
    broker_statement_subject_pattern: str = (
        "^\u53f0\u65b0\u8b49\u5238\\s+20\\d{2}\\.\\d{1,2}\\.\\d{1,2}\\s+\u4ea4\u5272\u6191\u55ae$"
    )
    check_limit: int = 10
    download_limit: int = 20
    scheduled_target_profile: str = "son"
    scheduled_max_results: int = 100
    scheduled_all_missing: bool = True


@dataclass(frozen=True)
class AppSettings:
    server: ServerDefaults
    profiles: ProfileDefaults
    paths: PathDefaults
    markets: MarketDefaults
    providers: ProviderDefaults
    schedules: ScheduleDefaults
    gmail: GmailDefaults
    deferred_settings_notes: tuple[str, ...] = (
        "Runtime code is not wired to this settings object yet.",
        "UI labels and localization remain in existing templates/static files.",
        "Provider behavior remains in current provider modules.",
    )


def load_app_settings(project_root: Path) -> AppSettings:
    root = Path(project_root)
    data_dir = root / "data"
    config_dir = root / "config"
    return AppSettings(
        server=ServerDefaults(),
        profiles=ProfileDefaults(),
        paths=PathDefaults(
            project_root=root,
            data_dir=data_dir,
            market_data_dir=data_dir / "market_data",
            legacy_central_db=data_dir / "central.sqlite",
            profiles_dir=data_dir / "profiles",
            uploads_dir=data_dir / "uploads",
            quote_cache=data_dir / "quotes_cache.json",
            refresh_log=data_dir / "refresh_log.json",
            cleanup_market_data_log=data_dir / "cleanup_market_data.log",
            config_dir=config_dir,
            gmail_credentials=config_dir / "gmail_credentials.json",
            gmail_token=config_dir / "gmail_token.json",
            templates_dir=root / "src" / "templates",
            static_dir=root / "src" / "static",
        ),
        markets=MarketDefaults(),
        providers=ProviderDefaults(),
        schedules=ScheduleDefaults(),
        gmail=GmailDefaults(),
    )

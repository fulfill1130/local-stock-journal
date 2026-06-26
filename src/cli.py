from __future__ import annotations

import argparse
import json
import socket
import time
from datetime import date, datetime
from pathlib import Path

from central_store import (
    add_split_action,
    begin_update_status,
    check_market_db,
    cleanup_market_data,
    finish_update_status,
    get_instrument,
    get_instruments_by_ticker,
    is_specific_name,
    list_ohlcv_daily,
    list_corporate_actions,
    migrate_market_databases,
    migrate_legacy_central_db,
    ohlcv_daily_stats,
    rebuild_health_summary,
    set_instrument,
    upsert_etf_dividends,
    upsert_ohlcv_daily,
)
from dividend_fetcher import fetch_twse_etf_dividends, parse_twse_etf_dividend_tsv
from gmail_reader import list_matching_messages, sync_latest_pdf_attachments
from official_market import (
    fetch_tpex_daily_range,
    fetch_tpex_name,
    fetch_twse_daily_range,
    fetch_twse_name,
    parse_iso_date,
)
from official_sync import sync_missing_official_daily_bars
from server import (
    DEFAULT_PROFILE,
    PROFILES,
    DemoRuntimeError,
    create_app,
    ensure_profile_files,
    profile_state_path,
    validate_demo_runtime,
)
from store import (
    rebuild_holdings_from_transactions,
    record_buy,
    record_sell,
    remove_watch,
    set_cash,
    set_price_override,
    update_state,
    upsert_watch,
)
from utils import yahoo_symbol


def add_profile_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--profile",
        choices=sorted(PROFILES),
        default=DEFAULT_PROFILE,
        help="Profile to update. Default: son",
    )


def _unique_hosts(hosts: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for host in hosts:
        if host not in seen:
            seen.add(host)
            result.append(host)
    return result


def _preflight_hosts(host: str) -> list[str]:
    normalized = (host or "127.0.0.1").strip()
    if normalized == "localhost":
        normalized = "127.0.0.1"
    if normalized in {"0.0.0.0", ""}:
        return ["127.0.0.1", "0.0.0.0"]
    if normalized == "127.0.0.1":
        return ["127.0.0.1", "0.0.0.0"]
    return [normalized]


def _can_connect(host: str, port: int) -> bool:
    connect_host = "127.0.0.1" if host in {"0.0.0.0", ""} else host
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(0.25)
            return sock.connect_ex((connect_host, int(port))) == 0
    except OSError:
        return False


def preflight_port_available(host: str, port: int) -> tuple[bool, str]:
    for candidate in _preflight_hosts(host):
        if _can_connect(candidate, port):
            return (
                False,
                f"Port {port} appears to be in use for {host}. "
                "Stop the existing server or choose a different --port.",
            )
    for candidate in _preflight_hosts(host):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
                    sock.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
                sock.bind((candidate, int(port)))
        except OSError:
            return (
                False,
                f"Port {port} appears to be occupied for {host}. "
                "Stop the existing server or choose a different --port.",
            )
    return True, ""


def print_startup_runtime_info(
    project_root: Path,
    runtime_root: Path,
    demo_mode: bool,
    host: str,
    port: int,
) -> None:
    root_label = "runtime_root" if demo_mode else "data_root"
    print(f"project_root={project_root.resolve()}")
    print(f"{root_label}={runtime_root.resolve()}")
    print(f"demo_mode={str(bool(demo_mode)).lower()}")
    print(f"host={host}")
    print(f"port={port}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Stock Daily Helper")
    sub = parser.add_subparsers(dest="command")

    serve = sub.add_parser("serve", help="Start the local dashboard")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8787)
    serve.add_argument("--debug", action="store_true")
    serve.add_argument("--share-token", default="")
    serve.add_argument("--refresh-on-start", action="store_true")

    serve_demo = sub.add_parser("serve-demo", help="Start a read-only synthetic demo dashboard")
    serve_demo.add_argument("--host", default="127.0.0.1")
    serve_demo.add_argument("--port", type=int, default=8787)
    serve_demo.add_argument("--debug", action="store_true")
    serve_demo.add_argument("--share-token", default="")
    serve_demo.add_argument(
        "--runtime",
        type=Path,
        default=None,
        help="Demo runtime directory. Defaults to ./demo_runtime.",
    )
    serve_demo.add_argument(
        "--check",
        action="store_true",
        help="Validate and create the demo app, then exit without starting the server.",
    )

    desktop_demo = sub.add_parser("desktop-demo", help="Start the optional demo desktop shell")
    desktop_demo.add_argument(
        "--runtime",
        type=Path,
        default=None,
        help="Demo runtime directory. Defaults to ./demo_runtime.",
    )

    buy = sub.add_parser("buy", help="Record a buy and update holdings")
    buy.add_argument("ticker")
    buy.add_argument("shares", type=float)
    buy.add_argument("price", type=float)
    buy.add_argument("--name", default="")
    buy.add_argument("--type", default="STOCK")
    buy.add_argument("--suffix", default=".TW")
    buy.add_argument("--fee", type=float, default=0.0)
    buy.add_argument("--date", default="")
    buy.add_argument("--note", default="")
    add_profile_argument(buy)

    sell = sub.add_parser("sell", help="Record a sell and update holdings")
    sell.add_argument("ticker")
    sell.add_argument("shares", type=float)
    sell.add_argument("price", type=float)
    sell.add_argument("--fee", type=float, default=0.0)
    sell.add_argument("--tax", type=float, default=0.0)
    sell.add_argument("--date", default="")
    sell.add_argument("--note", default="")
    add_profile_argument(sell)

    watch = sub.add_parser("watch", help="Create or update a watchlist item")
    watch.add_argument("ticker")
    watch.add_argument("--name", default="")
    watch.add_argument("--suffix", default=".TW")
    watch.add_argument("--buy", type=float, default=None)
    watch.add_argument("--alert", type=float, default=None)
    watch.add_argument("--stop", type=float, default=None)
    watch.add_argument("--sell", type=float, default=None)
    watch.add_argument("--reason", default="")
    watch.add_argument("--note", default="")
    add_profile_argument(watch)

    cash = sub.add_parser("cash", help="Set available cash")
    cash.add_argument("amount", type=float)
    add_profile_argument(cash)

    unwatch = sub.add_parser("unwatch", help="Remove a watchlist item")
    unwatch.add_argument("ticker")
    add_profile_argument(unwatch)

    price = sub.add_parser("price", help="Set a manual price override")
    price.add_argument("ticker")
    price.add_argument("close", type=float)
    price.add_argument("--suffix", default=".TW")
    price.add_argument("--prev-close", type=float, default=None)
    price.add_argument("--note", default="")
    add_profile_argument(price)

    split = sub.add_parser("split", help="Record a stock/ETF split corporate action")
    split.add_argument("ticker")
    split.add_argument("--date", required=True, help="Effective date, YYYY-MM-DD")
    split.add_argument("--ratio", required=True, help="Split ratio, for example 1:4")
    split.add_argument("--note", default="")

    history_sync = sub.add_parser("history-sync", help="Sync official daily OHLCV history into segmented market databases")
    history_sync.add_argument("ticker")
    history_sync.add_argument("--source", choices=["twse", "tpex"], default="twse")
    history_sync.add_argument("--start", default=f"{date.today().year}-01-01")
    history_sync.add_argument("--end", default=date.today().isoformat())

    history_sync_verified = sub.add_parser(
        "history-sync-verified",
        help="Slowly sync and validate one official daily OHLCV history series",
    )
    history_sync_verified.add_argument("ticker")
    history_sync_verified.add_argument("--source", choices=["auto", "twse", "tpex"], default="auto")
    history_sync_verified.add_argument("--start", default=f"{date.today().year}-01-01")
    history_sync_verified.add_argument("--end", default=date.today().isoformat())
    history_sync_verified.add_argument(
        "--request-pause",
        type=float,
        default=1.0,
        help="Seconds to wait between monthly source requests. Default: 1.0",
    )

    history_sync_all = sub.add_parser("history-sync-all", help="Sync official daily OHLCV history for central instruments")
    history_sync_all.add_argument("--start", default=f"{date.today().year}-01-01")
    history_sync_all.add_argument("--end", default=date.today().isoformat())

    history_sync_verified_all = sub.add_parser(
        "history-sync-verified-all",
        help="Slowly sync and validate official daily OHLCV history for central instruments",
    )
    history_sync_verified_all.add_argument("--start", default=f"{date.today().year}-01-01")
    history_sync_verified_all.add_argument("--end", default=date.today().isoformat())
    history_sync_verified_all.add_argument(
        "--request-pause",
        type=float,
        default=1.0,
        help="Seconds to wait between monthly source requests. Default: 1.0",
    )
    history_sync_verified_all.add_argument(
        "--ticker-pause",
        type=float,
        default=3.0,
        help="Seconds to wait after each ticker completes. Default: 3.0",
    )

    official_daily_sync = sub.add_parser(
        "official-daily-sync",
        help="Catch up missing official daily OHLCV rows for central instruments",
    )
    official_daily_sync.add_argument("--end", default=date.today().isoformat())
    official_daily_sync.add_argument(
        "--ticker-pause",
        type=float,
        default=0.5,
        help="Seconds to wait after each ticker completes. Default: 0.5",
    )

    sub.add_parser(
        "cleanup-market-data",
        help="Delete expired market data using the configured retention policy",
    )

    sub.add_parser(
        "migrate-market-db",
        help="Migrate segmented market SQLite files to the instrument_id schema",
    )

    sub.add_parser(
        "rebuild-health-summary",
        help="Rebuild local market data health summaries without external API calls",
    )

    sub.add_parser(
        "check-market-db",
        help="Check segmented market SQLite schema and relationships",
    )

    sync_official_daily = sub.add_parser(
        "sync-official-daily",
        help="Alias for official-daily-sync",
    )
    sync_official_daily.add_argument("--end", default=date.today().isoformat())
    sync_official_daily.add_argument(
        "--ticker-pause",
        type=float,
        default=0.5,
        help="Seconds to wait after each ticker completes. Default: 0.5",
    )

    dividend_test = sub.add_parser("dividend-test", help="Fetch ETF dividend records from TWSE ETFortune")
    dividend_test.add_argument("ticker")
    dividend_test.add_argument("--start-year", type=int, default=date.today().year)
    dividend_test.add_argument("--end-year", type=int, default=date.today().year)
    dividend_test.add_argument("--json", action="store_true")

    seed_dividends = sub.add_parser("seed-dividends-tsv", help="Import local ETF dividend TSV records")
    seed_dividends.add_argument("path", help="TSV file path")
    seed_dividends.add_argument("--source", default="manual")

    gmail_check = sub.add_parser(
        "gmail-check",
        help="Authorize Gmail read-only access and list matching PDF emails",
    )
    gmail_check.add_argument(
        "--query",
        default='from:service@billu.tssco.com.tw has:attachment filename:pdf newer_than:14d',
    )
    gmail_check.add_argument("--limit", type=int, default=10)

    gmail_download = sub.add_parser(
        "gmail-download",
        help="Download the latest broker PDF attachment into the local upload library",
    )
    gmail_download.add_argument(
        "--query",
        default=(
            'from:service@billu.tssco.com.tw has:attachment filename:pdf '
            'subject:"台新證券" "交割憑單" newer_than:30d'
        ),
    )
    gmail_download.add_argument("--limit", type=int, default=20)
    gmail_download.add_argument(
        "--all-missing",
        action="store_true",
        help="Download every missing PDF in the query instead of only the latest statement date",
    )
    add_profile_argument(gmail_download)

    return parser


def run_cli(project_root: Path, argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "gmail-check":
        rows = list_matching_messages(
            project_root / "config" / "gmail_credentials.json",
            project_root / "config" / "gmail_token.json",
            query=args.query,
            max_results=args.limit,
        )
        print(json.dumps(rows, ensure_ascii=False, indent=2))
        print(f"matched={len(rows)}")
        return 0

    if args.command == "gmail-download":
        summary = sync_latest_pdf_attachments(
            project_root,
            project_root / "data" / "market_data",
            profile_slug=args.profile,
            credentials_path=project_root / "config" / "gmail_credentials.json",
            token_path=project_root / "config" / "gmail_token.json",
            query=args.query,
            max_results=args.limit,
            all_missing=args.all_missing,
        )
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 1 if summary["failed"] else 0

    if args.command == "serve-demo":
        try:
            demo_runtime = validate_demo_runtime(project_root, args.runtime)
        except DemoRuntimeError as exc:
            print(str(exc))
            return 2
        host = getattr(args, "host", "127.0.0.1")
        port = getattr(args, "port", 8787)
        if not getattr(args, "check", False):
            port_ok, port_message = preflight_port_available(host, port)
            if not port_ok:
                print(port_message)
                return 2
        app = create_app(
            project_root,
            share_token=getattr(args, "share_token", ""),
            refresh_on_start=False,
            runtime_root=demo_runtime,
            demo_mode=True,
        )
        print(f"Demo Dashboard: http://{host}:{port}/demo")
        print_startup_runtime_info(project_root, demo_runtime, True, host, port)
        if getattr(args, "check", False):
            return 0
        app.run(host=host, port=port, debug=getattr(args, "debug", False))
        return 0

    if args.command == "desktop-demo":
        try:
            demo_runtime = validate_demo_runtime(project_root, args.runtime)
        except DemoRuntimeError as exc:
            print(str(exc))
            return 2
        try:
            launch_desktop_demo(project_root, demo_runtime)
        except ModuleNotFoundError as exc:
            if exc.name == "webview" or "webview" in str(exc):
                print(desktop_dependency_instructions())
                return 2
            raise
        return 0

    if args.command in (None, "serve"):
        host = getattr(args, "host", "127.0.0.1")
        port = getattr(args, "port", 8787)
        debug = getattr(args, "debug", False)
        port_ok, port_message = preflight_port_available(host, port)
        if not port_ok:
            print(port_message)
            return 2
        app = create_app(
            project_root,
            share_token=getattr(args, "share_token", ""),
            refresh_on_start=getattr(args, "refresh_on_start", False),
        )
        print(f"Dashboard: http://{host}:{port}")
        print_startup_runtime_info(project_root, project_root / "data", False, host, port)
        app.run(host=host, port=port, debug=debug)
        return 0

    ensure_profile_files(project_root)
    state_path = profile_state_path(project_root, getattr(args, "profile", DEFAULT_PROFILE))
    central_db_path = project_root / "data" / "market_data"

    if args.command == "migrate-market-db":
        results = migrate_market_databases(central_db_path, backup=True)
        for row in results:
            copied = row.get("copied") or {}
            print(
                f"{row.get('database')}: needed={row.get('needed')} "
                f"backup={row.get('backup') or 'none'} copied={copied}"
            )
        summaries = rebuild_health_summary(central_db_path)
        print(f"health_summary_rebuilt={len(summaries)}")
        return 0

    migrate_legacy_central_db(project_root / "data" / "central.sqlite", central_db_path)

    if args.command == "rebuild-health-summary":
        summaries = rebuild_health_summary(central_db_path)
        counts: dict[str, int] = {}
        for row in summaries:
            status = str(row.get("history_status") or "unknown")
            counts[status] = counts.get(status, 0) + 1
        for status, count in sorted(counts.items()):
            print(f"{status}: {count}")
        print(f"rebuilt={len(summaries)}")
        return 0

    if args.command == "check-market-db":
        results = check_market_db(central_db_path)
        exit_code = 0
        for row in results:
            level = row.get("level", "")
            if level == "error":
                exit_code = 1
            print(
                f"[{level}] {row.get('segment')} {row.get('check')}: "
                f"{row.get('message')} ({row.get('database')})"
            )
        return exit_code

    if args.command == "cleanup-market-data":
        results = cleanup_market_data(central_db_path)
        log_path = project_root / "data" / "cleanup_market_data.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        lines = [f"[{datetime.now().astimezone().isoformat(timespec='seconds')}] cleanup-market-data"]
        total_deleted = 0
        for row in results:
            total_deleted += int(row.get("deleted", 0) or 0)
            line = (
                f"{row['segment']}.{row['table']} cutoff={row['cutoff']} "
                f"deleted={row['deleted']} db={row['database']}"
            )
            lines.append(line)
            print(line)
        lines.append(f"total_deleted={total_deleted}")
        log_path.write_text(
            (log_path.read_text(encoding="utf-8") if log_path.exists() else "")
            + "\n".join(lines)
            + "\n",
            encoding="utf-8",
        )
        print(f"total_deleted={total_deleted}")
        print(f"log={log_path}")
        return 0

    if args.command == "seed-dividends-tsv":
        tsv_path = Path(args.path)
        if not tsv_path.is_absolute():
            tsv_path = project_root / tsv_path
        if not tsv_path.exists():
            parser.error(f"TSV file not found: {tsv_path}")
        records = parse_twse_etf_dividend_tsv(tsv_path.read_text(encoding="utf-8"), source=args.source)
        rows = [record.as_dict() for record in records]
        written = upsert_etf_dividends(central_db_path, rows)
        tickers = sorted({row["ticker"] for row in rows})
        print(f"Imported dividend rows={len(rows)}, db_changes={written}, tickers={','.join(tickers)}")
        return 0

    if args.command == "dividend-test":
        records = fetch_twse_etf_dividends(args.ticker, args.start_year, args.end_year)
        rows = [record.as_dict() for record in records]
        if args.json:
            print(json.dumps(rows, ensure_ascii=False, indent=2))
            return 0
        if not rows:
            print(f"No dividend records found for {args.ticker}")
            return 0
        print(f"TWSE ETF dividend records for {args.ticker}: {len(rows)}")
        print(f"source={rows[0]['source_url']}")
        for row in rows:
            dividend = "N/A" if row["dividend"] is None else f"{row['dividend']:g}"
            print(
                f"{row['ex_dividend_date']} payout={row['payout_date']} "
                f"dividend={dividend} name={row['name']}"
            )
        return 0

    if args.command == "history-sync":
        start_date = parse_iso_date(args.start)
        end_date = parse_iso_date(args.end)
        if end_date < start_date:
            parser.error("--end must be on or after --start")
        rows = (
            fetch_tpex_daily_range(args.ticker, start_date, end_date)
            if args.source == "tpex"
            else fetch_twse_daily_range(args.ticker, start_date, end_date)
        )
        sync_official_name_if_generic(central_db_path, args.ticker, args.source, start_date)
        written = upsert_ohlcv_daily(central_db_path, rows)
        stats = ohlcv_daily_stats(central_db_path, args.ticker)
        print(
            f"Synced {written} rows [{args.source.upper()}] for {args.ticker}: "
            f"{stats['first_date']}..{stats['last_date']} ({stats['bar_count']} total)"
        )
        return 0

    if args.command == "history-sync-verified":
        start_date = parse_iso_date(args.start)
        end_date = parse_iso_date(args.end)
        if end_date < start_date:
            parser.error("--end must be on or after --start")
        instrument = get_instrument(central_db_path, args.ticker)
        source = args.source
        if source == "auto":
            source = "tpex" if instrument and instrument.get("exchange_suffix") == ".TWO" else "twse"
        market = "TPEX" if source == "tpex" else "TWSE"
        rows = (
            fetch_tpex_daily_range(
                args.ticker,
                start_date,
                end_date,
                pause_seconds=max(args.request_pause, 0.0),
            )
            if market == "TPEX"
            else fetch_twse_daily_range(
                args.ticker,
                start_date,
                end_date,
                pause_seconds=max(args.request_pause, 0.0),
            )
        )
        sync_official_name_if_generic(central_db_path, args.ticker, source, start_date)
        written = upsert_ohlcv_daily(central_db_path, rows)
        db_rows = list_ohlcv_daily(
            central_db_path,
            args.ticker,
            start_date=start_date.isoformat(),
            end_date=end_date.isoformat(),
        )
        validation = validate_history_rows(db_rows, market)
        stats = ohlcv_daily_stats(central_db_path, args.ticker)
        status = "OK" if not validation["issues"] else "CHECK"
        issue_text = "; ".join(validation["issues"]) if validation["issues"] else "no issues"
        print(
            f"{status} {args.ticker} [{market}]: "
            f"fetched={written}, total={stats['bar_count']}, "
            f"range={stats['first_date']}..{stats['last_date']}, "
            f"duplicates={validation['duplicate_dates']}, "
            f"invalid_ohlc={validation['invalid_ohlc_rows']}, "
            f"blank_ohlc={validation['blank_ohlc_rows']}, "
            f"null_close={validation['null_close_rows']}; {issue_text}"
        )
        return 0

    if args.command == "history-sync-all":
        start_date = parse_iso_date(args.start)
        end_date = parse_iso_date(args.end)
        if end_date < start_date:
            parser.error("--end must be on or after --start")
        instruments = get_instruments_by_ticker(central_db_path)
        synced = []
        fallback = []
        failed = []
        for ticker, instrument in sorted(instruments.items()):
            try:
                if instrument.get("exchange_suffix") == ".TW":
                    rows = fetch_twse_daily_range(ticker, start_date, end_date)
                    source = "TWSE"
                    sync_official_name_if_generic(central_db_path, ticker, "twse", start_date)
                else:
                    rows = fetch_tpex_daily_range(ticker, start_date, end_date)
                    source = "TPEX"
                    sync_official_name_if_generic(central_db_path, ticker, "tpex", start_date)
                written = upsert_ohlcv_daily(central_db_path, rows)
                stats = ohlcv_daily_stats(central_db_path, ticker)
                synced.append((ticker, source, written, stats["bar_count"], stats["first_date"], stats["last_date"]))
                if source not in {"TWSE", "TPEX"}:
                    fallback.append(ticker)
            except Exception as exc:
                failed.append((ticker, str(exc)))
        for ticker, source, written, total, first_date, last_date in synced:
            print(f"Synced {ticker} [{source}]: {written} rows, {total} total, {first_date}..{last_date}")
        for ticker, error in failed:
            print(f"Failed {ticker}: {error}")
        print(f"Completed: synced={len(synced)}, fallback={len(fallback)}, failed={len(failed)}")
        return 0

    if args.command == "history-sync-verified-all":
        start_date = parse_iso_date(args.start)
        end_date = parse_iso_date(args.end)
        if end_date < start_date:
            parser.error("--end must be on or after --start")
        instruments = get_instruments_by_ticker(central_db_path)
        results = []
        failed = []
        ordered = sorted(instruments.items())
        for index, (ticker, instrument) in enumerate(ordered, start=1):
            market = "TPEX" if instrument.get("exchange_suffix") == ".TWO" else "TWSE"
            source = "tpex" if market == "TPEX" else "twse"
            try:
                rows = (
                    fetch_tpex_daily_range(
                        ticker,
                        start_date,
                        end_date,
                        pause_seconds=max(args.request_pause, 0.0),
                    )
                    if market == "TPEX"
                    else fetch_twse_daily_range(
                        ticker,
                        start_date,
                        end_date,
                        pause_seconds=max(args.request_pause, 0.0),
                    )
                )
                sync_official_name_if_generic(central_db_path, ticker, source, start_date)
                written = upsert_ohlcv_daily(central_db_path, rows)
                db_rows = list_ohlcv_daily(
                    central_db_path,
                    ticker,
                    start_date=start_date.isoformat(),
                    end_date=end_date.isoformat(),
                )
                validation = validate_history_rows(db_rows, market)
                stats = ohlcv_daily_stats(central_db_path, ticker)
                results.append(
                    (
                        ticker,
                        market,
                        written,
                        stats["bar_count"],
                        stats["first_date"],
                        stats["last_date"],
                        validation,
                    )
                )
                status = "OK" if not validation["issues"] else "CHECK"
                issue_text = "; ".join(validation["issues"]) if validation["issues"] else "no issues"
                print(
                    f"[{index}/{len(ordered)}] {status} {ticker} [{market}]: "
                    f"fetched={written}, total={stats['bar_count']}, "
                    f"range={stats['first_date']}..{stats['last_date']}, "
                    f"duplicates={validation['duplicate_dates']}, "
                    f"invalid_ohlc={validation['invalid_ohlc_rows']}, "
                    f"blank_ohlc={validation['blank_ohlc_rows']}, "
                    f"null_close={validation['null_close_rows']}; {issue_text}",
                    flush=True,
                )
            except Exception as exc:
                failed.append((ticker, str(exc)))
                print(f"[{index}/{len(ordered)}] FAILED {ticker}: {exc}", flush=True)
            if args.ticker_pause > 0 and index < len(ordered):
                time.sleep(args.ticker_pause)
        print(
            f"Completed verified sync: ok={sum(1 for row in results if not row[-1]['issues'])}, "
            f"check={sum(1 for row in results if row[-1]['issues'])}, failed={len(failed)}"
        )
        return 0

    if args.command in {"official-daily-sync", "sync-official-daily"}:
        end_date = parse_iso_date(args.end)
        started_at = datetime.now().astimezone().isoformat(timespec="seconds")
        begin_update_status(
            central_db_path,
            "official_daily",
            "twse_tpex",
            started_at,
            message="CLI official daily sync started",
        )
        try:
            summary = sync_missing_official_daily_bars(
                central_db_path,
                end_date=end_date,
                ticker_pause_seconds=max(args.ticker_pause, 0.0),
            )
        except Exception as exc:
            finish_update_status(
                central_db_path,
                "official_daily",
                "twse_tpex",
                started_at,
                datetime.now().astimezone().isoformat(timespec="seconds"),
                status="failed",
                message=str(exc)[:240],
            )
            raise
        for item in summary["updated"]:
            print(
                f"Updated {item['ticker']} [{item['source']}]: "
                f"{item['rows']} rows {','.join(item['trade_dates'])}"
            )
        for item in summary["no_new_rows"]:
            print(
                f"No rows {item['ticker']} [{item['source']}]: "
                f"{item['start_date']}..{item['end_date']}"
            )
        for item in summary["failed"]:
            print(f"Failed {item['ticker']}: {item['error']}")
        print(
            f"Completed official daily sync: instruments={summary['instrument_count']}, "
            f"rows_written={summary['rows_written']}, "
            f"updated={len(summary['updated'])}, "
            f"no_new_rows={len(summary['no_new_rows'])}, "
            f"already_current={len(summary['already_current'])}, "
            f"failed={len(summary['failed'])}"
        )
        finish_update_status(
            central_db_path,
            "official_daily",
            "twse_tpex",
            started_at,
            datetime.now().astimezone().isoformat(timespec="seconds"),
            status="success" if not summary["failed"] else "failed",
            message=(
                f"CLI rows_written={summary['rows_written']}; "
                f"updated={len(summary['updated'])}; failed={len(summary['failed'])}"
            ),
        )
        return 0

    if args.command == "buy":
        def buy_mutator(state: dict[str, object]) -> None:
            record_buy(
                state,
                ticker=args.ticker,
                shares=args.shares,
                price=args.price,
                name=args.name or None,
                asset_type=args.type,
                suffix=args.suffix,
                fee=args.fee,
                trade_date=args.date or None,
                note=args.note,
            )
            rebuild_holdings_from_transactions(state, list_corporate_actions(central_db_path))

        update_state(
            state_path,
            buy_mutator,
        )
        print(f"Recorded BUY [{args.profile}]: {args.ticker} {args.shares:g} @ {args.price:g}, fee {args.fee:g}")
        return 0

    if args.command == "sell":
        def sell_mutator(state: dict[str, object]) -> None:
            record_sell(
                state,
                ticker=args.ticker,
                shares=args.shares,
                price=args.price,
                fee=args.fee,
                tax=args.tax,
                trade_date=args.date or None,
                note=args.note,
            )
            rebuild_holdings_from_transactions(state, list_corporate_actions(central_db_path))

        update_state(
            state_path,
            sell_mutator,
        )
        print(
            f"Recorded SELL [{args.profile}]: {args.ticker} {args.shares:g} @ {args.price:g}, "
            f"fee {args.fee:g}, tax {args.tax:g}"
        )
        return 0

    if args.command == "watch":
        update_state(
            state_path,
            lambda state: upsert_watch(
                state,
                ticker=args.ticker,
                name=args.name or None,
                suffix=args.suffix,
                target_buy_price=args.buy,
                alert_price=args.alert,
                stop_loss_price=args.stop,
                target_sell_price=args.sell,
                reason=args.reason,
                note=args.note,
            ),
        )
        print(f"Updated watchlist [{args.profile}]: {args.ticker}")
        return 0

    if args.command == "cash":
        update_state(state_path, lambda state: set_cash(state, args.amount))
        print(f"Set cash [{args.profile}]: {args.amount:g}")
        return 0

    if args.command == "unwatch":
        update_state(state_path, lambda state: remove_watch(state, args.ticker))
        print(f"Removed watchlist item [{args.profile}]: {args.ticker}")
        return 0

    if args.command == "price":
        symbol = yahoo_symbol(args.ticker, args.suffix)
        update_state(
            state_path,
            lambda state: set_price_override(
                state,
                symbol=symbol,
                close=args.close,
                prev_close=args.prev_close,
                note=args.note,
            ),
        )
        print(f"Set manual price [{args.profile}]: {symbol} close={args.close:g}")
        return 0

    if args.command == "split":
        if ":" in args.ratio:
            left, right = args.ratio.split(":", 1)
        elif "/" in args.ratio:
            left, right = args.ratio.split("/", 1)
        else:
            raise ValueError("--ratio must use a format like 1:4")
        action = add_split_action(
            central_db_path,
            ticker=args.ticker,
            effective_date=args.date,
            ratio_from=float(left),
            ratio_to=float(right),
            note=args.note,
            source="manual_cli",
        )
        actions = list_corporate_actions(central_db_path)
        for profile_slug in PROFILES:
            profile_path = profile_state_path(project_root, profile_slug)
            update_state(profile_path, lambda state: rebuild_holdings_from_transactions(state, actions))
        print(
            f"Recorded split: {action['ticker']} {action['effective_date']} "
            f"{action['ratio_from']:g}:{action['ratio_to']:g}"
        )
        return 0

    parser.print_help()
    return 1


def desktop_dependency_instructions() -> str:
    return (
        "Optional desktop dependency pywebview is not installed.\n"
        "Install desktop dependencies with:\n"
        "pip install -r requirements-desktop.txt\n"
        "Normal web commands still work without pywebview:\n"
        "python src/main.py serve-demo\n"
        "python src/main.py serve"
    )


def launch_desktop_demo(project_root: Path, runtime_root: Path) -> None:
    from desktop_shell import DesktopShellConfig
    from pywebview_desktop_shell import PyWebviewDesktopShell

    shell = PyWebviewDesktopShell(
        DesktopShellConfig(
            project_root=project_root,
            runtime_root=runtime_root,
            profile="demo",
            demo_mode=True,
        )
    )
    shell.open_main_window()


def sync_official_name_if_generic(
    central_db_path: Path,
    ticker: str,
    source: str,
    reference_date: date,
) -> None:
    instrument = get_instrument(central_db_path, ticker)
    if instrument is None or is_specific_name(instrument.get("name", ""), ticker):
        return
    official_name = (
        fetch_tpex_name(ticker, reference_date)
        if source.lower() == "tpex"
        else fetch_twse_name(ticker, reference_date)
    )
    if not official_name:
        return
    set_instrument(
        central_db_path,
        ticker=ticker,
        name=official_name,
        asset_type=instrument.get("type", ""),
        exchange_suffix=instrument.get("exchange_suffix", ".TW"),
        source="official_name",
    )


def validate_history_rows(rows: list[dict], expected_market: str) -> dict[str, object]:
    dates = [str(row.get("trade_date", "")) for row in rows if row.get("trade_date")]
    duplicate_dates = len(dates) - len(set(dates))
    invalid_ohlc_rows = 0
    blank_ohlc_rows = 0
    null_close_rows = 0
    wrong_market_rows = 0

    for row in rows:
        open_price = row.get("open")
        high = row.get("high")
        low = row.get("low")
        close = row.get("close")
        if all(value is None for value in (open_price, high, low, close)):
            blank_ohlc_rows += 1
        elif close is None:
            null_close_rows += 1
        if row.get("source_market") != expected_market:
            wrong_market_rows += 1
        if None not in (open_price, high, low, close):
            if not (low <= high and low <= open_price <= high and low <= close <= high):
                invalid_ohlc_rows += 1

    issues = []
    if not rows:
        issues.append("no rows returned")
    if duplicate_dates:
        issues.append(f"{duplicate_dates} duplicate trade dates")
    if invalid_ohlc_rows:
        issues.append(f"{invalid_ohlc_rows} rows violate OHLC bounds")
    if null_close_rows:
        issues.append(f"{null_close_rows} rows missing close")
    if wrong_market_rows:
        issues.append(f"{wrong_market_rows} rows from unexpected market")

    return {
        "duplicate_dates": duplicate_dates,
        "invalid_ohlc_rows": invalid_ohlc_rows,
        "blank_ohlc_rows": blank_ohlc_rows,
        "null_close_rows": null_close_rows,
        "wrong_market_rows": wrong_market_rows,
        "issues": issues,
    }

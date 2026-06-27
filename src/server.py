from __future__ import annotations

import json
import base64
import hashlib
import mimetypes
import sqlite3
import uuid
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from flask import Flask, Response, abort, jsonify, redirect, render_template, request, send_file, url_for
from pypdf import PdfReader
from werkzeug.utils import secure_filename

from analyzer import build_dashboard_state
from central_store import (
    SEGMENT_FILES,
    add_split_action,
    apply_daily_quote_fallbacks,
    begin_update_status,
    enrich_items_with_instruments,
    ensure_central_db,
    finish_update_status,
    get_etf_holding_snapshot,
    get_instrument,
    is_specific_name,
    latest_after_close_quote,
    list_dividend_targets,
    list_corporate_actions,
    list_etf_dividends,
    list_ohlcv_daily,
    list_instruments,
    list_operation_logs,
    list_uploaded_documents,
    list_update_status,
    load_quote_cache,
    migrate_legacy_central_db,
    ohlcv_daily_stats,
    record_dividend_refresh_status,
    record_market_data_problem,
    record_operation_log,
    record_uploaded_document,
    rebuild_health_summary,
    register_instrument,
    seed_instruments_from_state,
    set_dividend_target,
    get_uploaded_document,
    update_uploaded_document_status,
    set_instrument,
    update_instrument_history_status,
    update_instrument_listing_date,
    upsert_ohlcv_daily,
    upsert_after_close_quotes,
    upsert_etf_dividends,
    upsert_etf_holding_snapshot,
    upsert_ohlcv_intraday_15m,
    upsert_quote_snapshots_15m,
)
from dividend_fetcher import fetch_twse_etf_dividends, fetch_yahoo_stock_dividends
from gmail_reader import sync_latest_pdf_attachments
from import_staging import (
    create_import_staging_batch,
    list_import_staging_batches,
    load_import_staging_batch,
    summarize_import_staging_batch,
)
from http_etf_holdings_provider import load_configured_http_etf_holdings_providers
from local_csv_etf_holdings_provider import normalize_etf_holdings_csv_text
from market import (
    QuoteService,
    US_MARKETS,
    apply_price_overrides,
    attach_quotes_to_items,
    fetch_symbol_bundle,
    market_snapshot,
    refresh_allowed_for_symbol,
    symbols_for_state,
)
from official_sync import sync_missing_official_daily_bars
from official_market import fetch_tpex_month, fetch_twse_listed_company_profiles, fetch_twse_month, month_starts, parse_iso_date
from scheduler import append_refresh_log, start_daily_time_scheduler, start_interval_refresh_scheduler
from store import ensure_transaction_ids, load_state, public_state_copy, rebuild_holdings_from_transactions, record_buy, record_sell, save_state, trade_consideration_twd, update_state
from utils import as_float, fmt_money, fmt_pct, now_string, yahoo_symbol


PROFILES = {
    "son": "兒子帳戶",
    "mom": "母親帳戶",
}
DEFAULT_PROFILE = "son"
DEMO_PROFILE = {"demo": "Demo Mode / 合成資料"}
DEMO_SENTINEL = ".demo_runtime"


class DemoRuntimeError(RuntimeError):
    pass


def demo_runtime_instructions() -> str:
    return (
        "Demo runtime is not ready. Run:\n"
        "python scripts/create_demo_data.py\n"
        "python scripts/prepare_demo_runtime.py --reset"
    )


def validate_demo_runtime(project_root: Path, runtime_root: Path | None = None) -> Path:
    root = Path(project_root).resolve()
    target = Path(runtime_root or root / "demo_runtime").resolve()
    forbidden_roots = {root / "data", root / "sample_data"}
    if target == root or any(target == forbidden or forbidden in target.parents for forbidden in forbidden_roots):
        raise DemoRuntimeError(f"Refusing unsafe demo runtime target: {target}")
    if not target.exists():
        raise DemoRuntimeError(demo_runtime_instructions())
    if not (target / DEMO_SENTINEL).exists():
        raise DemoRuntimeError(f"Refusing demo runtime without {DEMO_SENTINEL}: {target}")
    if not (target / "profiles" / "demo" / "state.json").exists():
        raise DemoRuntimeError(f"Demo profile missing: {target / 'profiles' / 'demo' / 'state.json'}")
    if not (target / "market_data").exists():
        raise DemoRuntimeError(f"Demo market data missing: {target / 'market_data'}")
    return target


def create_app(
    project_root: Path,
    share_token: str = "",
    refresh_on_start: bool = False,
    runtime_root: Path | None = None,
    demo_mode: bool = False,
) -> Flask:
    project_root = Path(project_root)
    data_root = validate_demo_runtime(project_root, runtime_root) if demo_mode else project_root / "data"
    profiles = DEMO_PROFILE if demo_mode else PROFILES
    default_profile = "demo" if demo_mode else DEFAULT_PROFILE
    app = Flask(
        __name__,
        template_folder=str(project_root / "src" / "templates"),
        static_folder=str(project_root / "src" / "static"),
    )
    app.config["DEMO_MODE"] = demo_mode
    app.config["PROJECT_ROOT"] = str(project_root.resolve())
    app.config["DATA_ROOT"] = str(data_root.resolve())
    app.config["RUNTIME_ROOT"] = str(data_root)
    app.config["APP_MODE"] = "demo" if demo_mode else "normal"
    if not demo_mode:
        ensure_profile_files(project_root)
    central_db_path = data_root / "market_data"
    quote_cache_path = data_root / "quotes_cache.json"
    ensure_central_db(central_db_path)
    if not demo_mode:
        migrate_legacy_central_db(project_root / "data" / "central.sqlite", central_db_path)
        seed_central_from_profiles(project_root, central_db_path)
        rebuild_health_summary(central_db_path)
    refresh_log_path = data_root / "refresh_log.json"

    @app.before_request
    def block_demo_writes():
        if demo_mode and request.method != "GET":
            return jsonify({"ok": False, "error": "Demo mode is read-only and uses synthetic data."}), 403
        return None

    @app.before_request
    def require_share_token():
        if not share_token:
            return None
        if request.endpoint in {"static", "health"}:
            return None
        token = request.args.get("token") or request.headers.get("X-Share-Token")
        if token == share_token:
            return None
        abort(401)

    def current_dashboard(
        profile_slug: str,
        force: bool = False,
        source: str = "api",
        force_symbols: list[str] | None = None,
    ) -> dict:
        profile = profile_info(profile_slug, profiles=profiles)
        state_path = profile_state_path(project_root, profile_slug, data_root=data_root, profiles=profiles)
        loaded_state = load_state(state_path)
        changed = ensure_transaction_ids(loaded_state)
        split_actions = list_corporate_actions(central_db_path)
        if split_actions and loaded_state.get("transactions"):
            rebuild_holdings_from_transactions(loaded_state, split_actions)
            changed = True
        if changed:
            save_state(state_path, loaded_state)
        raw_state = public_state_copy(loaded_state)
        seed_instruments_from_state(central_db_path, raw_state)
        raw_state["holdings"] = enrich_items_with_instruments(central_db_path, raw_state.get("holdings", []))
        raw_state["watchlist"] = enrich_items_with_instruments(central_db_path, raw_state.get("watchlist", []))
        refresh_seconds = raw_state.get("settings", {}).get("refresh_seconds", 900)
        manual_started_at = datetime.now().astimezone().isoformat(timespec="seconds") if force else ""
        if demo_mode:
            quotes = load_quote_cache(quote_cache_path)
            refresh_summary = {
                "demo_mode": True,
                "source": "demo_runtime/quotes_cache.json",
                "requested_symbols": [],
                "skipped_symbols": list(symbols_for_state(raw_state)),
                "forced_symbols": [],
            }
            intraday_written = 0
        else:
            service = QuoteService(quote_cache_path, refresh_seconds=refresh_seconds)
            quotes = service.get_quotes(
                symbols_for_state(raw_state),
                force=force,
                force_symbols=force_symbols,
            )
            refresh_summary = service.refresh_summary
            intraday_written = upsert_ohlcv_intraday_15m(central_db_path, service.intraday_15m_rows)
        profile_items = raw_state.get("holdings", []) + raw_state.get("watchlist", [])
        quotes = apply_daily_quote_fallbacks(
            central_db_path,
            quotes,
            [item.get("ticker", "") for item in profile_items],
            force_tickers=[
                item.get("ticker", "")
                for item in profile_items
                if not refresh_allowed_for_symbol(item.get("symbol", ""))
            ],
        )
        quotes = apply_price_overrides(quotes, raw_state.get("price_overrides"))
        holdings = attach_after_close_quotes(
            central_db_path,
            attach_quotes_to_items(raw_state.get("holdings", []), quotes),
        )
        holdings = attach_sparklines(central_db_path, holdings)
        holdings = attach_dividend_schedules(central_db_path, holdings)
        watchlist = attach_after_close_quotes(
            central_db_path,
            attach_quotes_to_items(raw_state.get("watchlist", []), quotes),
        )
        markets = market_snapshot(quotes)
        dashboard = build_dashboard_state(raw_state, holdings, watchlist, markets)
        dashboard["transaction_book"] = transaction_book_payload(raw_state.get("transactions", []))
        dashboard["updated_at"] = now_string()
        dashboard["data_status"] = data_status_payload(central_db_path)
        dashboard["refresh_policy"] = refresh_summary
        dashboard["refresh_policy"]["intraday_15m_rows_written"] = intraday_written
        dashboard["profile"] = profile
        dashboard["demo_mode"] = demo_mode
        dashboard["known_trade_items"] = trade_import_known_items(raw_state, central_db_path)
        if force and not demo_mode:
            requested = set(service.refresh_summary.get("requested_symbols", []))
            tw_requested = {symbol for symbol in requested if symbol.endswith(".TW") or symbol.endswith(".TWO")}
            us_requested = requested - tw_requested
            finished_at = datetime.now().astimezone().isoformat(timespec="seconds")
            if tw_requested:
                finish_update_status(
                    central_db_path,
                    "tw_intraday_15m",
                    "yfinance",
                    manual_started_at,
                    finished_at,
                    next_run_at=next_interval_run_at("tw").isoformat(timespec="seconds"),
                    status="success",
                    message=f"manual refresh; requested={len(tw_requested)}; source={source}",
                )
            if us_requested:
                finish_update_status(
                    central_db_path,
                    "us_intraday_15m",
                    "yfinance",
                    manual_started_at,
                    finished_at,
                    next_run_at=next_interval_run_at("us").isoformat(timespec="seconds"),
                    status="success",
                    message=f"manual refresh; requested={len(us_requested)}; source={source}",
                )
            append_refresh_log(
                refresh_log_path,
                f"{profile_slug}:{source}",
                "ok",
                refresh_log_message(service.refresh_summary),
            )
        return dashboard

    def scheduled_refresh() -> None:
        started_at = datetime.now().astimezone().isoformat(timespec="seconds")
        begin_update_status(
            central_db_path,
            "tw_intraday_15m",
            "yfinance",
            started_at,
            next_run_at=next_interval_run_at("tw").isoformat(timespec="seconds"),
            message="15m scheduler started",
        )
        begin_update_status(
            central_db_path,
            "us_intraday_15m",
            "yfinance",
            started_at,
            next_run_at=next_interval_run_at("us").isoformat(timespec="seconds"),
            message="15m scheduler started",
        )
        tracked_items = tracked_profile_items(project_root, central_db_path, profiles=profiles, data_root=data_root)
        service = QuoteService(quote_cache_path, refresh_seconds=900)
        try:
            service.get_quotes(
                [item["symbol"] for item in US_MARKETS] + [item["symbol"] for item in tracked_items],
                force=True,
            )
            requested = set(service.refresh_summary.get("requested_symbols", []))
            tw_requested = {symbol for symbol in requested if symbol.endswith(".TW") or symbol.endswith(".TWO")}
            us_requested = requested - tw_requested
            intraday_written = upsert_ohlcv_intraday_15m(central_db_path, service.intraday_15m_rows)
            snapshot_written = upsert_quote_snapshots_15m(
                central_db_path,
                quote_snapshot_rows(
                    tracked_items,
                    service.cache,
                    requested_symbols=requested,
                ),
            )
            message = (
                f"{refresh_log_message(service.refresh_summary)}; "
                f"intraday_15m_rows={intraday_written}; snapshots_15m_rows={snapshot_written}"
            )
            append_refresh_log(refresh_log_path, "schedule:15m:central", "ok", message)
            finished_at = datetime.now().astimezone().isoformat(timespec="seconds")
            finish_update_status(
                central_db_path,
                "tw_intraday_15m",
                "yfinance",
                started_at,
                finished_at,
                next_run_at=next_interval_run_at("tw").isoformat(timespec="seconds"),
                status="success",
                message=f"requested={len(tw_requested)}; snapshots_15m_rows={snapshot_written}",
            )
            finish_update_status(
                central_db_path,
                "us_intraday_15m",
                "yfinance",
                started_at,
                finished_at,
                next_run_at=next_interval_run_at("us").isoformat(timespec="seconds"),
                status="success",
                message=f"requested={len(us_requested)}",
            )
            for profile_slug in profiles:
                current_dashboard(
                    profile_slug,
                    force=False,
                    source="schedule:15m",
                )
        except Exception as exc:
            finished_at = datetime.now().astimezone().isoformat(timespec="seconds")
            message = str(exc)[:240]
            finish_update_status(
                central_db_path,
                "tw_intraday_15m",
                "yfinance",
                started_at,
                finished_at,
                next_run_at=next_interval_run_at("tw").isoformat(timespec="seconds"),
                status="failed",
                message=message,
            )
            finish_update_status(
                central_db_path,
                "us_intraday_15m",
                "yfinance",
                started_at,
                finished_at,
                next_run_at=next_interval_run_at("us").isoformat(timespec="seconds"),
                status="failed",
                message=message,
            )

    def after_close_refresh() -> None:
        started_at = datetime.now().astimezone().isoformat(timespec="seconds")
        begin_update_status(
            central_db_path,
            "tw_after_close",
            "yfinance",
            started_at,
            next_run_at=next_daily_run_at("13:31").isoformat(timespec="seconds"),
            message="after-close scheduler started",
        )
        tracked_items = tracked_profile_items(project_root, central_db_path, profiles=profiles, data_root=data_root)
        intraday_rows: list[dict[str, Any]] = []
        after_close_rows: list[dict[str, Any]] = []
        failed_symbols: list[str] = []

        for item in tracked_items:
            symbol = str(item.get("symbol", ""))
            if not symbol:
                continue
            try:
                quote, symbol_intraday_rows = fetch_symbol_bundle(symbol)
            except Exception:
                failed_symbols.append(symbol)
                continue

            intraday_rows.extend(symbol_intraday_rows)
            if quote.get("close") is None:
                continue

            captured_at = datetime.now().astimezone().replace(second=0, microsecond=0)
            trade_date = str(quote.get("price_time", ""))[:10] or captured_at.date().isoformat()
            after_close_rows.append(
                {
                    "ticker": item["ticker"],
                    "trade_date": trade_date,
                    "captured_at": captured_at.isoformat(),
                    "close": quote.get("close"),
                    "prev_close": quote.get("prev_close"),
                    "change": quote.get("change"),
                    "change_pct": quote.get("change_pct"),
                    "source": quote.get("source", "yfinance"),
                    "source_market": "YAHOO",
                    "fetched_at_ts": quote.get("fetched_at_ts", 0),
                }
            )

        intraday_written = upsert_ohlcv_intraday_15m(central_db_path, intraday_rows)
        after_close_written = upsert_after_close_quotes(central_db_path, after_close_rows)
        failed_text = ", ".join(failed_symbols) if failed_symbols else "none"
        append_refresh_log(
            refresh_log_path,
            "schedule:after-close",
            "ok" if not failed_symbols else "partial",
            (
                f"after_close_rows={after_close_written}; "
                f"intraday_15m_rows={intraday_written}; failed={failed_text}"
            ),
        )
        finish_update_status(
            central_db_path,
            "tw_after_close",
            "yfinance",
            started_at,
            datetime.now().astimezone().isoformat(timespec="seconds"),
            next_run_at=next_daily_run_at("13:31").isoformat(timespec="seconds"),
            status="success" if not failed_symbols else "failed",
            message=f"after_close_rows={after_close_written}; failed={failed_text}",
        )

    def official_daily_refresh() -> None:
        started_at = datetime.now().astimezone().isoformat(timespec="seconds")
        begin_update_status(
            central_db_path,
            "official_daily",
            "twse_tpex",
            started_at,
            next_run_at=next_daily_run_at("14:00").isoformat(timespec="seconds"),
            message="official daily sync started",
        )
        try:
            summary = sync_missing_official_daily_bars(central_db_path)
            failed = summary.get("failed", [])
            updated = summary.get("updated", [])
            no_new_rows = summary.get("no_new_rows", [])
            already_current = summary.get("already_current", [])
            failed_text = "; ".join(
                f"{item.get('ticker')}: {str(item.get('error', ''))[:80]}"
                for item in failed[:3]
            )
            message_parts = [
                f"end_date={summary.get('end_date')}",
                f"instruments={summary.get('instrument_count')}",
                f"rows_written={summary.get('rows_written')}",
                f"updated_tickers={len(updated)}",
                f"no_new_rows={len(no_new_rows)}",
                f"already_current={len(already_current)}",
                f"failed={len(failed)}",
            ]
            if failed_text:
                message_parts.append(f"failed_detail={failed_text}")
            message = "; ".join(message_parts)
            append_refresh_log(
                refresh_log_path,
                "schedule:official-daily",
                "ok" if not failed else "partial",
                message,
            )
            finish_update_status(
                central_db_path,
                "official_daily",
                "twse_tpex",
                started_at,
                datetime.now().astimezone().isoformat(timespec="seconds"),
                next_run_at=next_daily_run_at("14:00").isoformat(timespec="seconds"),
                status="success" if not failed else "failed",
                message=message,
            )
        except Exception as exc:
            finish_update_status(
                central_db_path,
                "official_daily",
                "twse_tpex",
                started_at,
                datetime.now().astimezone().isoformat(timespec="seconds"),
                next_run_at=next_daily_run_at("14:00").isoformat(timespec="seconds"),
                status="failed",
                message=str(exc)[:240],
            )

    def gmail_statement_refresh() -> None:
        started_at = datetime.now().astimezone().isoformat(timespec="seconds")
        next_run = next_daily_run_at("23:30").isoformat(timespec="seconds")
        begin_update_status(
            central_db_path,
            "gmail_statements",
            "gmail",
            started_at,
            next_run_at=next_run,
            message="Gmail statement scan started",
        )
        try:
            summary = sync_latest_pdf_attachments(
                project_root,
                central_db_path,
                profile_slug="son",
                credentials_path=project_root / "config" / "gmail_credentials.json",
                token_path=project_root / "config" / "gmail_token.json",
                query=(
                    'from:service@billu.tssco.com.tw has:attachment filename:pdf '
                    'subject:"台新證券" "交割憑單" newer_than:30d'
                ),
                max_results=100,
                all_missing=True,
            )
            message = (
                f"stored={summary['stored']}; duplicate_message={summary['duplicate_message']}; "
                f"duplicate_hash={summary['duplicate_hash']}; date_conflict={summary['date_conflict']}; "
                f"failed={summary['failed']}"
            )
            finish_update_status(
                central_db_path,
                "gmail_statements",
                "gmail",
                started_at,
                datetime.now().astimezone().isoformat(timespec="seconds"),
                next_run_at=next_run,
                status="failed" if summary["failed"] else "success",
                message=message,
            )
            append_refresh_log(
                refresh_log_path,
                "schedule:gmail-statements",
                "error" if summary["failed"] else "ok",
                message,
            )
        except Exception as exc:
            finish_update_status(
                central_db_path,
                "gmail_statements",
                "gmail",
                started_at,
                datetime.now().astimezone().isoformat(timespec="seconds"),
                next_run_at=next_run,
                status="failed",
                message=str(exc)[:240],
            )
            raise

    def official_history_backfill_tick() -> None:
        started_at = datetime.now().astimezone().isoformat(timespec="seconds")
        next_run = next_half_hour_run_at().isoformat(timespec="seconds")
        begin_update_status(
            central_db_path,
            "official_history_backfill",
            "twse_tpex",
            started_at,
            next_run_at=next_run,
            message="checking one instrument",
        )
        try:
            result = backfill_one_missing_history(central_db_path)
            append_refresh_log(
                refresh_log_path,
                "schedule:history-backfill",
                "ok" if result["ok"] else "skip",
                result["message"],
            )
            finish_update_status(
                central_db_path,
                "official_history_backfill",
                "twse_tpex",
                started_at,
                datetime.now().astimezone().isoformat(timespec="seconds"),
                next_run_at=next_run,
                status="success" if result["ok"] else "failed",
                message=result["message"][:240],
            )
        except Exception as exc:
            finish_update_status(
                central_db_path,
                "official_history_backfill",
                "twse_tpex",
                started_at,
                datetime.now().astimezone().isoformat(timespec="seconds"),
                next_run_at=next_run,
                status="failed",
                message=str(exc)[:240],
            )

    start_interval_refresh_scheduler(
        scheduled_refresh,
        refresh_log_path,
        interval_minutes=15,
        offset_minutes=1,
        name="schedule:15m:central",
    )
    start_daily_time_scheduler(
        after_close_refresh,
        refresh_log_path,
        run_times=["13:31"],
        name="schedule:after-close",
    )
    start_daily_time_scheduler(
        official_daily_refresh,
        refresh_log_path,
        run_times=["14:00"],
        name="schedule:official-daily",
    )
    start_daily_time_scheduler(
        gmail_statement_refresh,
        refresh_log_path,
        run_times=["23:30"],
        name="schedule:gmail-statements",
    )
    start_interval_refresh_scheduler(
        official_history_backfill_tick,
        refresh_log_path,
        interval_minutes=30,
        offset_minutes=7,
        name="schedule:history-backfill",
    )

    if refresh_on_start:
        try:
            now = datetime.now().astimezone()
            if now.hour >= 14:
                official_daily_refresh()
            else:
                append_refresh_log(
                    refresh_log_path,
                    "startup:official-daily",
                    "skip",
                    "skip before 14:00; official daily data is not expected yet",
                )
            for index, profile_slug in enumerate(profiles):
                current_dashboard(
                    profile_slug,
                    force=index == 0,
                    source="startup",
                )
        except Exception as exc:
            append_refresh_log(refresh_log_path, "startup", "error", str(exc))

    @app.get("/")
    def index():
        return redirect(url_for("profile_index", profile_slug=default_profile))

    @app.get("/p/<profile_slug>")
    def legacy_profile_index(profile_slug: str):
        profile_info(profile_slug, profiles=profiles)
        return redirect(url_for("profile_index", profile_slug=profile_slug))

    @app.get("/database")
    def database_index():
        return render_template("database.html", profiles=profile_links(profiles))

    @app.get("/database/dividends")
    def database_dividends_index():
        return render_template("dividends.html", profiles=profile_links(profiles))

    @app.get("/database/logs")
    def database_logs_index():
        return render_template("logs.html", profiles=profile_links(profiles))

    @app.get("/database/uploads")
    def database_uploads_index():
        return render_template("uploads.html", profiles=profile_links(profiles))

    @app.get("/api/market-data-status")
    def api_market_data_status():
        return jsonify(
            market_data_status_payload(
                data_root=data_root,
                central_db_path=central_db_path,
                quote_cache_path=quote_cache_path,
                refresh_log_path=refresh_log_path,
                demo_mode=demo_mode,
            )
        )

    @app.get("/api/database")
    def api_database():
        return jsonify(
            database_payload(
                central_db_path,
                quote_cache_path,
                limit=request.args.get("limit"),
                offset=request.args.get("offset"),
                q=request.args.get("q", ""),
                asset_type=request.args.get("type", ""),
                market=request.args.get("market", ""),
                exchange_suffix=request.args.get("suffix", ""),
                history_status=request.args.get("history_status", ""),
            )
        )

    @app.get("/api/database/logs")
    def api_database_logs():
        try:
            limit = int(request.args.get("limit") or 80)
            offset = int(request.args.get("offset") or 0)
        except ValueError:
            return jsonify({"ok": False, "error": "limit/offset must be numbers"}), 400
        payload = list_operation_logs(
            central_db_path,
            limit=limit,
            offset=offset,
            status=str(request.args.get("status") or "").strip(),
            job_name=str(request.args.get("job_name") or "").strip(),
        )
        return jsonify(
            {
                "ok": True,
                "updated_at": now_string(),
                "data_status": data_status_payload(central_db_path),
                **payload,
            }
        )

    @app.get("/api/database/uploads")
    def api_database_uploads():
        try:
            limit = int(request.args.get("limit") or 80)
            offset = int(request.args.get("offset") or 0)
        except ValueError:
            return jsonify({"ok": False, "error": "limit/offset must be numbers"}), 400
        payload = list_uploaded_documents(
            central_db_path,
            limit=limit,
            offset=offset,
            profile_slug=str(request.args.get("profile") or "").strip(),
            status=str(request.args.get("status") or "").strip(),
        )
        return jsonify(
            {
                "ok": True,
                "updated_at": now_string(),
                "data_status": data_status_payload(central_db_path),
                **payload,
            }
        )

    @app.post("/api/database/uploads")
    def api_database_upload():
        profile_slug = str(request.form.get("profile") or default_profile).strip()
        if profile_slug not in profiles:
            return jsonify({"ok": False, "error": "unknown profile"}), 400
        return handle_upload_document(profile_slug)

    @app.post("/api/database/uploads-base64")
    def api_database_upload_base64():
        payload = request.get_json(silent=True) or {}
        profile_slug = str(payload.get("profile") or default_profile).strip()
        if profile_slug not in profiles:
            return jsonify({"ok": False, "error": "unknown profile"}), 400
        return handle_upload_document_base64(profile_slug, payload)

    @app.get("/api/database/uploads/<int:upload_id>/file")
    def api_database_upload_file(upload_id: int):
        document = get_uploaded_document(central_db_path, upload_id)
        if not document:
            abort(404)
        path = safe_uploaded_document_path(project_root, document)
        if not path.exists():
            abort(404)
        return send_file(
            path,
            mimetype=document.get("mime_type") or mimetypes.guess_type(path.name)[0],
            as_attachment=False,
            download_name=document.get("original_filename") or path.name,
        )

    @app.patch("/api/database/uploads/<int:upload_id>")
    def api_database_upload_status(upload_id: int):
        payload = request.get_json(silent=True) or {}
        try:
            document = update_uploaded_document_status(
                central_db_path,
                upload_id,
                status=str(payload.get("status") or "stored"),
                note=str(payload.get("note") or ""),
            )
        except ValueError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 404
        return jsonify({"ok": True, "document": document})

    @app.get("/api/database/dividends")
    def api_database_dividends():
        raw_tickers = str(request.args.get("ticker") or "").strip().upper()
        targets = list_dividend_targets(central_db_path)
        tickers = parse_dividend_tickers(raw_tickers) if raw_tickers else [
            str(target.get("ticker") or "").strip().upper()
            for target in targets
            if target.get("ticker")
        ]
        if not tickers:
            tickers = ["00900", "0056", "00918", "00919"]
            for ticker in tickers:
                try:
                    set_dividend_target(central_db_path, ticker=ticker, asset_type="ETF", source="seed")
                except ValueError:
                    pass
            targets = list_dividend_targets(central_db_path)
        current_year = date.today().year
        try:
            start_year = int(request.args.get("start_year") or 2005)
            end_year = int(request.args.get("end_year") or current_year + 1)
        except ValueError:
            return jsonify({"ok": False, "error": "start_year/end_year must be numbers"}), 400
        if end_year < start_year:
            return jsonify({"ok": False, "error": "end_year must be on or after start_year"}), 400

        all_rows: list[dict[str, Any]] = []
        sources: set[str] = set()
        source_urls: list[str] = []
        errors: list[dict[str, str]] = []
        try:
            for ticker in tickers:
                rows = list_etf_dividends(central_db_path, ticker, start_year, end_year)
                if rows:
                    sources.add("本機股利資料庫")
                for row in rows:
                    if row.get("source_url"):
                        source_urls.append(str(row["source_url"]))
                all_rows.extend(rows)
        except Exception as exc:
            return jsonify({"ok": False, "error": str(exc)[:240]}), 502

        rows = sorted(
            all_rows,
            key=lambda row: (str(row.get("ticker") or ""), str(row.get("ex_dividend_date") or "")),
            reverse=True,
        )
        validation = {"mismatch_count": 0, "mismatch_keys": [], "mismatches": []}
        rows = dedupe_dividend_rows(rows)
        latest = max(rows, key=lambda row: str(row.get("ex_dividend_date") or ""), default=None)
        return jsonify(
            {
                "ok": True,
                "updated_at": now_string(),
                "ticker": ",".join(tickers),
                "source": " / ".join(sorted(sources)) if sources else "本機股利標的清單",
                "source_url": source_urls[0] if len(set(source_urls)) == 1 else "",
                "errors": errors,
                "targets": targets,
                "summary": {
                    "record_count": len(rows),
                    "ticker_count": len(set(tickers)),
                    "latest_ex_dividend_date": latest.get("ex_dividend_date") if latest else None,
                    "latest_payout_date": latest.get("payout_date") if latest else None,
                    "latest_dividend": latest.get("dividend") if latest else None,
                },
                "records": rows,
                "validation": validation,
                "data_status": data_status_payload(central_db_path),
            }
        )

    @app.post("/api/database/dividends/target")
    def api_database_dividend_target():
        payload = request.get_json(silent=True) or {}
        try:
            target = set_dividend_target(
                central_db_path,
                ticker=payload.get("ticker", ""),
                name=payload.get("name", ""),
                asset_type=payload.get("type", "ETF"),
                exchange_suffix=payload.get("exchange_suffix", ".TW"),
                source="manual",
            )
        except ValueError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400
        return jsonify(
            {
                "ok": True,
                "target": target,
                "targets": list_dividend_targets(central_db_path),
                "message": "已新增股利標的。尚未抓取 API，請按該標的更新。",
            }
        )

    @app.post("/api/database/dividends/refresh-all")
    def api_database_dividend_refresh_all():
        targets = list_dividend_targets(central_db_path)
        results: list[dict[str, Any]] = []
        for target in targets:
            ticker = str(target.get("ticker") or "").strip().upper()
            if not ticker:
                continue
            result, _ = refresh_dividend_from_yahoo(central_db_path, ticker)
            results.append(result)
        failed = [row for row in results if not row.get("ok")]
        return jsonify(
            {
                "ok": not failed,
                "source": "Yahoo 歷史股利",
                "updated_at": now_string(),
                "total": len(results),
                "success_count": len(results) - len(failed),
                "fail_count": len(failed),
                "results": results,
                "message": f"Yahoo 一鍵更新完成：成功 {len(results) - len(failed)} 檔，失敗 {len(failed)} 檔",
            }
        )

    @app.post("/api/database/dividends/<ticker>/refresh")
    def api_database_dividend_refresh(ticker: str):
        ticker = str(ticker or "").strip().upper()
        if not ticker:
            return jsonify({"ok": False, "error": "ticker is required"}), 400
        result, status_code = refresh_dividend_from_yahoo(central_db_path, ticker)
        return jsonify(result), status_code

    def refresh_dividend_from_yahoo(path: Path, ticker: str) -> tuple[dict[str, Any], int]:
        ticker = str(ticker or "").strip().upper()
        try:
            set_dividend_target(path, ticker=ticker, asset_type="ETF", source="manual")
        except ValueError:
            pass
        started_at = now_string()
        try:
            yahoo_records = fetch_yahoo_stock_dividends(ticker)
            rows = [record.as_dict() for record in yahoo_records]
            written = upsert_etf_dividends(path, rows)
            finished_at = now_string()
            status = "success" if rows else "failed"
            message = f"Yahoo fetched {len(rows)}, wrote {written}" if rows else "Yahoo 未回傳股利資料"
            record_dividend_refresh_status(
                path,
                ticker=ticker,
                source="Yahoo 歷史股利",
                started_at=started_at,
                finished_at=finished_at,
                status=status,
                fetched_count=len(rows),
                written_count=written,
                message=message,
            )
            validation = {"mismatch_count": 0, "mismatch_keys": [], "mismatches": []}
        except Exception as exc:
            finished_at = now_string()
            error = str(exc)[:240]
            record_dividend_refresh_status(
                path,
                ticker=ticker,
                source="Yahoo 歷史股利",
                started_at=started_at,
                finished_at=finished_at,
                status="failed",
                fetched_count=0,
                written_count=0,
                message=error,
            )
            return {"ok": False, "ticker": ticker, "source": "Yahoo 歷史股利", "error": error}, 502
        return (
            {
                "ok": status == "success",
                "ticker": ticker,
                "mode": "yahoo_only",
                "source": "Yahoo 歷史股利",
                "fetched": len(rows),
                "written": written,
                "validation": validation,
                "last_finished_at": finished_at,
                "message": message,
            },
            200 if rows else 502,
        )

    @app.post("/api/database/instrument")
    def api_database_instrument():
        payload = request.get_json(silent=True) or {}
        ticker = str(payload.get("ticker") or "").strip().upper()
        if not ticker:
            return jsonify({"ok": False, "error": "ticker is required"}), 400
        existing = get_instrument(central_db_path, ticker)
        if existing:
            return jsonify(
                {
                    "ok": True,
                    "duplicate": True,
                    "instrument": existing,
                    "message": f"{ticker} 已存在，未重複新增。",
                    "database": database_payload(central_db_path, quote_cache_path),
                }
            )
        try:
            instrument = set_instrument(
                central_db_path,
                ticker=ticker,
                name=payload.get("name", ""),
                asset_type=payload.get("type", ""),
                exchange_suffix=payload.get("exchange_suffix", ".TW"),
                source="manual",
            )
        except ValueError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400
        return jsonify(
            {
                "ok": True,
                "duplicate": False,
                "instrument": instrument,
                "message": f"{instrument.get('ticker') or ticker} 已加入中央股票主檔。",
                "database": database_payload(central_db_path, quote_cache_path),
            }
        )

    @app.get("/database/<ticker>/history")
    def database_history_index(ticker: str):
        instrument = get_instrument(central_db_path, ticker)
        if instrument is None:
            abort(404)
        return render_template("history.html", instrument=instrument)

    @app.get("/api/database/<ticker>/history")
    def api_database_history(ticker: str):
        instrument = get_instrument(central_db_path, ticker)
        if instrument is None:
            abort(404)
        rows = list_ohlcv_daily(
            central_db_path,
            ticker,
            start_date=request.args.get("start"),
            end_date=request.args.get("end"),
        )
        return jsonify(
            {
                "updated_at": now_string(),
                "instrument": instrument,
                "rows": rows,
                "summary": {
                    "row_count": len(rows),
                    "first_date": rows[-1]["trade_date"] if rows else None,
                    "last_date": rows[0]["trade_date"] if rows else None,
                },
            }
        )

    @app.get("/api/database/<ticker>/etf-holdings")
    def api_database_etf_holdings(ticker: str):
        return jsonify(
            etf_holdings_payload(
                central_db_path,
                ticker,
                as_of=request.args.get("as_of", "latest"),
            )
        )

    @app.post("/api/database/etf-holdings/import-csv")
    def api_database_etf_holdings_import_csv():
        payload = request.get_json(silent=True) or {}
        result, status_code = import_etf_holdings_csv_payload(central_db_path, payload)
        return jsonify(result), status_code

    @app.post("/api/database/etf-holdings/fetch-provider")
    def api_database_etf_holdings_fetch_provider():
        payload = request.get_json(silent=True) or {}
        result, status_code = fetch_etf_holdings_provider_payload(project_root, central_db_path, payload)
        return jsonify(result), status_code

    @app.post("/api/database/<ticker>/history/check")
    def api_database_history_check(ticker: str):
        instrument = get_instrument(central_db_path, ticker)
        if instrument is None:
            abort(404)
        started_at = now_string()
        result = backfill_history_for_instrument(central_db_path, instrument)
        finished_at = now_string()
        record_operation_log(
            central_db_path,
            job_name=f"manual_history_check:{str(ticker).strip().upper()}",
            source="manual",
            event_type="history_check",
            status="success" if result.get("ok") else "failed",
            started_at=started_at,
            finished_at=finished_at,
            summary=result.get("message", ""),
            details=result.get("message", ""),
        )
        return jsonify(
            {
                "ok": result["ok"],
                "ticker": str(ticker).strip().upper(),
                "message": result["message"],
                "database": database_payload(central_db_path, quote_cache_path),
            }
        )

    @app.post("/api/database/<ticker>/delisted")
    def api_database_mark_delisted(ticker: str):
        instrument = get_instrument(central_db_path, ticker)
        if instrument is None:
            abort(404)
        started_at = now_string()
        update_instrument_history_status(central_db_path, ticker, "delisted")
        rebuild_health_summary(central_db_path)
        finished_at = now_string()
        record_operation_log(
            central_db_path,
            job_name=f"manual_mark_delisted:{str(ticker).strip().upper()}",
            source="manual",
            event_type="instrument_status",
            status="success",
            started_at=started_at,
            finished_at=finished_at,
            summary=f"{str(ticker).strip().upper()} marked as delisted",
        )
        return jsonify(
            {
                "ok": True,
                "ticker": str(ticker).strip().upper(),
                "message": f"{str(ticker).strip().upper()} marked as delisted",
                "database": database_payload(central_db_path, quote_cache_path),
            }
        )

    @app.post("/api/database/<ticker>/listing-date")
    def api_database_listing_date(ticker: str):
        instrument = get_instrument(central_db_path, ticker)
        if instrument is None:
            abort(404)
        payload = request.get_json(silent=True) or {}
        listing_date = str(payload.get("listing_date") or "").strip()
        try:
            parse_iso_date(listing_date)
        except (TypeError, ValueError):
            return jsonify({"ok": False, "error": "listing_date must be YYYY-MM-DD"}), 400
        started_at = now_string()
        update_instrument_listing_date(central_db_path, ticker, listing_date)
        rebuild_health_summary(central_db_path)
        finished_at = now_string()
        record_operation_log(
            central_db_path,
            job_name=f"manual_listing_date:{str(ticker).strip().upper()}",
            source="manual",
            event_type="instrument_master",
            status="success",
            started_at=started_at,
            finished_at=finished_at,
            summary=f"{str(ticker).strip().upper()} listing_date={listing_date}",
        )
        return jsonify(
            {
                "ok": True,
                "ticker": str(ticker).strip().upper(),
                "listing_date": listing_date,
                "message": f"{str(ticker).strip().upper()} 已更新上市/掛牌日 {listing_date}",
                "database": database_payload(central_db_path, quote_cache_path),
            }
        )

    @app.post("/api/database/<ticker>/split")
    def api_database_split(ticker: str):
        instrument = get_instrument(central_db_path, ticker)
        if instrument is None:
            abort(404)
        payload = request.get_json(silent=True) or {}
        effective_date = str(payload.get("effective_date") or "").strip()
        try:
            parse_iso_date(effective_date)
        except (TypeError, ValueError):
            return jsonify({"ok": False, "error": "effective_date must be YYYY-MM-DD"}), 400
        ratio_from = as_float(payload.get("ratio_from"), 0) or 0
        ratio_to = as_float(payload.get("ratio_to"), 0) or 0
        if ratio_from <= 0 or ratio_to <= 0:
            return jsonify({"ok": False, "error": "ratio_from and ratio_to must be greater than 0"}), 400
        note = str(payload.get("note") or "").strip()
        started_at = now_string()
        action = add_split_action(
            central_db_path,
            ticker=ticker,
            effective_date=effective_date,
            ratio_from=ratio_from,
            ratio_to=ratio_to,
            note=note,
            source="manual",
        )
        split_actions = list_corporate_actions(central_db_path)
        for slug in profiles:
            state_path = profile_state_path(project_root, slug, data_root=data_root, profiles=profiles)
            state = load_state(state_path)
            rebuild_holdings_from_transactions(state, split_actions)
            save_state(state_path, state)
        rebuild_health_summary(central_db_path)
        normalized = str(ticker).strip().upper()
        finished_at = now_string()
        record_operation_log(
            central_db_path,
            job_name=f"manual_split:{normalized}",
            source="manual",
            event_type="corporate_action",
            status="success",
            started_at=started_at,
            finished_at=finished_at,
            summary=f"{normalized} split {effective_date} {ratio_from:g}:{ratio_to:g}",
            details=json.dumps(action, ensure_ascii=False),
        )
        return jsonify(
            {
                "ok": True,
                "ticker": normalized,
                "action": action,
                "message": f"{normalized} 已新增分割 {effective_date} {ratio_from:g}:{ratio_to:g}",
                "database": database_payload(central_db_path, quote_cache_path),
            }
        )

    @app.post("/api/database/<ticker>/history/refresh")
    def api_database_history_refresh(ticker: str):
        instrument = get_instrument(central_db_path, ticker)
        if instrument is None:
            abort(404)

        ticker = str(ticker or "").strip().upper()
        started_at = now_string()
        today = date.today()
        stats = ohlcv_daily_stats(central_db_path, ticker)
        bar_count = as_float(stats.get("bar_count"), 0) or 0
        last_date_text = str(stats.get("last_date") or "")
        if bar_count < 1000 or not last_date_text:
            start_date = today - timedelta(days=(365 * 5 + 30))
            mode = "backfill_5y"
        else:
            start_date = parse_iso_date(last_date_text) + timedelta(days=1)
            mode = "catch_up"
        if start_date > today:
            finished_at = now_string()
            record_operation_log(
                central_db_path,
                job_name=f"manual_history_refresh:{ticker}",
                source="manual",
                event_type="history_refresh",
                status="success",
                started_at=started_at,
                finished_at=finished_at,
                summary=f"{ticker} already current",
            )
            return jsonify(
                {
                    "ok": True,
                    "ticker": ticker,
                    "mode": "already_current",
                    "message": "日線已是最新資料。",
                    "database": database_payload(central_db_path, quote_cache_path),
                }
            )

        primary_suffix = str(instrument.get("exchange_suffix") or ".TW").upper()
        attempts: list[dict[str, Any]] = []
        rows: list[dict[str, Any]] = []
        used_suffix = primary_suffix
        used_source = "TPEX" if primary_suffix == ".TWO" else "TWSE"

        for suffix in ([primary_suffix, ".TWO"] if primary_suffix == ".TW" else [primary_suffix, ".TW"]):
            source = "TPEX" if suffix == ".TWO" else "TWSE"
            fetched, errors = fetch_official_daily_resilient(ticker, suffix, start_date, today, pause_seconds=0.12)
            attempts.append(
                {
                    "source": source,
                    "suffix": suffix,
                    "rows": len(fetched),
                    "error": "; ".join(errors[:3]),
                    "error_count": len(errors),
                }
            )
            if fetched:
                rows = fetched
                used_suffix = suffix
                used_source = source
                break

        written = upsert_ohlcv_daily(central_db_path, rows)
        rebuild_health_summary(central_db_path)
        if rows and used_suffix != primary_suffix:
            set_instrument(
                central_db_path,
                ticker=ticker,
                name=instrument.get("name", ""),
                asset_type=instrument.get("type", ""),
                exchange_suffix=used_suffix,
                source="official_detected",
            )

        refreshed_stats = ohlcv_daily_stats(central_db_path, ticker)
        no_data_message = (
            "官方 API 查無日線資料；若此股已下市，之後可手動標記已下市。"
            if not rows
            else f"{used_source} 已更新日線 {written} 筆。"
        )
        finished_at = now_string()
        record_operation_log(
            central_db_path,
            job_name=f"manual_history_refresh:{ticker}",
            source=used_source if rows else "official",
            event_type="history_refresh",
            status="success" if rows else "failed",
            started_at=started_at,
            finished_at=finished_at,
            summary=f"{ticker} fetched={len(rows)} written={written}",
            details=json.dumps(attempts, ensure_ascii=False),
        )
        return jsonify(
            {
                "ok": True,
                "ticker": ticker,
                "mode": mode,
                "source": used_source if rows else "",
                "start_date": start_date.isoformat(),
                "end_date": today.isoformat(),
                "fetched": len(rows),
                "written": written,
                "attempts": attempts,
                "stats": refreshed_stats,
                "message": no_data_message,
                "database": database_payload(central_db_path, quote_cache_path),
            }
        )

    @app.get("/<profile_slug>")
    def profile_index(profile_slug: str):
        profile = profile_info(profile_slug, profiles=profiles)
        return render_template("dashboard.html", profile=profile)

    @app.get("/<profile_slug>/stocks")
    def profile_stock_details(profile_slug: str):
        profile = profile_info(profile_slug, profiles=profiles)
        return render_template("stock_detail.html", profile=profile)

    @app.get("/<profile_slug>/api/state")
    def api_state(profile_slug: str):
        return jsonify(current_dashboard(profile_slug, force=False))

    @app.post("/<profile_slug>/api/refresh")
    def api_refresh(profile_slug: str):
        return jsonify(current_dashboard(profile_slug, force=True, source="manual-button"))

    @app.post("/<profile_slug>/api/cash")
    def api_cash(profile_slug: str):
        state_path = profile_state_path(project_root, profile_slug, data_root=data_root, profiles=profiles)
        payload = request.get_json(silent=True) or {}
        try:
            result = record_cash_deposit_from_payload(state_path, payload)
        except ValueError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400

        dashboard = current_dashboard(profile_slug, force=False)
        dashboard["cash_result"] = result
        return jsonify(dashboard)

    @app.post("/<profile_slug>/api/dividend-income")
    def api_dividend_income(profile_slug: str):
        state_path = profile_state_path(project_root, profile_slug, data_root=data_root, profiles=profiles)
        payload = request.get_json(silent=True) or {}
        try:
            result = record_dividend_income_from_payload(state_path, payload)
        except ValueError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400

        dashboard = current_dashboard(profile_slug, force=False)
        dashboard["dividend_income_result"] = result
        return jsonify(dashboard)

    @app.post("/<profile_slug>/api/uploads")
    def api_profile_upload(profile_slug: str):
        profile_info(profile_slug, profiles=profiles)
        return handle_upload_document(profile_slug)

    @app.post("/<profile_slug>/api/uploads-base64")
    def api_profile_upload_base64(profile_slug: str):
        profile_info(profile_slug, profiles=profiles)
        payload = request.get_json(silent=True) or {}
        return handle_upload_document_base64(profile_slug, payload)

    @app.post("/<profile_slug>/api/import-staging")
    def api_create_import_staging(profile_slug: str):
        profile_info(profile_slug, profiles=profiles)
        if not request.is_json:
            return jsonify({"ok": False, "error": "Import staging requires a JSON payload."}), 400
        payload = request.get_json(silent=True)
        if payload is None:
            return jsonify({"ok": False, "error": "Invalid JSON payload."}), 400
        state_path = profile_state_path(project_root, profile_slug, data_root=data_root, profiles=profiles)
        existing_transactions = load_state(state_path).get("transactions", [])
        try:
            batch = create_import_staging_batch(
                data_root / "imports" / "staging",
                profile=profile_slug,
                payload=payload,
                existing_transactions=existing_transactions if isinstance(existing_transactions, list) else [],
            )
        except ValueError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400
        return jsonify(
            {
                "ok": True,
                "batch": summarize_import_staging_batch(batch),
                "rows": batch.get("rows", []),
            }
        ), 201

    @app.get("/<profile_slug>/api/import-staging")
    def api_list_import_staging(profile_slug: str):
        profile_info(profile_slug, profiles=profiles)
        batches = list_import_staging_batches(data_root / "imports" / "staging", profile=profile_slug)
        return jsonify({"ok": True, "batches": batches})

    @app.get("/<profile_slug>/api/import-staging/<batch_id>")
    def api_get_import_staging(profile_slug: str, batch_id: str):
        profile_info(profile_slug, profiles=profiles)
        try:
            batch = load_import_staging_batch(
                data_root / "imports" / "staging",
                profile=profile_slug,
                batch_id=batch_id,
            )
        except ValueError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400
        except FileNotFoundError:
            return jsonify({"ok": False, "error": "Import staging batch not found."}), 404
        return jsonify({"ok": True, "batch": batch})

    @app.post("/<profile_slug>/api/transaction")
    def api_transaction(profile_slug: str):
        state_path = profile_state_path(project_root, profile_slug, data_root=data_root, profiles=profiles)
        payload = request.get_json(silent=True) or {}
        try:
            result = record_transaction_from_payload(state_path, payload, central_db_path=central_db_path)
        except ValueError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400

        force_symbol = result.get("symbol")
        dashboard = current_dashboard(
            profile_slug,
            force=True,
            source=f"transaction:{result.get('ticker', '')}",
            force_symbols=[force_symbol] if force_symbol else None,
        )
        dashboard["transaction_result"] = result
        return jsonify(dashboard)

    @app.patch("/<profile_slug>/api/transactions/<transaction_id>")
    def api_update_transaction(profile_slug: str, transaction_id: str):
        state_path = profile_state_path(project_root, profile_slug, data_root=data_root, profiles=profiles)
        payload = request.get_json(silent=True) or {}
        try:
            result = update_transaction_from_payload(state_path, transaction_id, payload, central_db_path=central_db_path)
        except ValueError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400

        dashboard = current_dashboard(profile_slug, force=True, source=f"transaction-edit:{result.get('ticker', '')}")
        dashboard["transaction_edit_result"] = result
        return jsonify(dashboard)

    @app.delete("/<profile_slug>/api/transactions/<transaction_id>")
    def api_delete_transaction(profile_slug: str, transaction_id: str):
        state_path = profile_state_path(project_root, profile_slug, data_root=data_root, profiles=profiles)
        try:
            result = delete_transaction_from_payload(state_path, transaction_id, central_db_path=central_db_path)
        except ValueError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400

        dashboard = current_dashboard(profile_slug, force=True, source=f"transaction-delete:{result.get('ticker', '')}")
        dashboard["transaction_delete_result"] = result
        return jsonify(dashboard)

    @app.post("/<profile_slug>/api/import/extract")
    def api_import_extract(profile_slug: str):
        profile_info(profile_slug, profiles=profiles)
        started_at = now_string()
        upload = request.files.get("file")
        if upload is None or not upload.filename:
            return jsonify({"ok": False, "error": "missing file"}), 400
        filename = str(upload.filename or "")
        content_type = str(upload.content_type or "").lower()
        password = str(request.form.get("password") or "")
        payload = upload.read()
        if not payload:
            return jsonify({"ok": False, "error": "empty file"}), 400
        if filename.lower().endswith(".pdf") or content_type == "application/pdf":
            try:
                result = extract_pdf_text(payload, password=password)
            except ValueError as exc:
                record_operation_log(
                    central_db_path,
                    job_name="pdf_import_extract",
                    source="browser_upload",
                    event_type="import_extract",
                    status="failed",
                    started_at=started_at,
                    finished_at=now_string(),
                    summary=f"{filename} value_error",
                    details=str(exc),
                )
                return jsonify({"ok": False, "error": str(exc)}), 400
            except Exception as exc:
                record_operation_log(
                    central_db_path,
                    job_name="pdf_import_extract",
                    source="browser_upload",
                    event_type="import_extract",
                    status="failed",
                    started_at=started_at,
                    finished_at=now_string(),
                    summary=f"{filename} extract_error",
                    details=str(exc),
                )
                return jsonify({"ok": False, "error": f"PDF extract failed: {str(exc)[:180]}"}), 422
            record_operation_log(
                central_db_path,
                job_name="pdf_import_extract",
                source="browser_upload",
                event_type="import_extract",
                status="success",
                started_at=started_at,
                finished_at=now_string(),
                summary=f"{filename} pages={result.get('page_count')} chars={result.get('char_count')}",
            )
            return jsonify({"ok": True, "kind": "pdf", **result})
        if content_type.startswith("image/"):
            return jsonify(
                {
                    "ok": False,
                    "kind": "image",
                    "error": "本機尚未安裝 OCR 引擎。圖片可以預覽，但請先用 Google Lens / AI 轉文字後再貼上。",
                }
            ), 422
        return jsonify({"ok": False, "error": "只支援 PDF 或圖片檔"}), 400

    @app.post("/<profile_slug>/api/import/extract-base64")
    def api_import_extract_base64(profile_slug: str):
        profile_info(profile_slug, profiles=profiles)
        started_at = now_string()
        payload = request.get_json(silent=True) or {}
        filename = str(payload.get("filename") or "upload.pdf")
        content_type = str(payload.get("content_type") or "").lower()
        password = str(payload.get("password") or "")
        encoded = str(payload.get("data") or "")
        if "," in encoded and encoded.strip().lower().startswith("data:"):
            encoded = encoded.split(",", 1)[1]
        if not encoded:
            return jsonify({"ok": False, "error": "missing base64 data"}), 400
        try:
            file_bytes = base64.b64decode(encoded, validate=True)
        except Exception:
            return jsonify({"ok": False, "error": "base64 decode failed"}), 400
        if not file_bytes:
            return jsonify({"ok": False, "error": "empty file"}), 400
        if len(file_bytes) > 25 * 1024 * 1024:
            return jsonify({"ok": False, "error": "PDF too large; max 25 MB"}), 413
        if filename.lower().endswith(".pdf") or content_type == "application/pdf":
            try:
                result = extract_pdf_text(file_bytes, password=password)
            except ValueError as exc:
                record_operation_log(
                    central_db_path,
                    job_name="pdf_import_extract_base64",
                    source="browser_base64",
                    event_type="import_extract",
                    status="failed",
                    started_at=started_at,
                    finished_at=now_string(),
                    summary=f"{filename} value_error",
                    details=str(exc),
                )
                return jsonify({"ok": False, "error": str(exc)}), 400
            except Exception as exc:
                record_operation_log(
                    central_db_path,
                    job_name="pdf_import_extract_base64",
                    source="browser_base64",
                    event_type="import_extract",
                    status="failed",
                    started_at=started_at,
                    finished_at=now_string(),
                    summary=f"{filename} extract_error",
                    details=str(exc),
                )
                return jsonify({"ok": False, "error": f"PDF extract failed: {str(exc)[:180]}"}), 422
            record_operation_log(
                central_db_path,
                job_name="pdf_import_extract_base64",
                source="browser_base64",
                event_type="import_extract",
                status="success",
                started_at=started_at,
                finished_at=now_string(),
                summary=f"{filename} pages={result.get('page_count')} chars={result.get('char_count')}",
            )
            return jsonify({"ok": True, "kind": "pdf", **result})
        return jsonify({"ok": False, "error": "只支援 PDF"}), 400

    @app.post("/<profile_slug>/api/import/extract-latest-local")
    def api_import_extract_latest_local(profile_slug: str):
        profile_info(profile_slug, profiles=profiles)
        payload = request.get_json(silent=True) or {}
        password = str(payload.get("password") or request.form.get("password") or request.args.get("password") or "")
        folder = project_root / "到現在的買賣"
        pdfs = sorted(
            [path for path in folder.glob("*.pdf") if path.is_file()],
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )
        if not pdfs:
            return jsonify({"ok": False, "error": "到現在的買賣資料夾沒有 PDF"}), 404
        path = pdfs[0]
        try:
            result = extract_pdf_text(path.read_bytes(), password=password)
        except ValueError as exc:
            return jsonify({"ok": False, "error": str(exc), "filename": path.name}), 400
        except Exception as exc:
            return jsonify({"ok": False, "error": f"PDF extract failed: {str(exc)[:180]}", "filename": path.name}), 422
        return jsonify({"ok": True, "kind": "pdf", "filename": path.name, **result})

    def handle_upload_document(profile_slug: str):
        uploaded = request.files.get("file") or request.files.get("document")
        if not uploaded or not uploaded.filename:
            return jsonify({"ok": False, "error": "請選擇 PDF 或截圖檔案"}), 400
        payload = uploaded.read()
        if not payload:
            return jsonify({"ok": False, "error": "檔案是空的"}), 400
        max_bytes = 25 * 1024 * 1024
        if len(payload) > max_bytes:
            return jsonify({"ok": False, "error": "檔案超過 25MB，請先壓縮或分批上傳"}), 400

        original = uploaded.filename
        mime_type = uploaded.mimetype or mimetypes.guess_type(original)[0] or "application/octet-stream"
        allowed_mimes = {
            "application/pdf",
            "image/png",
            "image/jpeg",
            "image/webp",
            "image/heic",
            "image/heif",
        }
        if mime_type not in allowed_mimes and not mime_type.startswith("image/"):
            return jsonify({"ok": False, "error": f"不支援的檔案類型：{mime_type}"}), 400

        digest = hashlib.sha256(payload).hexdigest()
        today = date.today()
        upload_dir = data_root / "uploads" / profile_slug / f"{today:%Y}" / f"{today:%m}"
        upload_dir.mkdir(parents=True, exist_ok=True)
        safe_name = secure_filename(original) or "upload"
        suffix = Path(safe_name).suffix.lower()
        stored_name = f"{today:%Y%m%d}_{uuid.uuid4().hex[:12]}{suffix}"
        stored_path = upload_dir / stored_name
        stored_path.write_bytes(payload)

        relative_path = str(stored_path.relative_to(project_root)).replace("\\", "/")
        document = record_uploaded_document(
            central_db_path,
            profile_slug=profile_slug,
            original_filename=original,
            stored_path=relative_path,
            mime_type=mime_type,
            file_size=len(payload),
            sha256=digest,
            source=str(request.form.get("source") or "manual_upload"),
            status="stored",
            note=str(request.form.get("note") or ""),
        )
        if document.get("duplicate"):
            try:
                stored_path.unlink(missing_ok=True)
            except OSError:
                pass

        record_operation_log(
            central_db_path,
            job_name="document_upload",
            source=profile_slug,
            event_type="upload",
            status="success",
            summary=f"{original}; {len(payload)} bytes; duplicate={bool(document.get('duplicate'))}",
            details=json.dumps(
                {
                    "profile": profile_slug,
                    "filename": original,
                    "mime_type": mime_type,
                    "size": len(payload),
                    "sha256": digest,
                    "duplicate": bool(document.get("duplicate")),
                },
                ensure_ascii=False,
            ),
        )
        return jsonify({"ok": True, "document": document})

    def handle_upload_document_base64(profile_slug: str, payload: dict[str, Any]):
        filename = str(payload.get("filename") or "upload").strip() or "upload"
        content_type = str(payload.get("content_type") or mimetypes.guess_type(filename)[0] or "application/octet-stream")
        encoded = str(payload.get("data") or "")
        if "," in encoded and encoded.strip().lower().startswith("data:"):
            encoded = encoded.split(",", 1)[1]
        if not encoded:
            return jsonify({"ok": False, "error": "missing base64 data"}), 400
        try:
            file_bytes = base64.b64decode(encoded, validate=True)
        except Exception:
            return jsonify({"ok": False, "error": "base64 decode failed"}), 400
        return store_uploaded_document_bytes(
            profile_slug,
            filename=filename,
            mime_type=content_type,
            payload=file_bytes,
            source=str(payload.get("source") or "manual_upload_base64"),
            note=str(payload.get("note") or ""),
        )

    def store_uploaded_document_bytes(
        profile_slug: str,
        *,
        filename: str,
        mime_type: str,
        payload: bytes,
        source: str,
        note: str = "",
    ):
        if not payload:
            return jsonify({"ok": False, "error": "檔案是空的"}), 400
        max_bytes = 25 * 1024 * 1024
        if len(payload) > max_bytes:
            return jsonify({"ok": False, "error": "檔案超過 25MB，請先壓縮或分批上傳"}), 400
        allowed_mimes = {
            "application/pdf",
            "image/png",
            "image/jpeg",
            "image/webp",
            "image/heic",
            "image/heif",
        }
        if mime_type not in allowed_mimes and not mime_type.startswith("image/"):
            return jsonify({"ok": False, "error": f"不支援的檔案類型：{mime_type}"}), 400

        digest = hashlib.sha256(payload).hexdigest()
        today = date.today()
        upload_dir = data_root / "uploads" / profile_slug / f"{today:%Y}" / f"{today:%m}"
        upload_dir.mkdir(parents=True, exist_ok=True)
        safe_name = secure_filename(filename) or "upload"
        suffix = Path(safe_name).suffix.lower()
        stored_name = f"{today:%Y%m%d}_{uuid.uuid4().hex[:12]}{suffix}"
        stored_path = upload_dir / stored_name
        stored_path.write_bytes(payload)

        relative_path = str(stored_path.relative_to(project_root)).replace("\\", "/")
        document = record_uploaded_document(
            central_db_path,
            profile_slug=profile_slug,
            original_filename=filename,
            stored_path=relative_path,
            mime_type=mime_type,
            file_size=len(payload),
            sha256=digest,
            source=source,
            status="stored",
            note=note,
        )
        if document.get("duplicate"):
            try:
                stored_path.unlink(missing_ok=True)
            except OSError:
                pass
        record_operation_log(
            central_db_path,
            job_name="document_upload",
            source=profile_slug,
            event_type="upload",
            status="success",
            summary=f"{filename}; {len(payload)} bytes; duplicate={bool(document.get('duplicate'))}",
            details=json.dumps(
                {
                    "profile": profile_slug,
                    "filename": filename,
                    "mime_type": mime_type,
                    "size": len(payload),
                    "sha256": digest,
                    "duplicate": bool(document.get("duplicate")),
                    "source": source,
                },
                ensure_ascii=False,
            ),
        )
        return jsonify({"ok": True, "document": document})

    def safe_uploaded_document_path(project_root: Path, document: dict[str, Any]) -> Path:
        relative = str(document.get("stored_path") or "").replace("\\", "/")
        path = (project_root / relative).resolve()
        upload_root = (data_root / "uploads").resolve()
        if upload_root not in path.parents and path != upload_root:
            abort(403)
        return path

    @app.get("/<profile_slug>/ai")
    def ai_report(profile_slug: str):
        return Response(
            render_ai_report(current_dashboard(profile_slug, force=False)),
            mimetype="text/plain; charset=utf-8",
        )

    @app.get("/api/state")
    def legacy_api_state():
        return jsonify(current_dashboard(default_profile, force=False))

    @app.post("/api/refresh")
    def legacy_api_refresh():
        return jsonify(current_dashboard(default_profile, force=True, source="manual-button"))

    @app.get("/health")
    def health():
        return {"ok": True}

    @app.get("/api/runtime-info")
    def runtime_info():
        return jsonify(
            {
                "ok": True,
                "project_root": app.config["PROJECT_ROOT"],
                "data_root": app.config["DATA_ROOT"],
                "runtime_root": app.config["DATA_ROOT"],
                "demo_mode": bool(app.config["DEMO_MODE"]),
                "app_mode": app.config["APP_MODE"],
                "available_profiles": sorted(profiles),
            }
        )

    app.jinja_env.filters["money"] = fmt_money
    app.jinja_env.filters["pct"] = fmt_pct
    return app


def ensure_profile_files(project_root: Path) -> None:
    profiles_dir = project_root / "data" / "profiles"
    profiles_dir.mkdir(parents=True, exist_ok=True)
    legacy_state_path = project_root / "data" / "state.json"

    son_path = profile_state_path(project_root, "son")
    if not son_path.exists():
        if legacy_state_path.exists():
            son_state = load_state(legacy_state_path)
        else:
            son_state = empty_profile_state("son")
        normalise_profile_state(son_state, "son")
        save_state(son_path, son_state)

    mom_path = profile_state_path(project_root, "mom")
    if not mom_path.exists():
        mom_state = empty_profile_state("mom")
        save_state(mom_path, mom_state)


def extract_pdf_text(payload: bytes, password: str = "") -> dict[str, Any]:
    from io import BytesIO

    reader = PdfReader(BytesIO(payload))
    if reader.is_encrypted:
        password_text = str(password or "")
        if not password_text:
            raise ValueError("PDF 需要密碼，請輸入密碼後再抽文字。")
        if reader.decrypt(password_text) == 0:
            raise ValueError("PDF 密碼錯誤，無法抽文字。")
    pages: list[dict[str, Any]] = []
    parts: list[str] = []
    for index, page in enumerate(reader.pages, start=1):
        text = page.extract_text() or ""
        text = normalize_extracted_statement_text(text)
        pages.append({"page": index, "chars": len(text)})
        if text:
            parts.append(text)
    full_text = "\n".join(parts).strip()
    if not full_text:
        raise ValueError("PDF 沒有可抽取文字，可能是掃描圖檔，需要 OCR。")
    return {
        "text": full_text,
        "page_count": len(reader.pages),
        "pages": pages,
        "char_count": len(full_text),
    }


def normalize_extracted_statement_text(text: str) -> str:
    lines = []
    for raw_line in str(text or "").replace("\r", "\n").split("\n"):
        line = " ".join(raw_line.split())
        if line:
            lines.append(line)
    return "\n".join(lines)


def seed_central_from_profiles(project_root: Path, central_db_path: Path) -> None:
    for profile_slug in PROFILES:
        state_path = profile_state_path(project_root, profile_slug)
        if state_path.exists():
            seed_instruments_from_state(central_db_path, load_state(state_path))


def sync_official_listing_dates(central_db_path: Path) -> None:
    try:
        twse_profiles = fetch_twse_listed_company_profiles()
    except Exception:
        return
    for item in list_instruments(central_db_path):
        if item.get("type") == "ETF" or item.get("exchange_suffix") != ".TW":
            continue
        profile = twse_profiles.get(str(item.get("ticker") or "").strip().upper())
        if not profile or not profile.get("listing_date"):
            continue
        set_instrument(
            central_db_path,
            ticker=item["ticker"],
            name=item.get("name", "") or profile.get("name", ""),
            asset_type=item.get("type", ""),
            exchange_suffix=item.get("exchange_suffix", ".TW"),
            source=item.get("source", "profile"),
            listing_date=profile["listing_date"],
        )


def tracked_profile_items(
    project_root: Path,
    central_db_path: Path,
    profiles: dict[str, str] | None = None,
    data_root: Path | None = None,
) -> list[dict[str, Any]]:
    items_by_ticker: dict[str, dict[str, Any]] = {}
    active_profiles = profiles or PROFILES
    for profile_slug in active_profiles:
        state_path = profile_state_path(project_root, profile_slug, data_root=data_root, profiles=active_profiles)
        if not state_path.exists():
            continue
        state = load_state(state_path)
        enriched = enrich_items_with_instruments(
            central_db_path,
            state.get("holdings", []) + state.get("watchlist", []),
        )
        for item in enriched:
            symbol = str(item.get("symbol", ""))
            ticker = str(item.get("ticker", "")).strip().upper()
            if ticker and (symbol.endswith(".TW") or symbol.endswith(".TWO")):
                items_by_ticker[ticker] = item
    return list(items_by_ticker.values())


def trade_import_known_items(raw_state: dict[str, Any], central_db_path: Path) -> list[dict[str, str]]:
    by_ticker: dict[str, dict[str, str]] = {}
    for item in raw_state.get("holdings", []) + raw_state.get("watchlist", []):
        ticker = str(item.get("ticker") or "").strip().upper()
        if not ticker:
            continue
        by_ticker[ticker] = {
            "ticker": ticker,
            "name": str(item.get("name") or "").strip(),
        }
    for item in list_instruments(central_db_path):
        ticker = str(item.get("ticker") or "").strip().upper()
        if not ticker or ticker in by_ticker:
            continue
        by_ticker[ticker] = {
            "ticker": ticker,
            "name": str(item.get("name") or "").strip(),
        }
    return sorted(by_ticker.values(), key=lambda item: (item["ticker"], item["name"]))


def fetch_official_daily_resilient(
    ticker: str,
    exchange_suffix: str,
    start_date: date,
    end_date: date,
    pause_seconds: float = 0.0,
) -> tuple[list[dict[str, Any]], list[str]]:
    rows: list[dict[str, Any]] = []
    errors: list[str] = []
    months = month_starts(start_date, end_date)
    for index, month_start in enumerate(months):
        try:
            month_rows = (
                fetch_tpex_month(ticker, month_start)
                if exchange_suffix == ".TWO"
                else fetch_twse_month(ticker, month_start)
            )
            rows.extend(month_rows)
        except Exception as exc:
            errors.append(f"{month_start.strftime('%Y-%m')}: {str(exc)[:90]}")
        if pause_seconds > 0 and index < len(months) - 1:
            import time

            time.sleep(pause_seconds)
    filtered = [
        row
        for row in rows
        if start_date.isoformat() <= str(row.get("trade_date", "")) <= end_date.isoformat()
    ]
    return filtered, errors


def fetch_official_month(ticker: str, exchange_suffix: str, month_start: date) -> list[dict[str, Any]]:
    return (
        fetch_tpex_month(ticker, month_start)
        if str(exchange_suffix).upper() == ".TWO"
        else fetch_twse_month(ticker, month_start)
    )


def backfill_one_missing_history(central_db_path: Path) -> dict[str, Any]:
    candidate = pick_history_backfill_candidate(central_db_path)
    if candidate is None:
        return {"ok": True, "message": "all instruments have enough daily history or are waiting for review"}
    return backfill_history_for_instrument(central_db_path, candidate)


def pick_history_backfill_candidate(central_db_path: Path) -> dict[str, Any] | None:
    candidates: list[dict[str, Any]] = []
    for item in list_instruments(central_db_path):
        item = {**item, "_central_db_path": str(central_db_path)}
        instrument_status = str(item.get("status") or "")
        history_status = str(item.get("history_status") or "")
        if instrument_status == "delisted" or history_status == "delisted":
            continue
        if int(item.get("manual_review_required") or 0) or history_status == "manual_review":
            continue
        next_retry_at = parse_datetime_or_none(item.get("next_retry_at"))
        if next_retry_at and next_retry_at > datetime.now().astimezone():
            continue
        if history_status in {"recent_missing", "broken", "symbol_problem"}:
            candidates.append(item)
            continue
        if int(item.get("daily_bar_count") or 0) <= 0:
            candidates.append(item)
            continue
        if history_status in {"partial_old_missing", "recent_ok_partial_history"}:
            candidates.append(item)
    if not candidates:
        return None
    priorities = {
        "recent_missing": 0,
        "broken": 1,
        "symbol_problem": 2,
        "partial_old_missing": 10,
        "recent_ok_partial_history": 20,
    }
    return sorted(
        candidates,
        key=lambda item: (
            priorities.get(str(item.get("history_status") or ""), 5 if int(item.get("daily_bar_count") or 0) <= 0 else 50),
            str(item.get("last_checked_at") or item.get("history_checked_at") or ""),
            str(item.get("ticker") or ""),
        ),
    )[0]


def history_is_insufficient(item: dict[str, Any], today: date) -> bool:
    return bool(missing_months_from_summary(item))


def missing_history_months(item: dict[str, Any], today: date) -> list[date]:
    return missing_months_from_summary(item)


def history_coverage_payload(central_db_path: Path, item: dict[str, Any], today: date | None = None) -> dict[str, Any]:
    today = today or date.today()
    scoped_item = {**item, "_central_db_path": str(central_db_path)}
    missing = missing_months_from_summary(scoped_item)
    target_start_text = str(scoped_item.get("expected_start_date") or "")
    return {
        "history_target_start": target_start_text,
        "missing_month_count": len(missing),
        "first_missing_month": missing[0].strftime("%Y-%m") if missing else "",
        "last_missing_month": missing[-1].strftime("%Y-%m") if missing else "",
        "history_coverage_status": "complete" if not missing else "missing_months",
    }


def reconcile_history_coverage_statuses(central_db_path: Path) -> None:
    rebuild_health_summary(central_db_path)


def history_target_start(item: dict[str, Any], today: date) -> date:
    retention_start = today - timedelta(days=365 * 5 + 30)
    listing_date = parse_date_or_none(item.get("listing_date"))
    if listing_date and listing_date > retention_start:
        return listing_date
    first_date = parse_date_or_none(item.get("daily_first_date"))
    last_date = parse_date_or_none(item.get("daily_last_date"))
    if first_date and last_date and first_date > today - timedelta(days=120) and last_date >= today - timedelta(days=7):
        return first_date
    return retention_start


def backfill_history_for_instrument(central_db_path: Path, instrument: dict[str, Any]) -> dict[str, Any]:
    ticker = str(instrument.get("ticker") or "").strip().upper()
    if not ticker:
        return {"ok": False, "message": "missing ticker"}
    if str(instrument.get("status") or "") == "delisted" or str(instrument.get("history_status") or "") == "delisted":
        return {"ok": True, "message": f"{ticker} is marked delisted; skipped"}

    today = date.today()
    stats = ohlcv_daily_stats(central_db_path, ticker)
    current_view = next(
        (
            item
            for item in list_instruments(central_db_path)
            if str(item.get("ticker") or "").strip().upper() == ticker
        ),
        instrument,
    )
    missing_months = missing_months_from_summary(current_view)
    if not missing_months:
        rebuild_health_summary(central_db_path)
        return {"ok": True, "message": f"{ticker} daily history already sufficient by health summary"}

    primary_suffix = str(instrument.get("exchange_suffix") or ".TW").upper()
    suffixes = [primary_suffix, ".TWO" if primary_suffix == ".TW" else ".TW"]
    rows: list[dict[str, Any]] = []
    used_suffix = primary_suffix
    attempts: list[str] = []
    had_request_error = False

    for month_start in missing_months[:1]:
        month_rows: list[dict[str, Any]] = []
        for suffix in suffixes:
            source = "TPEX" if suffix == ".TWO" else "TWSE"
            try:
                fetched = fetch_official_month(ticker, suffix, month_start)
            except Exception as exc:
                had_request_error = True
                attempts.append(f"{month_start:%Y-%m} {source}_error:{str(exc)[:80]}")
                continue
            attempts.append(f"{month_start:%Y-%m} {source}:{len(fetched)}")
            if fetched:
                month_rows = fetched
                used_suffix = suffix
                break
        rows.extend(month_rows)
        if rows:
            break

    if not rows:
        next_retry_at = (datetime.now().astimezone() + timedelta(hours=6)).isoformat(timespec="seconds")
        if had_request_error:
            record_market_data_problem(
                central_db_path,
                ticker,
                "broken",
                "official_no_data",
                "high",
                f"official daily fetch error; attempts={'; '.join(attempts[:4])}",
                next_retry_at=next_retry_at,
            )
            return {
                "ok": False,
                "message": f"{ticker} official daily fetch error; missing_months={len(missing_months)}; attempts={'; '.join(attempts[:4])}",
            }
        prior_retry = int(current_view.get("retry_count") or 0)
        next_status = "delisted_candidate" if prior_retry + 1 >= 3 else "recent_missing"
        record_market_data_problem(
            central_db_path,
            ticker,
            next_status,
            "official_no_data" if next_status != "delisted_candidate" else "delisted_candidate",
            "medium" if next_status == "delisted_candidate" else "high",
            f"no official daily rows; missing_months={len(missing_months)}; attempts={','.join(attempts[:6])}",
            next_retry_at=next_retry_at,
        )
        return {
            "ok": False,
            "message": f"{ticker} no official daily rows; missing_months={len(missing_months)}; attempts={','.join(attempts[:6])}; status={next_status}",
        }

    written = upsert_ohlcv_daily(central_db_path, rows)
    if used_suffix != primary_suffix:
        set_instrument(
            central_db_path,
            ticker=ticker,
            name=instrument.get("name", ""),
            asset_type=instrument.get("type", ""),
            exchange_suffix=used_suffix,
            source="official_detected",
        )
    summaries = rebuild_health_summary(central_db_path)
    refreshed_stats = ohlcv_daily_stats(central_db_path, ticker)
    status = next(
        (
            row.get("history_status", "")
            for row in summaries
            if str(row.get("instrument_id") or "").endswith(f":{ticker}")
        ),
        "",
    )
    return {
        "ok": True,
        "message": f"{ticker} daily backfill wrote {written} rows; status={status}; missing_months={len(missing_months)}; first={refreshed_stats.get('first_date')}; last={refreshed_stats.get('last_date')}",
    }


def missing_months_from_summary(item: dict[str, Any]) -> list[date]:
    raw = item.get("missing_months_json")
    months: list[str] = []
    if raw:
        try:
            parsed = json.loads(str(raw))
            if isinstance(parsed, list):
                months = [str(value) for value in parsed]
        except json.JSONDecodeError:
            months = []
    if not months and item.get("first_missing_month"):
        months = [str(item["first_missing_month"])]
    parsed_months: list[date] = []
    for month in months:
        try:
            parsed_months.append(datetime.strptime(month[:7], "%Y-%m").date().replace(day=1))
        except ValueError:
            continue
    return parsed_months


def parse_datetime_or_none(value: object) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.astimezone()
    return parsed


def parse_date_or_none(value: object) -> date | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return parse_iso_date(text)
    except ValueError:
        return None


def attach_dividend_schedules(path: Path, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    today = date.today()
    enriched: list[dict[str, Any]] = []
    for item in items:
        ticker = str(item.get("ticker", "")).strip().upper()
        if not ticker:
            enriched.append(item)
            continue
        if bool(item.get("no_dividend", False)) or str(item.get("dividend_policy", "")).strip() == "不配息":
            enriched.append(
                {
                    **item,
                    "monthly_dividend_est": 0,
                    "annual_dividend_est": 0,
                    "ex_dividend_date": "",
                    "payout_date": "",
                    "dividend_source": "manual",
                    "dividend_schedule": no_dividend_schedule_payload(),
                }
            )
            continue
        rows = list_etf_dividends(path, ticker, today.year - 3, today.year + 1)
        if not rows:
            enriched.append(item)
            continue

        rows = dedupe_dividend_rows(rows)
        schedule = dividend_schedule_payload(rows, today, as_float(item.get("shares"), 0) or 0)
        updated = {**item, "dividend_schedule": schedule}
        if schedule.get("estimated_monthly_cash") is not None:
            updated["monthly_dividend_est"] = schedule["estimated_monthly_cash"]
            updated["annual_dividend_est"] = schedule["estimated_annual_cash"]
            updated["dividend_source"] = "yahoo"
            next_event = schedule.get("next_event") or {}
            if next_event.get("is_upcoming") and next_event.get("ex_dividend_date"):
                updated["ex_dividend_date"] = next_event["ex_dividend_date"]
            else:
                updated["ex_dividend_date"] = ""
            if next_event.get("is_upcoming") and next_event.get("payout_date"):
                updated["payout_date"] = next_event["payout_date"]
            else:
                updated["payout_date"] = ""
        enriched.append(updated)
    return enriched


def no_dividend_schedule_payload() -> dict[str, Any]:
    return {
        "source": "manual",
        "record_count": 0,
        "frequency": {"type": "none", "label": "不配息", "months": [], "sample_count": 0},
        "next_event": None,
        "has_upcoming": False,
        "upcoming_events": [],
        "recent_events": [],
        "recent_per_unit_total": 0,
        "estimated_annual_cash": 0,
        "estimated_monthly_cash": 0,
    }


def dividend_schedule_payload(rows: list[dict[str, Any]], today: date, shares: float = 0) -> dict[str, Any]:
    normalized = sorted(
        [row for row in rows if row.get("ex_dividend_date") and as_float(row.get("dividend")) is not None],
        key=lambda row: str(row.get("ex_dividend_date") or ""),
    )
    upcoming = [row for row in normalized if _parse_iso_date(row.get("ex_dividend_date")) and _parse_iso_date(row.get("ex_dividend_date")) >= today]
    past_or_today = [row for row in normalized if _parse_iso_date(row.get("ex_dividend_date")) and _parse_iso_date(row.get("ex_dividend_date")) <= today]
    next_event = upcoming[0] if upcoming else (past_or_today[-1] if past_or_today else normalized[-1])
    recent_12m = [
        row for row in normalized
        if _parse_iso_date(row.get("ex_dividend_date"))
        and today - timedelta(days=366) <= _parse_iso_date(row.get("ex_dividend_date")) <= today + timedelta(days=45)
    ]
    if not recent_12m:
        recent_12m = normalized[-4:]
    per_unit_annual = sum(as_float(row.get("dividend"), 0) or 0 for row in recent_12m)
    estimated_annual_cash = per_unit_annual * shares if shares > 0 else None
    estimated_monthly_cash = estimated_annual_cash / 12 if estimated_annual_cash is not None else None
    next_event_payload = _dividend_event_payload(next_event, shares)
    frequency = dividend_frequency_payload(normalized)

    return {
        "source": "yahoo",
        "record_count": len(normalized),
        "frequency": frequency,
        "next_event": next_event_payload,
        "has_upcoming": bool(upcoming),
        "upcoming_events": [_dividend_event_payload(row, shares) for row in upcoming[:3]],
        "recent_events": [_dividend_event_payload(row, shares) for row in list(reversed(past_or_today[-4:]))],
        "recent_per_unit_total": per_unit_annual,
        "estimated_annual_cash": estimated_annual_cash,
        "estimated_monthly_cash": estimated_monthly_cash,
    }


def dividend_frequency_payload(rows: list[dict[str, Any]]) -> dict[str, Any]:
    recent = sorted(
        [row for row in rows if _parse_iso_date(row.get("ex_dividend_date"))],
        key=lambda row: str(row.get("ex_dividend_date") or ""),
        reverse=True,
    )[:10]
    months = [_parse_iso_date(row.get("ex_dividend_date")).month for row in recent if _parse_iso_date(row.get("ex_dividend_date"))]
    if len(months) < 2:
        return {"type": "unknown", "label": "不固定", "months": months, "sample_count": len(months)}

    unique_months = sorted(set(months))
    coverage = len(unique_months)
    if coverage >= 10:
        return {
            "type": "monthly",
            "label": "月配（每月配息）",
            "months": list(range(1, 13)),
            "sample_count": len(months),
        }

    expected_count = max(1, round(12 / coverage))
    counts = {month: months.count(month) for month in unique_months}
    stable = all(count >= expected_count - 1 for count in counts.values())
    if not stable and len(months) >= 8:
        return {"type": "irregular", "label": "不固定", "months": unique_months, "sample_count": len(months)}

    if coverage == 1:
        label = f"年配（每年{_month_list_text(unique_months)}配息）"
        kind = "annual"
    elif coverage == 2:
        label = f"半年配（每年{_month_list_text(unique_months)}配息）"
        kind = "semiannual"
    elif coverage == 3:
        label = f"三次配（每年{_month_list_text(unique_months)}配息）"
        kind = "three_times"
    elif coverage == 4:
        label = f"季配（每年{_month_list_text(unique_months)}配息）"
        kind = "quarterly"
    elif coverage == 6:
        label = f"雙月配（每年{_month_list_text(unique_months)}配息）"
        kind = "bimonthly"
    else:
        label = "不固定"
        kind = "irregular"
    return {"type": kind, "label": label, "months": unique_months, "sample_count": len(months)}


def _month_list_text(months: list[int]) -> str:
    return "、".join(f"{month}月" for month in months)


def _dividend_event_payload(row: dict[str, Any] | None, shares: float = 0) -> dict[str, Any] | None:
    if not row:
        return None
    dividend = as_float(row.get("dividend"))
    ex_date = _parse_iso_date(row.get("ex_dividend_date"))
    today = date.today()
    return {
        "ex_dividend_date": row.get("ex_dividend_date"),
        "payout_date": row.get("payout_date"),
        "dividend": dividend,
        "estimated_cash": dividend * shares if dividend is not None and shares > 0 else None,
        "is_upcoming": ex_date is not None and ex_date >= today,
        "days_to_ex_dividend": (ex_date - today).days if ex_date else None,
        "announcement_year": row.get("announcement_year"),
        "source": row.get("source"),
    }


def _parse_iso_date(value: object) -> date | None:
    try:
        return date.fromisoformat(str(value or "")[:10])
    except ValueError:
        return None


def quote_snapshot_rows(
    items: list[dict[str, Any]],
    quotes: dict[str, dict[str, Any]],
    requested_symbols: set[str],
) -> list[dict[str, Any]]:
    now = datetime.now().astimezone().replace(second=0, microsecond=0)
    rows = []
    for item in items:
        symbol = item.get("symbol", "")
        if symbol not in requested_symbols:
            continue
        quote = quotes.get(symbol, {})
        if quote.get("close") is None:
            continue
        rows.append(
            {
                "ticker": item["ticker"],
                "captured_at": now.isoformat(),
                "trade_date": now.date().isoformat(),
                "close": quote.get("close"),
                "prev_close": quote.get("prev_close"),
                "change": quote.get("change"),
                "change_pct": quote.get("change_pct"),
                "source": quote.get("source", "yfinance"),
                "source_market": "YAHOO",
                "fetched_at_ts": quote.get("fetched_at_ts", 0),
            }
        )
    return rows


def attach_after_close_quotes(path: Path, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    enriched = []
    for item in items:
        enriched.append(
            {
                **item,
                "after_close_quote": latest_after_close_quote(path, item.get("ticker", "")),
            }
        )
    return enriched


def attach_sparklines(path: Path, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    enriched = []
    for item in items:
        rows = list_ohlcv_daily(path, str(item.get("ticker", "")), limit=15)
        points = [
            {
                "date": row.get("trade_date"),
                "close": as_float(row.get("close")),
            }
            for row in reversed(rows)
            if as_float(row.get("close")) is not None
        ]
        first_close = points[0]["close"] if points else None
        latest_close = points[-1]["close"] if points else None
        enriched.append(
            {
                **item,
                "sparkline": {
                    "points": points,
                    "latest_close": latest_close,
                    "first_close": first_close,
                    "avg_cost": as_float(item.get("avg_cost")),
                },
            }
        )
    return enriched


def profile_state_path(
    project_root: Path,
    profile_slug: str,
    data_root: Path | None = None,
    profiles: dict[str, str] | None = None,
) -> Path:
    profile = profile_info(profile_slug, profiles=profiles)
    root = Path(data_root) if data_root is not None else Path(project_root) / "data"
    return root / "profiles" / profile["slug"] / "state.json"


def profile_info(profile_slug: str, profiles: dict[str, str] | None = None) -> dict[str, str]:
    slug = str(profile_slug).strip().lower()
    active_profiles = profiles or PROFILES
    label = active_profiles.get(slug)
    if label is None:
        abort(404)
    return {
        "slug": slug,
        "label": label,
        "api_base": f"/{slug}",
    }


def parse_dividend_tickers(value: str) -> list[str]:
    tickers: list[str] = []
    seen: set[str] = set()
    for raw in str(value or "").replace("，", ",").split(","):
        ticker = raw.strip().upper()
        if not ticker or ticker in seen:
            continue
        seen.add(ticker)
        tickers.append(ticker)
    return tickers


def dedupe_dividend_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_event: dict[tuple[str, str, str], dict[str, Any]] = {}
    for row in rows:
        key = (
            str(row.get("ticker") or ""),
            str(row.get("ex_dividend_date") or ""),
            str(row.get("dividend") or ""),
        )
        existing = by_event.get(key)
        existing_is_yahoo = str(existing.get("source") or "").startswith("yahoo") if existing else False
        row_is_yahoo = str(row.get("source") or "").startswith("yahoo")
        if existing is None or (row_is_yahoo and not existing_is_yahoo):
            by_event[key] = row
    return sorted(
        by_event.values(),
        key=lambda row: (str(row.get("ticker") or ""), str(row.get("ex_dividend_date") or "")),
        reverse=True,
    )


def dividend_validation_payload(rows: list[dict[str, Any]]) -> dict[str, Any]:
    by_month: dict[tuple[str, str], dict[str, list[dict[str, Any]]]] = {}
    for row in rows:
        ticker = str(row.get("ticker") or "").strip().upper()
        ex_date = str(row.get("ex_dividend_date") or "")
        source_family = dividend_source_family(row.get("source"))
        if not ticker or len(ex_date) < 7 or source_family not in {"yahoo", "twse"}:
            continue
        month = ex_date[:7]
        by_month.setdefault((ticker, month), {}).setdefault(source_family, []).append(row)

    mismatches: list[dict[str, Any]] = []
    mismatch_keys: set[str] = set()
    for (ticker, month), sources in by_month.items():
        yahoo_rows = sorted(sources.get("yahoo", []), key=lambda row: str(row.get("ex_dividend_date") or ""), reverse=True)
        twse_rows = sorted(sources.get("twse", []), key=lambda row: str(row.get("ex_dividend_date") or ""), reverse=True)
        if not yahoo_rows or not twse_rows:
            continue
        yahoo = yahoo_rows[0]
        twse = twse_rows[0]
        yahoo_dividend = as_float(yahoo.get("dividend"))
        twse_dividend = as_float(twse.get("dividend"))
        date_mismatch = str(yahoo.get("ex_dividend_date") or "") != str(twse.get("ex_dividend_date") or "")
        dividend_mismatch = (
            yahoo_dividend is not None
            and twse_dividend is not None
            and abs(yahoo_dividend - twse_dividend) > 0.0001
        )
        if not date_mismatch and not dividend_mismatch:
            continue
        key = f"{ticker}|{month}"
        mismatch_keys.add(key)
        mismatches.append(
            {
                "key": key,
                "ticker": ticker,
                "month": month,
                "message": "Yahoo / TWSE 股利資料不一致，請人工檢查",
                "yahoo": {
                    "ex_dividend_date": yahoo.get("ex_dividend_date"),
                    "dividend": yahoo.get("dividend"),
                    "source": yahoo.get("source"),
                },
                "twse": {
                    "ex_dividend_date": twse.get("ex_dividend_date"),
                    "dividend": twse.get("dividend"),
                    "source": twse.get("source"),
                },
            }
        )

    return {
        "mismatch_count": len(mismatches),
        "mismatch_keys": sorted(mismatch_keys),
        "mismatches": sorted(mismatches, key=lambda row: (row["ticker"], row["month"]), reverse=True),
    }


def dividend_source_family(value: object) -> str:
    source = str(value or "").lower()
    if "yahoo" in source:
        return "yahoo"
    if "twse" in source:
        return "twse"
    return "other"


def profile_links(profiles: dict[str, str] | None = None) -> list[dict[str, str]]:
    active_profiles = profiles or PROFILES
    return [
        {"slug": slug, "label": label, "url": f"/{slug}"}
        for slug, label in active_profiles.items()
    ]


def database_payload(
    central_db_path: Path,
    quote_cache_path: Path,
    limit: object = None,
    offset: object = 0,
    q: str = "",
    asset_type: str = "",
    market: str = "",
    exchange_suffix: str = "",
    history_status: str = "",
) -> dict[str, Any]:
    all_matching = list_instruments(
        central_db_path,
        quote_cache=load_quote_cache(quote_cache_path),
        q=str(q or "").strip(),
        asset_type=str(asset_type or "").strip().upper(),
        market=str(market or "").strip().upper(),
        exchange_suffix=str(exchange_suffix or "").strip().upper(),
        history_status=str(history_status or "").strip(),
    )
    try:
        normalized_offset = max(int(offset or 0), 0)
    except (TypeError, ValueError):
        normalized_offset = 0
    try:
        normalized_limit = int(limit) if limit not in (None, "") else 200
    except (TypeError, ValueError):
        normalized_limit = 200
    normalized_limit = max(min(normalized_limit, 500), 1)
    instruments = all_matching[normalized_offset : normalized_offset + normalized_limit]
    quote_count = sum(1 for item in all_matching if item.get("close") is not None)
    tw_count = sum(1 for item in all_matching if item.get("exchange_suffix") == ".TW")
    two_count = sum(1 for item in all_matching if item.get("exchange_suffix") == ".TWO")
    etf_count = sum(1 for item in all_matching if item.get("segment") == "etf")
    listed_count = sum(1 for item in all_matching if item.get("segment") == "twse")
    otc_count = sum(1 for item in all_matching if item.get("segment") == "tpex")
    return {
        "updated_at": now_string(),
        "data_status": data_status_payload(central_db_path),
        "pagination": {
            "limit": normalized_limit,
            "offset": normalized_offset,
            "returned": len(instruments),
            "total": len(all_matching),
            "has_more": normalized_offset + len(instruments) < len(all_matching),
        },
        "summary": {
            "instrument_count": len(all_matching),
            "tw_count": tw_count,
            "two_count": two_count,
            "etf_count": etf_count,
            "listed_count": listed_count,
            "otc_count": otc_count,
            "quote_count": quote_count,
            "missing_quote_count": len(all_matching) - quote_count,
        },
        "instruments": instruments,
    }


def etf_holdings_payload(central_db_path: Path, ticker: str, as_of: str = "latest") -> dict[str, Any]:
    normalized = str(ticker or "").strip().upper()
    as_of_value = str(as_of or "latest").strip()
    result = get_etf_holding_snapshot(
        central_db_path,
        normalized,
        None if as_of_value.lower() in {"", "latest"} else as_of_value,
    )
    if not result:
        return {
            "ok": True,
            "ticker": normalized,
            "snapshot": None,
            "components": [],
            "summary": {
                "component_count": 0,
                "as_of_date": None,
                "source": None,
                "weight_total": 0,
            },
            "message": "No local ETF holdings snapshot is available for this ticker.",
            "data_status": data_status_payload(central_db_path),
        }

    snapshot = result["snapshot"]
    components = result["components"]
    weight_total = sum(as_float(row.get("weight"), 0) or 0 for row in components)
    return {
        "ok": True,
        "ticker": normalized,
        "snapshot": snapshot,
        "components": components,
        "summary": {
            "component_count": len(components),
            "as_of_date": snapshot.get("as_of_date"),
            "source": snapshot.get("source"),
            "weight_total": weight_total,
        },
        "message": "",
        "data_status": data_status_payload(central_db_path),
    }


def import_etf_holdings_csv_payload(central_db_path: Path, payload: dict[str, Any]) -> tuple[dict[str, Any], int]:
    confirm = bool(payload.get("confirm", False))
    override = bool(payload.get("override", False))
    source = str(payload.get("source") or "manual_csv").strip() or "manual_csv"
    source_url = str(payload.get("source_url") or "").strip()
    snapshot, provider_issues = normalize_etf_holdings_csv_text(
        str(payload.get("csv_text") or ""),
        etf_ticker=str(payload.get("etf_ticker") or ""),
        source=source,
        source_url=source_url,
    )
    issues = [_safe_provider_issue(issue) for issue in provider_issues]
    older_issue = _older_etf_snapshot_issue(central_db_path, snapshot, override=override)
    if older_issue:
        issues.append(older_issue)

    errors = [issue for issue in issues if issue.get("severity") == "error"]
    warnings = [issue for issue in issues if issue.get("severity") != "error"]
    response = _etf_holdings_import_response(
        snapshot=snapshot,
        issues=issues,
        warnings=warnings,
        errors=errors,
        confirm=confirm,
        imported=False,
    )

    if errors:
        return response, 409 if any(issue.get("code") == "older_snapshot_exists" for issue in errors) and confirm else (400 if confirm else 200)

    if not confirm:
        response["message"] = "Preview only. No ETF holdings snapshot was written."
        return response, 200

    imported = upsert_etf_holding_snapshot(
        central_db_path,
        etf_ticker=snapshot["etf_ticker"],
        as_of_date=snapshot["as_of_date"],
        source=snapshot["source"],
        source_url=snapshot.get("source_url", ""),
        status=snapshot.get("status", "ok"),
        notes=snapshot.get("notes", ""),
        rows=list(snapshot.get("components") or []),
    )
    imported_snapshot = dict(imported.get("snapshot") or {})
    imported_components = list(imported.get("components") or [])
    response = _etf_holdings_import_response(
        snapshot={
            **snapshot,
            **{
                "row_count": imported_snapshot.get("row_count", snapshot.get("row_count", 0)),
                "components": imported_components,
            },
        },
        issues=issues,
        warnings=warnings,
        errors=errors,
        confirm=confirm,
        imported=True,
    )
    response["message"] = "ETF holdings snapshot imported."
    return response, 200


def fetch_etf_holdings_provider_payload(project_root: Path, central_db_path: Path, payload: dict[str, Any]) -> tuple[dict[str, Any], int]:
    ticker = str(payload.get("ticker") or "").strip().upper()
    confirm = bool(payload.get("confirm", False))
    override = bool(payload.get("override", False))
    provider_id = str(payload.get("provider_id") or "").strip()
    if not ticker:
        issue = {
            "provider_id": provider_id or "configured_http_etf_holdings",
            "code": "ticker_required",
            "message": "ticker is required.",
            "severity": "error",
            "retryable": False,
            "instrument_id": "",
            "source": "local_config",
        }
        return _empty_etf_holdings_provider_response(ticker, confirm=confirm, issues=[issue], provider_id=provider_id), 400

    providers, config_issues = load_configured_http_etf_holdings_providers(project_root)
    if config_issues:
        issues = [_safe_provider_issue(issue) for issue in config_issues]
        return _empty_etf_holdings_provider_response(ticker, confirm=confirm, issues=issues, provider_id=provider_id), 400

    provider = None
    if provider_id:
        provider = next((candidate for candidate in providers if candidate.provider_id == provider_id), None)
        if provider is not None and not provider.supports(ticker):
            issue = {
                "provider_id": provider.provider_id,
                "code": "provider_unsupported_ticker",
                "message": "Configured ETF holdings provider does not support this ticker.",
                "severity": "error",
                "retryable": False,
                "instrument_id": ticker,
                "source": provider.source,
            }
            return _empty_etf_holdings_provider_response(ticker, confirm=confirm, issues=[issue], provider_id=provider.provider_id), 400
    else:
        provider = next((candidate for candidate in providers if candidate.supports(ticker)), None)

    if provider is None:
        issue = {
            "provider_id": provider_id or "configured_http_etf_holdings",
            "code": "provider_not_found",
            "message": "No configured ETF holdings provider was found for this ticker.",
            "severity": "error",
            "retryable": False,
            "instrument_id": ticker,
            "source": "local_config",
        }
        return _empty_etf_holdings_provider_response(ticker, confirm=confirm, issues=[issue], provider_id=provider_id), 400

    result = provider.load(ticker)
    snapshot = dict(result.items[0]) if result.items else _empty_provider_snapshot(ticker=ticker, source=provider.source)
    issues = [_safe_provider_issue(issue) for issue in result.issues]
    if not result.items and not any(issue.get("severity") == "error" for issue in issues):
        issues.append(
            {
                "provider_id": provider.provider_id,
                "code": "provider_no_snapshot",
                "message": "ETF holdings provider did not return a usable snapshot.",
                "severity": "error",
                "retryable": False,
                "instrument_id": ticker,
                "source": provider.source,
            }
        )
    older_issue = _older_etf_snapshot_issue(
        central_db_path,
        snapshot,
        override=override,
        provider_id=provider.provider_id,
        source=provider.source,
    )
    if older_issue:
        issues.append(older_issue)

    errors = [issue for issue in issues if issue.get("severity") == "error"]
    warnings = [issue for issue in issues if issue.get("severity") != "error"]
    response = _etf_holdings_import_response(
        snapshot=snapshot,
        issues=issues,
        warnings=warnings,
        errors=errors,
        confirm=confirm,
        imported=False,
    )
    response["provider"] = _safe_etf_provider_metadata(provider.provider_id, snapshot, result, errors=errors)
    if errors:
        response["message"] = "ETF holdings provider has validation or fetch errors."

    if errors:
        return response, 409 if any(issue.get("code") == "older_snapshot_exists" for issue in errors) and confirm else (400 if confirm else 200)
    if not confirm:
        response["message"] = "Preview only. No ETF holdings snapshot was written."
        return response, 200

    imported = upsert_etf_holding_snapshot(
        central_db_path,
        etf_ticker=snapshot["etf_ticker"],
        as_of_date=snapshot["as_of_date"],
        source=snapshot["source"],
        source_url=snapshot.get("source_url", ""),
        status=snapshot.get("status", "ok"),
        notes=snapshot.get("notes", ""),
        rows=list(snapshot.get("components") or []),
    )
    imported_snapshot = dict(imported.get("snapshot") or {})
    imported_components = list(imported.get("components") or [])
    response = _etf_holdings_import_response(
        snapshot={
            **snapshot,
            **{
                "row_count": imported_snapshot.get("row_count", snapshot.get("row_count", 0)),
                "components": imported_components,
            },
        },
        issues=issues,
        warnings=warnings,
        errors=errors,
        confirm=confirm,
        imported=True,
    )
    response["provider"] = _safe_etf_provider_metadata(provider.provider_id, snapshot, result, errors=errors)
    response["message"] = "ETF holdings snapshot imported from configured provider."
    return response, 200


def _empty_etf_holdings_provider_response(
    ticker: str,
    *,
    confirm: bool,
    issues: list[dict[str, Any]],
    provider_id: str = "",
) -> dict[str, Any]:
    errors = [issue for issue in issues if issue.get("severity") == "error"]
    warnings = [issue for issue in issues if issue.get("severity") != "error"]
    snapshot = _empty_provider_snapshot(ticker=ticker, source=provider_id or "configured_http_etf_holdings")
    response = _etf_holdings_import_response(
        snapshot=snapshot,
        issues=issues,
        warnings=warnings,
        errors=errors,
        confirm=confirm,
        imported=False,
    )
    if errors:
        response["message"] = "ETF holdings provider has validation or fetch errors."
    response["provider"] = {
        "provider_id": provider_id or "configured_http_etf_holdings",
        "fetched_at": "",
        "status": "error",
        "message": errors[0]["message"] if errors else "",
        "parser_version": "",
        "checksum": "",
    }
    return response


def _empty_provider_snapshot(*, ticker: str, source: str) -> dict[str, Any]:
    return {
        "etf_ticker": str(ticker or "").strip().upper(),
        "as_of_date": "",
        "source": str(source or "configured_http_etf_holdings").strip() or "configured_http_etf_holdings",
        "source_url": "",
        "status": "error",
        "row_count": 0,
        "notes": "",
        "components": [],
        "message": "",
    }


def _safe_etf_provider_metadata(
    provider_id: str,
    snapshot: dict[str, Any],
    result: Any,
    *,
    errors: list[dict[str, Any]],
) -> dict[str, Any]:
    fetched_at = result.fetched_at.isoformat() if getattr(result, "fetched_at", None) else str(snapshot.get("fetched_at") or "")
    return {
        "provider_id": str(provider_id or ""),
        "fetched_at": fetched_at,
        "status": "error" if errors else str(snapshot.get("status") or "ok"),
        "message": str(snapshot.get("message") or (errors[0]["message"] if errors else "")).strip(),
        "parser_version": str(snapshot.get("parser_version") or "").strip(),
        "checksum": str(snapshot.get("checksum") or "").strip(),
    }


def _etf_holdings_import_response(
    *,
    snapshot: dict[str, Any],
    issues: list[dict[str, Any]],
    warnings: list[dict[str, Any]],
    errors: list[dict[str, Any]],
    confirm: bool,
    imported: bool,
) -> dict[str, Any]:
    components = list(snapshot.get("components") or [])
    return {
        "ok": not errors,
        "mode": "import" if confirm else "preview",
        "confirmed": confirm,
        "imported": imported,
        "snapshot": _safe_etf_snapshot_preview(snapshot),
        "components": [_safe_etf_component_preview(row) for row in components],
        "summary": {
            "etf_ticker": str(snapshot.get("etf_ticker") or "").strip().upper(),
            "as_of_date": str(snapshot.get("as_of_date") or "").strip()[:10],
            "source": str(snapshot.get("source") or "").strip(),
            "component_count": len(components),
            "weight_total": sum(as_float(row.get("weight"), 0) or 0 for row in components),
        },
        "warnings": warnings,
        "errors": errors,
        "issues": issues,
        "message": "ETF holdings CSV has validation errors." if errors else "",
    }


def _safe_etf_snapshot_preview(snapshot: dict[str, Any]) -> dict[str, Any]:
    return {
        "etf_ticker": str(snapshot.get("etf_ticker") or "").strip().upper(),
        "as_of_date": str(snapshot.get("as_of_date") or "").strip()[:10],
        "source": str(snapshot.get("source") or "").strip(),
        "source_url": str(snapshot.get("source_url") or "").strip(),
        "status": str(snapshot.get("status") or "ok").strip() or "ok",
        "row_count": int(snapshot.get("row_count") or len(snapshot.get("components") or [])),
        "notes": str(snapshot.get("notes") or "").strip(),
        "parser_version": str(snapshot.get("parser_version") or "").strip(),
        "checksum": str(snapshot.get("checksum") or "").strip(),
        "message": str(snapshot.get("message") or "").strip(),
    }


def _safe_etf_component_preview(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "constituent_ticker": str(row.get("constituent_ticker") or "").strip().upper(),
        "constituent_name": str(row.get("constituent_name") or "").strip(),
        "weight": as_float(row.get("weight")),
        "shares": as_float(row.get("shares")),
        "market_value": as_float(row.get("market_value")),
        "industry": str(row.get("industry") or "").strip(),
        "sort_order": int(as_float(row.get("sort_order"), 0) or 0),
    }


def _safe_provider_issue(issue: Any) -> dict[str, Any]:
    payload = issue.to_dict() if hasattr(issue, "to_dict") else dict(issue)
    safe = {
        "provider_id": str(payload.get("provider_id") or ""),
        "code": str(payload.get("code") or ""),
        "message": str(payload.get("message") or ""),
        "severity": str(payload.get("severity") or "error"),
        "retryable": bool(payload.get("retryable", False)),
        "instrument_id": str(payload.get("instrument_id") or ""),
        "source": str(payload.get("source") or ""),
    }
    details = payload.get("details")
    if isinstance(details, dict):
        safe["details"] = {
            str(key): value
            for key, value in details.items()
            if isinstance(value, (str, int, float, bool)) or value is None
        }
    return safe


def _older_etf_snapshot_issue(
    central_db_path: Path,
    snapshot: dict[str, Any],
    *,
    override: bool,
    provider_id: str = "manual_csv",
    source: str = "manual_csv",
) -> dict[str, Any] | None:
    if override:
        return None
    ticker = str(snapshot.get("etf_ticker") or "").strip().upper()
    as_of_date = str(snapshot.get("as_of_date") or "").strip()[:10]
    if not ticker or not as_of_date:
        return None
    etf_db_path = central_db_path / SEGMENT_FILES["etf"]
    if not etf_db_path.exists():
        return None
    existing = get_etf_holding_snapshot(central_db_path, ticker)
    existing_date = str(existing.get("snapshot", {}).get("as_of_date") or "").strip()[:10] if existing else ""
    if existing_date and existing_date > as_of_date:
        return {
            "provider_id": provider_id,
            "code": "older_snapshot_exists",
            "message": f"Existing ETF holdings snapshot for {ticker} is newer ({existing_date}) than submitted snapshot ({as_of_date}).",
            "severity": "error",
            "retryable": False,
            "instrument_id": ticker,
            "source": source,
            "details": {
                "existing_as_of_date": existing_date,
                "submitted_as_of_date": as_of_date,
            },
        }
    return None


def market_data_status_payload(
    *,
    data_root: Path,
    central_db_path: Path,
    quote_cache_path: Path,
    refresh_log_path: Path,
    demo_mode: bool = False,
) -> dict[str, Any]:
    segment_rows = [_read_market_segment_status(central_db_path, segment, filename) for segment, filename in SEGMENT_FILES.items()]
    official_daily = _official_daily_status_from_segments(segment_rows, demo_mode)
    quote_cache = _quote_cache_status(quote_cache_path)
    quote_tables = _combined_table_status(segment_rows, "quotes")
    return {
        "ok": True,
        "demo_mode": bool(demo_mode),
        "runtime_root": str(data_root.resolve()),
        "data_root": str(data_root.resolve()),
        "generated_at": now_string(),
        "updated_at": now_string(),
        "official_daily": official_daily,
        "ohlcv": {
            "updated_through": _max_text(row["ohlcv"]["last_date"] for row in segment_rows),
            "first_date": _min_text(row["ohlcv"]["first_date"] for row in segment_rows),
            "row_count": sum(row["ohlcv"]["row_count"] for row in segment_rows),
            "segments": {row["segment"]: row["ohlcv"] for row in segment_rows},
        },
        "quotes": {
            "latest_cache_timestamp": quote_cache["latest_timestamp"],
            "cache_count": quote_cache["count"],
            "cache_status_counts": quote_cache["status_counts"],
            "latest_table_date": quote_tables["max_quote_date"],
            "latest_table_updated_at": quote_tables["max_updated_at"],
            "table_row_count": quote_tables["row_count"],
            "segments": {row["segment"]: row["quotes"] for row in segment_rows},
        },
        "after_close": _combined_table_status(segment_rows, "after_close"),
        "dividends": _combined_table_status(segment_rows, "dividends"),
        "health": _combined_health_status(segment_rows),
        "recent_refresh_log": _recent_refresh_log(refresh_log_path),
    }


def _read_market_segment_status(root: Path, segment: str, filename: str) -> dict[str, Any]:
    db_path = root / filename
    status: dict[str, Any] = {
        "segment": segment,
        "database": filename,
        "exists": db_path.exists(),
        "ohlcv": _empty_ohlcv_status(),
        "quotes": _empty_quotes_status(),
        "after_close": _empty_after_close_status(),
        "dividends": _empty_dividends_status(),
        "health": _empty_health_status(),
        "update_status": {},
    }
    if not db_path.exists():
        return status
    try:
        with _connect_sqlite_readonly(db_path) as conn:
            conn.row_factory = sqlite3.Row
            status["ohlcv"] = _read_ohlcv_status(conn)
            status["quotes"] = _read_quotes_status(conn)
            status["after_close"] = _read_after_close_status(conn)
            status["dividends"] = _read_dividends_status(conn)
            status["health"] = _read_health_status(conn)
            status["update_status"] = _read_update_status_rows(conn)
    except sqlite3.Error as exc:
        status["error"] = str(exc)
    return status


def _connect_sqlite_readonly(path: Path) -> sqlite3.Connection:
    return sqlite3.connect(f"file:{path.resolve().as_posix()}?mode=ro", uri=True)


def _table_exists_readonly(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table,),
    ).fetchone()
    return row is not None


def _read_ohlcv_status(conn: sqlite3.Connection) -> dict[str, Any]:
    if not _table_exists_readonly(conn, "ohlcv_daily"):
        return _empty_ohlcv_status()
    row = conn.execute(
        "SELECT COUNT(*) AS row_count, MIN(date) AS first_date, MAX(date) AS last_date FROM ohlcv_daily"
    ).fetchone()
    return {
        "row_count": int(row["row_count"] or 0),
        "first_date": row["first_date"],
        "last_date": row["last_date"],
    }


def _read_quotes_status(conn: sqlite3.Connection) -> dict[str, Any]:
    if not _table_exists_readonly(conn, "quotes"):
        return _empty_quotes_status()
    row = conn.execute(
        """
        SELECT
            COUNT(*) AS row_count,
            MAX(quote_date) AS max_quote_date,
            MAX(quote_time) AS max_quote_time,
            MAX(updated_at) AS max_updated_at
        FROM quotes
        """
    ).fetchone()
    return {
        "row_count": int(row["row_count"] or 0),
        "max_quote_date": row["max_quote_date"],
        "max_quote_time": row["max_quote_time"],
        "max_updated_at": row["max_updated_at"],
    }


def _read_after_close_status(conn: sqlite3.Connection) -> dict[str, Any]:
    if not _table_exists_readonly(conn, "after_close_quotes"):
        return _empty_after_close_status()
    row = conn.execute(
        """
        SELECT
            COUNT(*) AS row_count,
            MAX(quote_date) AS max_quote_date,
            MAX(created_at) AS max_created_at
        FROM after_close_quotes
        """
    ).fetchone()
    return {
        "row_count": int(row["row_count"] or 0),
        "max_quote_date": row["max_quote_date"],
        "max_created_at": row["max_created_at"],
    }


def _read_dividends_status(conn: sqlite3.Connection) -> dict[str, Any]:
    if not _table_exists_readonly(conn, "etf_dividends"):
        return _empty_dividends_status()
    row = conn.execute(
        """
        SELECT
            COUNT(*) AS row_count,
            MAX(ex_dividend_date) AS max_ex_dividend_date,
            MAX(payout_date) AS max_payout_date
        FROM etf_dividends
        """
    ).fetchone()
    return {
        "row_count": int(row["row_count"] or 0),
        "max_ex_dividend_date": row["max_ex_dividend_date"],
        "max_payout_date": row["max_payout_date"],
    }


def _read_health_status(conn: sqlite3.Connection) -> dict[str, Any]:
    if not _table_exists_readonly(conn, "instrument_health_summary"):
        return _empty_health_status()
    rows = conn.execute(
        """
        SELECT
            COALESCE(history_status, '') AS history_status,
            COUNT(*) AS count,
            MAX(last_daily_date) AS max_last_daily_date,
            MAX(last_checked_at) AS max_last_checked_at,
            MAX(last_success_at) AS max_last_success_at
        FROM instrument_health_summary
        GROUP BY COALESCE(history_status, '')
        """
    ).fetchall()
    status_counts = {str(row["history_status"] or "unknown"): int(row["count"] or 0) for row in rows}
    return {
        "instrument_count": sum(status_counts.values()),
        "status_counts": status_counts,
        "max_last_daily_date": _max_text(row["max_last_daily_date"] for row in rows),
        "max_last_checked_at": _max_text(row["max_last_checked_at"] for row in rows),
        "max_last_success_at": _max_text(row["max_last_success_at"] for row in rows),
    }


def _read_update_status_rows(conn: sqlite3.Connection) -> dict[str, dict[str, Any]]:
    if not _table_exists_readonly(conn, "update_status"):
        return {}
    rows = conn.execute(
        """
        SELECT
            job_name,
            source,
            last_started_at,
            last_finished_at,
            next_run_at,
            last_status,
            success_count,
            fail_count,
            message
        FROM update_status
        """
    ).fetchall()
    return {str(row["job_name"] or ""): dict(row) for row in rows}


def _official_daily_status_from_segments(segment_rows: list[dict[str, Any]], demo_mode: bool) -> dict[str, Any]:
    rows = [
        row["update_status"]["official_daily"]
        for row in segment_rows
        if row.get("update_status", {}).get("official_daily")
    ]
    if rows:
        latest = max(rows, key=lambda row: str(row.get("last_started_at") or row.get("last_finished_at") or ""))
        return {
            "job_name": "official_daily",
            "source": latest.get("source", ""),
            "status": latest.get("last_status", ""),
            "last_started_at": latest.get("last_started_at", ""),
            "last_finished_at": latest.get("last_finished_at", ""),
            "next_run_at": latest.get("next_run_at", ""),
            "success_count": latest.get("success_count", 0),
            "fail_count": latest.get("fail_count", 0),
            "message": _safe_status_message("official_daily", latest.get("message", "")),
        }
    if demo_mode:
        return {
            "job_name": "official_daily",
            "source": "synthetic_demo",
            "status": "local_fixture",
            "last_started_at": "",
            "last_finished_at": "",
            "next_run_at": "",
            "success_count": 0,
            "fail_count": 0,
            "message": "Demo mode uses local synthetic fixture market data; refresh is disabled.",
        }
    return {
        "job_name": "official_daily",
        "source": "",
        "status": "unknown",
        "last_started_at": "",
        "last_finished_at": "",
        "next_run_at": "",
        "success_count": 0,
        "fail_count": 0,
        "message": "No official daily update status is available.",
    }


def _quote_cache_status(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"exists": False, "count": 0, "latest_timestamp": None, "status_counts": {}}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"exists": True, "count": 0, "latest_timestamp": None, "status_counts": {}, "error": "unreadable"}
    if not isinstance(payload, dict):
        return {"exists": True, "count": 0, "latest_timestamp": None, "status_counts": {}}
    timestamps: list[str] = []
    status_counts: dict[str, int] = {}
    for item in payload.values():
        if not isinstance(item, dict):
            continue
        status = str(item.get("status") or "unknown")
        status_counts[status] = status_counts.get(status, 0) + 1
        timestamp = _quote_cache_timestamp(item)
        if timestamp:
            timestamps.append(timestamp)
    return {
        "exists": True,
        "count": len(payload),
        "latest_timestamp": _max_text(timestamps),
        "status_counts": status_counts,
    }


def _quote_cache_timestamp(item: dict[str, Any]) -> str:
    fetched_at_ts = item.get("fetched_at_ts")
    if fetched_at_ts not in (None, ""):
        try:
            return datetime.fromtimestamp(float(fetched_at_ts)).astimezone().isoformat(timespec="seconds")
        except (TypeError, ValueError, OSError):
            pass
    return _max_text(str(item.get(key) or "").strip() for key in ("fetched_at", "price_time")) or ""


def _recent_refresh_log(path: Path, limit: int = 10) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if not isinstance(payload, list):
        return []
    rows = []
    for row in payload[-limit:]:
        if not isinstance(row, dict):
            continue
        source = str(row.get("source") or "")
        rows.append(
            {
                "time": row.get("time", ""),
                "source": source,
                "status": row.get("status", ""),
                "message": _safe_status_message(source, row.get("message", "")),
            }
        )
    return rows


def _safe_status_message(source: str, message: Any) -> str:
    text = str(message or "")
    source_text = str(source or "").lower()
    lowered = text.lower()
    if "gmail" in source_text:
        return "Gmail refresh details redacted."
    sensitive_markers = ("credential", "token", "password", "secret", "authorization", "bearer")
    if any(marker in lowered for marker in sensitive_markers):
        return "Refresh details redacted."
    return text[:500]


def _combined_table_status(segment_rows: list[dict[str, Any]], key: str) -> dict[str, Any]:
    rows = [row[key] for row in segment_rows]
    if key == "quotes":
        return {
            "row_count": sum(row["row_count"] for row in rows),
            "max_quote_date": _max_text(row["max_quote_date"] for row in rows),
            "max_quote_time": _max_text(row["max_quote_time"] for row in rows),
            "max_updated_at": _max_text(row["max_updated_at"] for row in rows),
        }
    if key == "after_close":
        return {
            "row_count": sum(row["row_count"] for row in rows),
            "max_quote_date": _max_text(row["max_quote_date"] for row in rows),
            "max_created_at": _max_text(row["max_created_at"] for row in rows),
            "segments": {row["segment"]: row["after_close"] for row in segment_rows},
        }
    if key == "dividends":
        return {
            "row_count": sum(row["row_count"] for row in rows),
            "max_ex_dividend_date": _max_text(row["max_ex_dividend_date"] for row in rows),
            "max_payout_date": _max_text(row["max_payout_date"] for row in rows),
            "segments": {row["segment"]: row["dividends"] for row in segment_rows},
        }
    return {"row_count": 0}


def _combined_health_status(segment_rows: list[dict[str, Any]]) -> dict[str, Any]:
    status_counts: dict[str, int] = {}
    for row in segment_rows:
        for status, count in row["health"]["status_counts"].items():
            status_counts[status] = status_counts.get(status, 0) + int(count or 0)
    return {
        "instrument_count": sum(row["health"]["instrument_count"] for row in segment_rows),
        "status_counts": status_counts,
        "max_last_daily_date": _max_text(row["health"]["max_last_daily_date"] for row in segment_rows),
        "max_last_checked_at": _max_text(row["health"]["max_last_checked_at"] for row in segment_rows),
        "max_last_success_at": _max_text(row["health"]["max_last_success_at"] for row in segment_rows),
        "segments": {row["segment"]: row["health"] for row in segment_rows},
    }


def _max_text(values: Any) -> str | None:
    texts = [str(value) for value in values if value not in (None, "")]
    return max(texts) if texts else None


def _min_text(values: Any) -> str | None:
    texts = [str(value) for value in values if value not in (None, "")]
    return min(texts) if texts else None


def _empty_ohlcv_status() -> dict[str, Any]:
    return {"row_count": 0, "first_date": None, "last_date": None}


def _empty_quotes_status() -> dict[str, Any]:
    return {"row_count": 0, "max_quote_date": None, "max_quote_time": None, "max_updated_at": None}


def _empty_after_close_status() -> dict[str, Any]:
    return {"row_count": 0, "max_quote_date": None, "max_created_at": None}


def _empty_dividends_status() -> dict[str, Any]:
    return {"row_count": 0, "max_ex_dividend_date": None, "max_payout_date": None}


def _empty_health_status() -> dict[str, Any]:
    return {
        "instrument_count": 0,
        "status_counts": {},
        "max_last_daily_date": None,
        "max_last_checked_at": None,
        "max_last_success_at": None,
    }


def data_status_payload(central_db_path: Path) -> list[dict[str, Any]]:
    labels = {
        "tw_intraday_15m": "台股盤中",
        "tw_after_close": "台股盤後",
        "official_daily": "官方日線",
        "official_history_backfill": "日線補齊",
        "us_intraday_15m": "美股盤中",
        "gmail_statements": "Gmail 對帳單",
    }
    order = {key: index for index, key in enumerate(labels)}
    rows_by_job: dict[str, dict[str, Any]] = {}
    for row in list_update_status(central_db_path):
        job_name = str(row.get("job_name", ""))
        rows_by_job[job_name] = {
            "job_name": job_name,
            "label": labels.get(job_name, job_name),
            "source": row.get("source", ""),
            "last_started_at": row.get("last_started_at", ""),
            "last_finished_at": row.get("last_finished_at", ""),
            "next_run_at": row.get("next_run_at", "") or default_next_run_at(job_name),
            "last_status": row.get("last_status", ""),
            "success_count": row.get("success_count", 0),
            "fail_count": row.get("fail_count", 0),
            "message": row.get("message", ""),
        }
    for job_name, label in labels.items():
        rows_by_job.setdefault(
            job_name,
            {
                "job_name": job_name,
                "label": label,
                "source": default_status_source(job_name),
                "last_started_at": "",
                "last_finished_at": "",
                "next_run_at": default_next_run_at(job_name),
                "last_status": "pending",
                "success_count": 0,
                "fail_count": 0,
                "message": "尚未執行",
            },
        )
    rows = list(rows_by_job.values())
    return sorted(rows, key=lambda row: order.get(row["job_name"], 99))


def default_status_source(job_name: str) -> str:
    if job_name == "gmail_statements":
        return "gmail"
    if job_name in {"official_daily", "official_history_backfill"}:
        return "twse_tpex"
    return "yfinance"


def default_next_run_at(job_name: str) -> str:
    if job_name == "tw_intraday_15m":
        return next_interval_run_at("tw").isoformat(timespec="seconds")
    if job_name == "us_intraday_15m":
        return next_interval_run_at("us").isoformat(timespec="seconds")
    if job_name == "tw_after_close":
        return next_daily_run_at("13:31").isoformat(timespec="seconds")
    if job_name == "official_daily":
        return next_daily_run_at("14:00").isoformat(timespec="seconds")
    if job_name == "official_history_backfill":
        return next_half_hour_run_at().isoformat(timespec="seconds")
    if job_name == "gmail_statements":
        return next_daily_run_at("23:30").isoformat(timespec="seconds")
    return ""


def next_half_hour_run_at(now: datetime | None = None) -> datetime:
    now = now or datetime.now().astimezone()
    if now.minute < 7:
        candidate = now.replace(minute=7, second=0, microsecond=0)
    elif now.minute < 37:
        candidate = now.replace(minute=37, second=0, microsecond=0)
    else:
        candidate = (now + timedelta(hours=1)).replace(minute=7, second=0, microsecond=0)
    if candidate <= now:
        candidate += timedelta(minutes=30)
    return candidate


def next_interval_run_at(market: str, now: datetime | None = None) -> datetime:
    now = now or datetime.now().astimezone()
    if market == "tw":
        start, end = "09:01", "13:01"
    else:
        start, end = "21:30", "05:00"
    candidates = []
    for day_offset in range(3):
        day = (now + timedelta(days=day_offset)).date()
        for hour, minute in _interval_slots(start, end):
            candidate = datetime.combine(day, datetime.min.time(), tzinfo=now.tzinfo).replace(hour=hour, minute=minute)
            if _slot_in_market_window(candidate, start, end) and candidate > now:
                candidates.append(candidate)
    return min(candidates) if candidates else now + timedelta(minutes=15)


def next_daily_run_at(hhmm: str, now: datetime | None = None) -> datetime:
    now = now or datetime.now().astimezone()
    hour, minute = [int(part) for part in hhmm.split(":", 1)]
    candidate = datetime.combine(now.date(), datetime.min.time(), tzinfo=now.tzinfo).replace(hour=hour, minute=minute)
    if candidate <= now:
        candidate += timedelta(days=1)
    return candidate


def _interval_slots(start: str, end: str) -> list[tuple[int, int]]:
    start_minute = _hhmm_to_minutes(start)
    end_minute = _hhmm_to_minutes(end)
    if start_minute <= end_minute:
        minutes = range(start_minute, end_minute + 1, 15)
    else:
        minutes = list(range(start_minute, 24 * 60, 15)) + list(range(0, end_minute + 1, 15))
    return [(minute // 60, minute % 60) for minute in minutes]


def _slot_in_market_window(candidate: datetime, start: str, end: str) -> bool:
    current = candidate.hour * 60 + candidate.minute
    start_minute = _hhmm_to_minutes(start)
    end_minute = _hhmm_to_minutes(end)
    if start_minute <= end_minute:
        return start_minute <= current <= end_minute
    return current >= start_minute or current <= end_minute


def _hhmm_to_minutes(value: str) -> int:
    hour_text, minute_text = value.split(":", 1)
    return int(hour_text) * 60 + int(minute_text)


def normalise_profile_state(state: dict[str, Any], profile_slug: str) -> None:
    settings = state.setdefault("settings", {})
    settings["app_title"] = PROFILES[profile_slug]
    settings.setdefault("currency", "TWD")
    settings.setdefault("cash_available", 0)
    settings["refresh_seconds"] = 900
    settings["scheduled_refresh_minutes"] = 15
    settings["tw_refresh_window"] = "09:01-13:01"
    settings["us_refresh_window"] = "21:30-05:00"
    settings.setdefault("broker_fee_rate", 0.001425)
    settings.setdefault("transaction_tax_rate", 0.003)
    state.setdefault("holdings", [])
    state.setdefault("watchlist", [])
    state.setdefault("transactions", [])
    state.setdefault("cash_movements", [])
    state.setdefault("price_overrides", {})


def empty_profile_state(profile_slug: str) -> dict[str, Any]:
    state: dict[str, Any] = {
        "settings": {
            "app_title": PROFILES[profile_slug],
            "currency": "TWD",
            "cash_available": 0,
            "refresh_seconds": 900,
            "scheduled_refresh_minutes": 15,
            "tw_refresh_window": "09:01-13:01",
            "us_refresh_window": "21:30-05:00",
            "important_signal_limit": 6,
            "broker_fee_rate": 0.001425,
            "transaction_tax_rate": 0.003,
        },
        "holdings": [],
        "watchlist": [],
        "transactions": [],
        "cash_movements": [],
        "price_overrides": {},
    }
    return state


def refresh_log_message(summary: dict[str, Any]) -> str:
    requested = ", ".join(summary.get("requested_symbols", [])) or "none"
    skipped = ", ".join(summary.get("skipped_symbols", [])) or "none"
    forced = ", ".join(summary.get("forced_symbols", [])) or "none"
    return f"requested={requested}; skipped={skipped}; forced={forced}"


def record_cash_deposit_from_payload(state_path: Path, payload: dict[str, Any]) -> dict[str, Any]:
    amount = optional_float(payload.get("amount"))
    if amount is None or amount <= 0:
        raise ValueError("請輸入大於 0 的存入金額。")

    movement_date = parse_trade_date(payload.get("date"))
    note = str(payload.get("note", "") or "").strip() or "存入資金"
    result: dict[str, Any] = {}

    def mutator(state: dict[str, Any]) -> None:
        settings = state.setdefault("settings", {})
        cash = as_float(settings.get("cash_available"), 0) or 0
        new_cash = cash + amount
        settings["cash_available"] = new_cash
        state.setdefault("cash_movements", []).append(
            {
                "time": movement_date,
                "action": "CASH_IN",
                "amount": amount,
                "note": note,
            }
        )
        result.update(
            {
                "ok": True,
                "action": "CASH_IN",
                "date": movement_date,
                "amount": amount,
                "cash_available": new_cash,
            }
        )

    update_state(state_path, mutator)
    return result


def record_dividend_income_from_payload(state_path: Path, payload: dict[str, Any]) -> dict[str, Any]:
    ticker = str(payload.get("ticker", "") or "").strip().upper()
    if not ticker:
        raise ValueError("請輸入股票代碼。")

    amount = optional_float(payload.get("amount"))
    if amount is None or amount == 0:
        raise ValueError("請輸入不等於 0 的實收股利；修正時可輸入負數。")

    movement_date = parse_trade_date(payload.get("date"))
    note = str(payload.get("note", "") or "").strip() or "券商實收股利"
    result: dict[str, Any] = {}

    def mutator(state: dict[str, Any]) -> None:
        settings = state.setdefault("settings", {})
        movements = state.setdefault("dividend_movements", [])
        current = sum(
            as_float(item.get("amount"), 0) or 0
            for item in movements
            if isinstance(item, dict)
        )
        new_total = current + amount
        settings["dividend_income_total"] = new_total
        movements.append(
            {
                "id": uuid.uuid4().hex,
                "ticker": ticker,
                "time": movement_date,
                "amount": amount,
                "note": note,
                "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            }
        )
        result.update(
            {
                "ok": True,
                "date": movement_date,
                "ticker": ticker,
                "amount": amount,
                "dividend_income_total": new_total,
            }
        )

    update_state(state_path, mutator)
    return result


def record_transaction_from_payload(
    state_path: Path,
    payload: dict[str, Any],
    central_db_path: Path | None = None,
) -> dict[str, Any]:
    action = str(payload.get("action", "")).strip().upper()
    if action not in {"BUY", "SELL"}:
        raise ValueError("交易類型必須是 BUY 或 SELL。")

    ticker = str(payload.get("ticker", "")).strip().upper()
    if not ticker:
        raise ValueError("請輸入股票代碼。")

    trade_date = parse_trade_date(payload.get("date"))
    odd_shares = optional_float(payload.get("shares")) or 0
    lots = optional_float(payload.get("lots")) or 0
    price = optional_float(payload.get("price"))
    if lots < 0 or odd_shares < 0:
        raise ValueError("張數與股數不能小於 0。")
    shares = lots * 1000 + odd_shares
    if shares <= 0:
        raise ValueError("請輸入張數或股數。")
    if price is None or price <= 0:
        raise ValueError("請輸入有效成交價。")

    note = str(payload.get("note", "") or "").strip()
    provided_fee = optional_float(payload.get("fee"))
    provided_tax = optional_float(payload.get("tax"))
    if provided_fee is not None and provided_fee < 0:
        raise ValueError("手續費不能小於 0。")
    if provided_tax is not None and provided_tax < 0:
        raise ValueError("交易稅不能小於 0。")

    result: dict[str, Any] = {}

    def mutator(state: dict[str, Any]) -> None:
        settings = state.setdefault("settings", {})
        gross_amount = trade_consideration_twd(shares, price)
        fee = provided_fee if provided_fee is not None else estimate_charge(gross_amount, settings.get("broker_fee_rate"))
        tax = 0.0
        if action == "SELL":
            tax = provided_tax if provided_tax is not None else estimate_charge(gross_amount, settings.get("transaction_tax_rate"))

        duplicate = find_duplicate_transaction(
            state,
            action=action,
            ticker=ticker,
            trade_date=trade_date,
            shares=shares,
            price=price,
            fee=fee,
            tax=tax,
        )
        if duplicate:
            result.update(
                {
                    "ok": True,
                    "duplicate": True,
                    "skipped": True,
                    "action": action,
                    "ticker": ticker,
                    "date": trade_date,
                    "shares": shares,
                    "price": price,
                    "fee": fee,
                    "tax": tax,
                    "message": "重複交易，已跳過寫入。",
                }
            )
            return

        existing = find_existing_item(state, ticker)
        central = get_instrument(central_db_path, ticker) if central_db_path else None
        suffix = str(
            payload.get("exchange_suffix")
            or (central or {}).get("exchange_suffix")
            or existing.get("exchange_suffix")
            or ".TW"
        )
        asset_type = str(
            payload.get("type")
            or (central or {}).get("type")
            or existing.get("type")
            or infer_asset_type(ticker)
        )
        central_name = (central or {}).get("name")
        name = str(
            payload.get("name")
            or (central_name if is_specific_name(central_name, ticker) else "")
            or existing.get("name")
            or ticker
        )
        registered = (
            register_instrument(
                central_db_path,
                ticker=ticker,
                name=name,
                asset_type=asset_type,
                exchange_suffix=suffix,
                source="transaction",
            )
            if central_db_path
            else None
        )
        if registered:
            suffix = registered["exchange_suffix"]
            asset_type = registered["type"]
            name = registered["name"]
            symbol = registered["symbol"]
        else:
            symbol = yahoo_symbol(ticker, suffix)

        if action == "BUY":
            record_buy(
                state,
                ticker=ticker,
                shares=shares,
                price=price,
                name=name,
                asset_type=asset_type,
                suffix=suffix,
                fee=fee,
                trade_date=trade_date,
                note=note or "網頁買進",
            )
            cash_delta = -(gross_amount + fee)
        else:
            record_sell(
                state,
                ticker=ticker,
                shares=shares,
                price=price,
                fee=fee,
                tax=tax,
                trade_date=trade_date,
                note=note or "網頁賣出",
            )
            cash_delta = gross_amount - fee - tax

        if central_db_path:
            rebuild_holdings_from_transactions(state, list_corporate_actions(central_db_path))

        cash = as_float(settings.get("cash_available"), 0) or 0
        settings["cash_available"] = cash + cash_delta
        result.update(
            {
                "ok": True,
                "action": action,
                "ticker": ticker,
                "symbol": symbol,
                "date": trade_date,
                "shares": shares,
                "price": price,
                "fee": fee,
                "tax": tax,
                "gross_amount": gross_amount,
                "cash_delta": cash_delta,
                "cash_available": settings["cash_available"],
                "duplicate": False,
                "skipped": False,
            }
        )

    update_state(state_path, mutator)
    return result


def find_duplicate_transaction(
    state: dict[str, Any],
    *,
    action: str,
    ticker: str,
    trade_date: str,
    shares: float,
    price: float,
    fee: float,
    tax: float,
) -> dict[str, Any] | None:
    target = transaction_match_key(action, ticker, trade_date, shares, price, fee, tax)
    for transaction in state.get("transactions", []):
        candidate = transaction_match_key(
            transaction.get("action"),
            transaction.get("ticker"),
            str(transaction.get("time", ""))[:10],
            transaction.get("shares"),
            transaction.get("price"),
            transaction.get("fee"),
            transaction.get("tax"),
        )
        if candidate == target:
            return transaction
    return None


def transaction_match_key(
    action: object,
    ticker: object,
    trade_date: object,
    shares: object,
    price: object,
    fee: object,
    tax: object,
) -> tuple[object, ...]:
    return (
        str(action or "").strip().upper(),
        str(ticker or "").strip().upper(),
        str(trade_date or "")[:10],
        round(as_float(shares, 0) or 0, 4),
        round(as_float(price, 0) or 0, 4),
        round(as_float(fee, 0) or 0, 4),
        round(as_float(tax, 0) or 0, 4),
    )


def update_transaction_from_payload(
    state_path: Path,
    transaction_id: str,
    payload: dict[str, Any],
    central_db_path: Path | None = None,
) -> dict[str, Any]:
    transaction_id = str(transaction_id or "").strip()
    if not transaction_id:
        raise ValueError("缺少交易 id。")

    result: dict[str, Any] = {}

    def mutator(state: dict[str, Any]) -> None:
        ensure_transaction_ids(state)
        transactions = state.setdefault("transactions", [])
        transaction = next((item for item in transactions if str(item.get("id", "")) == transaction_id), None)
        if transaction is None:
            raise ValueError("找不到這筆交易。")

        old_delta = transaction_cash_delta(transaction)
        action = str(payload.get("action", transaction.get("action", ""))).strip().upper()
        if action not in {"BUY", "SELL"}:
            raise ValueError("交易方向必須是 BUY 或 SELL。")
        ticker = str(payload.get("ticker", transaction.get("ticker", ""))).strip().upper()
        if not ticker:
            raise ValueError("請輸入股票代碼。")
        trade_date = parse_trade_date(payload.get("date", transaction.get("time", "")))
        shares = optional_float(payload.get("shares", transaction.get("shares")))
        price = optional_float(payload.get("price", transaction.get("price")))
        fee = optional_float(payload.get("fee", transaction.get("fee"))) or 0
        tax = optional_float(payload.get("tax", transaction.get("tax"))) or 0
        if shares is None or shares <= 0:
            raise ValueError("股數必須大於 0。")
        if price is None or price <= 0:
            raise ValueError("成交價必須大於 0。")
        if fee < 0 or tax < 0:
            raise ValueError("手續費與交易稅不能小於 0。")
        if action == "BUY":
            tax = 0.0

        gross_amount = trade_consideration_twd(shares, price)
        transaction.update(
            {
                "time": trade_date,
                "action": action,
                "ticker": ticker,
                "shares": shares,
                "price": price,
                "gross_amount": gross_amount,
                "fee": fee,
                "tax": tax,
                "amount": gross_amount + fee if action == "BUY" else gross_amount - fee - tax,
                "note": str(payload.get("note", transaction.get("note", "")) or "").strip(),
                "reviewed": bool(payload.get("reviewed", transaction.get("reviewed", False))),
                "conflict_acknowledged": bool(
                    payload.get("conflict_acknowledged", transaction.get("conflict_acknowledged", False))
                ),
            }
        )
        transaction.pop("conflict", None)
        transaction.pop("lots", None)
        transaction.pop("realized_pnl", None)

        new_delta = transaction_cash_delta(transaction)
        settings = state.setdefault("settings", {})
        settings["cash_available"] = (as_float(settings.get("cash_available"), 0) or 0) - old_delta + new_delta
        rebuild_holdings_from_transactions(
            state,
            list_corporate_actions(central_db_path) if central_db_path else None,
        )
        result.update({"ok": True, "id": transaction_id, "ticker": ticker, "cash_delta": new_delta - old_delta})

    update_state(state_path, mutator)
    return result


def delete_transaction_from_payload(
    state_path: Path,
    transaction_id: str,
    central_db_path: Path | None = None,
) -> dict[str, Any]:
    transaction_id = str(transaction_id or "").strip()
    if not transaction_id:
        raise ValueError("缺少交易 id。")

    result: dict[str, Any] = {}

    def mutator(state: dict[str, Any]) -> None:
        ensure_transaction_ids(state)
        transactions = state.setdefault("transactions", [])
        index = next((idx for idx, item in enumerate(transactions) if str(item.get("id", "")) == transaction_id), -1)
        if index < 0:
            raise ValueError("找不到這筆交易。")
        transaction = transactions.pop(index)
        delta = transaction_cash_delta(transaction)
        settings = state.setdefault("settings", {})
        settings["cash_available"] = (as_float(settings.get("cash_available"), 0) or 0) - delta
        rebuild_holdings_from_transactions(
            state,
            list_corporate_actions(central_db_path) if central_db_path else None,
        )
        result.update({"ok": True, "id": transaction_id, "ticker": transaction.get("ticker", ""), "cash_delta": -delta})

    update_state(state_path, mutator)
    return result


def transaction_cash_delta(transaction: dict[str, Any]) -> float:
    shares = as_float(transaction.get("shares"), 0) or 0
    price = as_float(transaction.get("price"), 0) or 0
    fee = as_float(transaction.get("fee"), 0) or 0
    tax = as_float(transaction.get("tax"), 0) or 0
    gross = trade_consideration_twd(shares, price)
    action = str(transaction.get("action", "")).strip().upper()
    if action == "BUY":
        return -(gross + fee)
    if action == "SELL":
        return gross - fee - tax
    return 0.0


def transaction_book_payload(transactions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = [dict(row) for row in transactions]
    exact_counts: dict[tuple[object, ...], int] = {}
    for row in rows:
        key = transaction_match_key(
            row.get("action"),
            row.get("ticker"),
            str(row.get("time", ""))[:10],
            row.get("shares"),
            row.get("price"),
            row.get("fee"),
            row.get("tax"),
        )
        exact_counts[key] = exact_counts.get(key, 0) + 1

    for index, row in enumerate(rows):
        row.setdefault("id", "")
        row["date"] = str(row.get("time", ""))[:10]
        reviewed = bool(row.get("reviewed"))
        severe = "" if bool(row.get("conflict_acknowledged", False)) else str(row.get("conflict", "") or "")
        warnings: list[str] = []
        key = transaction_match_key(
            row.get("action"),
            row.get("ticker"),
            row["date"],
            row.get("shares"),
            row.get("price"),
            row.get("fee"),
            row.get("tax"),
        )
        if exact_counts.get(key, 0) > 1 and not reviewed:
            warnings.append("疑似重複")
        if not reviewed and near_date_conflict(row, rows, index):
            warnings.append("日期可能衝突")
        if severe:
            warnings.append(severe)
        row["warnings"] = warnings
        row["status"] = "error" if severe else ("warning" if warnings else ("reviewed" if reviewed else "normal"))
    return list(reversed(rows))


def near_date_conflict(row: dict[str, Any], rows: list[dict[str, Any]], row_index: int) -> bool:
    row_date = _parse_iso_date(str(row.get("time", ""))[:10])
    if row_date is None:
        return False
    for other_index, other in enumerate(rows):
        if other_index == row_index:
            continue
        if str(other.get("action", "")).upper() != str(row.get("action", "")).upper():
            continue
        if str(other.get("ticker", "")).upper() != str(row.get("ticker", "")).upper():
            continue
        if round(as_float(other.get("shares"), 0) or 0, 4) != round(as_float(row.get("shares"), 0) or 0, 4):
            continue
        if round(as_float(other.get("price"), 0) or 0, 4) != round(as_float(row.get("price"), 0) or 0, 4):
            continue
        other_date = _parse_iso_date(str(other.get("time", ""))[:10])
        if other_date and 0 < abs((row_date - other_date).days) <= 2:
            return True
    return False


def parse_trade_date(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return date.today().isoformat()
    for fmt in ("%Y/%m/%d", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt).date().isoformat()
        except ValueError:
            pass
    raise ValueError("日期格式請使用 yyyy/mm/dd。")


def optional_float(value: Any) -> float | None:
    return as_float(value, None)


def estimate_charge(amount: float, rate_value: Any) -> float:
    rate = as_float(rate_value, 0) or 0
    if amount <= 0 or rate <= 0:
        return 0.0
    return float(max(1, int(amount * rate + 0.5)))


def infer_asset_type(ticker: str) -> str:
    return "ETF" if str(ticker).startswith("00") else "STOCK"


def find_existing_item(state: dict[str, Any], ticker: str) -> dict[str, Any]:
    normalized = str(ticker).strip().upper()
    for collection in (state.get("holdings", []), state.get("watchlist", [])):
        for item in collection:
            if str(item.get("ticker", "")).strip().upper() == normalized:
                return item
    return {}


def render_ai_report(data: dict) -> str:
    summary = data.get("summary", {})
    lines = [
        "# 股票 / ETF 決策資料",
        "",
        f"更新時間：{data.get('updated_at', '')}",
        "",
        "## 摘要",
        f"- 可用資金：{fmt_money(summary.get('cash_available'))}",
        f"- 持股總市值：{fmt_money(summary.get('total_market_value'))}",
        f"- 持股總成本：{fmt_money(summary.get('total_cost_value'))}",
        f"- 總損益：{fmt_money(summary.get('total_pnl'))}（{fmt_pct(summary.get('total_pnl_pct'))}）",
        "",
        "## 美股與總經",
    ]

    for item in data.get("markets", []):
        close = item.get("close")
        if item.get("symbol") == "^TNX" and close is not None:
            close_text = f"{close:.2f}%"
        else:
            close_text = fmt_money(close, 2)
        lines.append(f"- {item.get('label')}：{close_text}（{fmt_pct(item.get('change_pct'))}）")

    lines.extend(
        [
            "",
            "## 持股",
            "| 代號 | 名稱 | 股數 | 現價 | 損益 | 損益率 | 損益兩平 | 訊號 | 備註 |",
            "| --- | --- | ---: | ---: | ---: | ---: | ---: | --- | --- |",
        ]
    )
    for item in data.get("holdings", []):
        lines.append(
            "| "
            + " | ".join(
                [
                    str(item.get("ticker", "")),
                    str(item.get("name", "")),
                    fmt_money(item.get("shares")),
                    fmt_money(item.get("close"), 2),
                    fmt_money(item.get("unrealized_pnl")),
                    fmt_pct(item.get("pnl_pct")),
                    fmt_money(item.get("breakeven_price"), 2),
                    "、".join(item.get("signals", [])),
                    str(item.get("note", "")),
                ]
            )
            + " |"
        )

    lines.extend(["", "## 重要訊號"])
    important = data.get("important", [])
    if important:
        for item in important:
            lines.append(
                f"- {item.get('source')} {item.get('ticker')} {item.get('name')}："
                + "、".join(item.get("signals", []))
            )
    else:
        lines.append("- 無")

    lines.extend(
        [
            "",
            "## 請 AI 判斷",
            "1. 今天哪些標的可以買？",
            "2. 哪些不買或等回檔？",
            "3. 哪些可以賣一部分？",
            "4. 哪些適合等除息後再看？",
            "5. 可用資金有限時，最佳優先順序是什麼？",
            "",
        ]
    )
    return "\n".join(lines)

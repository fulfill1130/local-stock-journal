from __future__ import annotations

import csv
import hashlib
import json
import os
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from market_data_types import ProviderIssue, ProviderResult
from yuanta_etf_holdings_provider import YuantaEtfHoldingsProvider


HttpFetcher = Callable[[str, dict[str, str], float], str]


@dataclass
class ConfiguredHttpEtfHoldingsProvider:
    provider_id: str
    endpoint_url: str
    response_format: str = "csv"
    tickers: tuple[str, ...] = ("*",)
    source: str = "http_etf_holdings"
    public_source_url: str = ""
    display_name: str = ""
    issuer: str = ""
    provider_type: str = "http"
    headers: dict[str, str] = field(default_factory=dict)
    timeout_seconds: float = 15
    cache_dir: Path | None = None
    fetcher: HttpFetcher | None = None

    parser_version = "1"

    def supports(self, ticker: str) -> bool:
        normalized = _ticker(ticker)
        supported = {_ticker(item) for item in self.tickers}
        return bool(normalized and ("*" in supported or normalized in supported))

    def fetch(self, ticker: str) -> str:
        normalized = _ticker(ticker)
        url = self.endpoint_url.replace("{ticker}", normalized)
        fetcher = self.fetcher or _default_fetch
        return fetcher(url, dict(self.headers), float(self.timeout_seconds or 15))

    def load(self, ticker: str) -> ProviderResult[dict[str, Any]]:
        normalized = _ticker(ticker)
        fetched_at = datetime.now().astimezone()
        if not self.endpoint_url:
            return self._result(
                fetched_at,
                issues=(
                    self._issue(
                        "provider_config_missing",
                        "ETF holdings provider is missing its endpoint URL.",
                        instrument_id=normalized,
                    ),
                ),
            )
        if not self.supports(normalized):
            return self._result(
                fetched_at,
                issues=(
                    self._issue(
                        "provider_unsupported_ticker",
                        "Configured ETF holdings provider does not support this ticker.",
                        instrument_id=normalized,
                        severity="warning",
                    ),
                ),
            )

        try:
            raw = self.fetch(normalized)
        except (HTTPError, URLError, TimeoutError, OSError, ValueError) as exc:
            return self._result(
                fetched_at,
                issues=(
                    self._issue(
                        "provider_fetch_failed",
                        f"ETF holdings provider fetch failed: {type(exc).__name__}",
                        instrument_id=normalized,
                        retryable=True,
                    ),
                ),
            )

        checksum = hashlib.sha256(raw.encode("utf-8")).hexdigest()
        self._cache_raw_response(normalized, raw, fetched_at, checksum)

        try:
            parsed = self.parse(raw)
            snapshot = self.normalize(parsed)
        except (csv.Error, json.JSONDecodeError, TypeError, ValueError) as exc:
            return self._result(
                fetched_at,
                issues=(
                    self._issue(
                        "provider_parse_failed",
                        f"ETF holdings provider response could not be parsed: {type(exc).__name__}",
                        instrument_id=normalized,
                    ),
                ),
            )

        snapshot["etf_ticker"] = snapshot.get("etf_ticker") or normalized
        snapshot["source"] = snapshot.get("source") or self.source
        snapshot["source_url"] = snapshot.get("source_url") or self.public_source_url
        snapshot["status"] = snapshot.get("status") or "ok"
        snapshot["fetched_at"] = fetched_at.isoformat()
        snapshot["parser_version"] = self.parser_version
        snapshot["checksum"] = checksum
        snapshot["message"] = snapshot.get("message") or "Fetched from configured live ETF holdings provider."
        issues = self.validate(snapshot)
        return self._result(
            fetched_at,
            items=() if any(issue.severity == "error" for issue in issues) else (snapshot,),
            issues=issues,
        )

    def parse(self, raw: Any) -> Any:
        text = str(raw or "")
        response_format = str(self.response_format or "csv").strip().lower()
        if response_format == "json":
            return json.loads(text)
        if response_format != "csv":
            raise ValueError("unsupported ETF holdings response format")
        return [dict(row) for row in csv.DictReader(text.splitlines()) if _has_any_value(row)]

    def normalize(self, parsed: Any) -> dict[str, Any]:
        if isinstance(parsed, dict):
            return self._normalize_json(parsed)
        return self._normalize_rows(list(parsed or []))

    def validate(self, snapshot: dict[str, Any]) -> tuple[ProviderIssue, ...]:
        issues: list[ProviderIssue] = []
        etf_ticker = _ticker(snapshot.get("etf_ticker"))
        components = list(snapshot.get("components") or [])
        if not etf_ticker:
            issues.append(self._issue("etf_ticker_required", "etf_ticker is required."))
        if not str(snapshot.get("as_of_date") or "").strip():
            issues.append(self._issue("as_of_date_required", "as_of_date is required.", instrument_id=etf_ticker))
        if not str(snapshot.get("source") or "").strip():
            issues.append(self._issue("source_required", "source is required.", instrument_id=etf_ticker))
        if not any(_ticker(row.get("constituent_ticker")) or str(row.get("constituent_name") or "").strip() for row in components):
            issues.append(
                self._issue(
                    "components_required",
                    "At least one component with ticker or name is required.",
                    instrument_id=etf_ticker,
                )
            )
        for index, row in enumerate(components, 1):
            weight = _float_or_none(row.get("weight"))
            if weight is not None and weight < 0:
                issues.append(
                    self._issue(
                        "negative_weight",
                        "ETF holding component weight must not be negative.",
                        instrument_id=etf_ticker,
                        details={"sort_order": row.get("sort_order") or index},
                    )
                )
        return tuple(issues)

    def _normalize_json(self, payload: dict[str, Any]) -> dict[str, Any]:
        components = [_normalize_component(row, index) for index, row in enumerate(list(payload.get("components") or []), 1)]
        return {
            "etf_ticker": _ticker(payload.get("etf_ticker") or payload.get("ticker")),
            "as_of_date": str(payload.get("as_of_date") or payload.get("date") or "").strip()[:10],
            "source": str(payload.get("source") or self.source).strip() or self.source,
            "source_url": str(payload.get("source_url") or self.public_source_url).strip(),
            "status": str(payload.get("status") or "ok").strip() or "ok",
            "row_count": len(components),
            "notes": str(payload.get("notes") or "").strip(),
            "components": components,
            "message": str(payload.get("message") or "").strip(),
        }

    def _normalize_rows(self, rows: list[dict[str, Any]]) -> dict[str, Any]:
        canonical_rows = [_canonical_row(row) for row in rows]
        first = canonical_rows[0] if canonical_rows else {}
        components = [_normalize_component(row, index) for index, row in enumerate(canonical_rows, 1)]
        return {
            "etf_ticker": _ticker(first.get("etf_ticker")),
            "as_of_date": str(first.get("as_of_date") or "").strip()[:10],
            "source": str(first.get("source") or self.source).strip() or self.source,
            "source_url": str(first.get("source_url") or self.public_source_url).strip(),
            "status": str(first.get("status") or "ok").strip() or "ok",
            "row_count": len(components),
            "notes": str(first.get("notes") or "").strip(),
            "components": components,
            "message": "",
        }

    def _cache_raw_response(self, ticker: str, raw: str, fetched_at: datetime, checksum: str) -> None:
        if self.cache_dir is None:
            return
        target = self.cache_dir / _safe_name(self.provider_id) / _safe_name(ticker)
        target.mkdir(parents=True, exist_ok=True)
        timestamp = fetched_at.strftime("%Y%m%dT%H%M%S%z")
        suffix = "json" if str(self.response_format).lower() == "json" else "csv"
        (target / f"{timestamp}-{checksum[:12]}.{suffix}").write_text(raw, encoding="utf-8")

    def _result(
        self,
        fetched_at: datetime,
        *,
        items: tuple[dict[str, Any], ...] = (),
        issues: tuple[ProviderIssue, ...] = (),
    ) -> ProviderResult[dict[str, Any]]:
        return ProviderResult(
            provider_id=self.provider_id,
            items=items,
            issues=issues,
            fetched_at=fetched_at,
            source=self.source,
        )

    def _issue(
        self,
        code: str,
        message: str,
        *,
        instrument_id: str = "",
        severity: str = "error",
        retryable: bool = False,
        details: dict[str, Any] | None = None,
    ) -> ProviderIssue:
        return ProviderIssue(
            provider_id=self.provider_id,
            code=code,
            message=message,
            severity=severity,  # type: ignore[arg-type]
            retryable=retryable,
            instrument_id=instrument_id,
            source=self.source,
            observed_at=datetime.now().astimezone(),
            details=details or {},
        )


def load_configured_http_etf_holdings_providers(
    project_root: Path,
    *,
    env: dict[str, str] | None = None,
    fetcher: HttpFetcher | None = None,
) -> tuple[list[Any], tuple[ProviderIssue, ...]]:
    env_map = env if env is not None else os.environ
    config_path = Path(project_root) / "config" / "providers.local.json"
    if not config_path.exists():
        return [], (_config_issue("provider_config_missing", "No local ETF holdings provider config is available."),)
    try:
        payload = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return [], (_config_issue("provider_config_invalid", "Local ETF holdings provider config could not be read."),)

    rows = payload.get("etf_holdings_providers")
    if rows is None:
        rows = payload.get("etf_holdings", {}).get("providers") if isinstance(payload.get("etf_holdings"), dict) else []
    providers: list[Any] = []
    for index, row in enumerate(rows or [], 1):
        if not isinstance(row, dict):
            continue
        provider_type = str(row.get("type") or "http").strip().lower()
        if provider_type == "yuanta":
            tickers = row.get("tickers") or row.get("supported_tickers") or ["0050", "0056"]
            yuanta_fetcher = (lambda url, timeout, _fetcher=fetcher: _fetcher(url, {}, timeout)) if fetcher else None
            providers.append(
                YuantaEtfHoldingsProvider(
                    provider_id=str(row.get("provider_id") or "yuanta_etf_holdings").strip() or "yuanta_etf_holdings",
                    tickers=tuple(str(item) for item in tickers) if isinstance(tickers, list) else (str(tickers),),
                    url_template=str(row.get("url_template") or "https://www.yuantaetfs.com/product/detail/{ticker}/ratio").strip(),
                    timeout_seconds=float(row.get("timeout_seconds") or 15),
                    display_name=str(row.get("display_name") or row.get("name") or "").strip(),
                    issuer=str(row.get("issuer") or "Yuanta").strip() or "Yuanta",
                    fetcher=yuanta_fetcher,
                )
            )
            continue
        if provider_type not in {"http", "https"}:
            continue
        provider_id = str(row.get("provider_id") or f"http_etf_holdings_{index}").strip()
        endpoint_url = str(row.get("url") or "").strip()
        url_env = str(row.get("url_env") or "").strip()
        if url_env:
            endpoint_url = str(env_map.get(url_env) or "").strip()
        api_key_env = str(row.get("api_key_env") or "").strip()
        headers = {
            str(key): str(value)
            for key, value in dict(row.get("headers") or {}).items()
            if str(key).strip() and str(value).strip()
        }
        if api_key_env and env_map.get(api_key_env):
            header_name = str(row.get("api_key_header") or "Authorization").strip() or "Authorization"
            scheme = str(row.get("auth_scheme") or "Bearer").strip()
            token = str(env_map[api_key_env])
            headers[header_name] = f"{scheme} {token}" if scheme else token
        tickers = row.get("tickers") or row.get("supported_tickers") or ["*"]
        providers.append(
            ConfiguredHttpEtfHoldingsProvider(
                provider_id=provider_id,
                endpoint_url=endpoint_url,
                response_format=str(row.get("format") or "csv").strip().lower() or "csv",
                tickers=tuple(str(item) for item in tickers) if isinstance(tickers, list) else (str(tickers),),
                source=str(row.get("source") or provider_id).strip() or provider_id,
                public_source_url=str(row.get("public_source_url") or "").strip(),
                display_name=str(row.get("display_name") or row.get("name") or "").strip(),
                issuer=str(row.get("issuer") or "").strip(),
                headers=headers,
                timeout_seconds=float(row.get("timeout_seconds") or 15),
                cache_dir=(Path(project_root) / "data" / "provider_cache" / "etf_holdings") if row.get("cache_raw") else None,
                fetcher=fetcher,
            )
        )
    if not providers:
        return [], (_config_issue("provider_config_missing", "No HTTP ETF holdings providers are configured."),)
    return providers, ()


def _default_fetch(url: str, headers: dict[str, str], timeout_seconds: float) -> str:
    request = Request(url, headers=headers | {"User-Agent": "stock-daily-helper/etf-holdings-manual"})
    with urlopen(request, timeout=timeout_seconds) as response:
        return response.read().decode("utf-8-sig")


def _config_issue(code: str, message: str) -> ProviderIssue:
    return ProviderIssue(
        provider_id="configured_http_etf_holdings",
        code=code,
        message=message,
        severity="error",
        retryable=False,
        source="local_config",
        observed_at=datetime.now().astimezone(),
    )


def _canonical_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "etf_ticker": _first_value(row, "etf_ticker", "ETF", "ticker"),
        "as_of_date": _first_value(row, "as_of_date", "date"),
        "source": _first_value(row, "source"),
        "source_url": _first_value(row, "source_url"),
        "status": _first_value(row, "status") or "ok",
        "notes": _first_value(row, "notes"),
        "constituent_ticker": _first_value(row, "constituent_ticker", "component_ticker", "holding_ticker"),
        "constituent_name": _first_value(row, "constituent_name", "name"),
        "weight": _first_value(row, "weight", "weight_percent"),
        "shares": _first_value(row, "shares"),
        "market_value": _first_value(row, "market_value"),
        "industry": _first_value(row, "industry"),
        "sort_order": _first_value(row, "sort_order"),
    }


def _normalize_component(row: dict[str, Any], index: int) -> dict[str, Any]:
    return {
        "constituent_ticker": _ticker(_first_value(row, "constituent_ticker", "component_ticker", "holding_ticker")),
        "constituent_name": _first_value(row, "constituent_name", "name"),
        "weight": _float_or_none(_first_value(row, "weight", "weight_percent")),
        "shares": _float_or_none(_first_value(row, "shares")),
        "market_value": _float_or_none(_first_value(row, "market_value")),
        "industry": _first_value(row, "industry"),
        "sort_order": _int_or_none(_first_value(row, "sort_order")) or index,
    }


def _first_value(row: dict[str, Any], *names: str) -> str:
    normalized = {_column_key(key): value for key, value in row.items()}
    for name in names:
        value = normalized.get(_column_key(name))
        text = str(value or "").strip()
        if text:
            return text
    return ""


def _column_key(value: Any) -> str:
    return str(value or "").strip().lower()


def _ticker(value: Any) -> str:
    return str(value or "").strip().upper()


def _has_any_value(row: dict[str, Any]) -> bool:
    return any(str(value or "").strip() for value in row.values())


def _float_or_none(value: Any) -> float | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return float(text)
    except (TypeError, ValueError):
        return None


def _int_or_none(value: Any) -> int | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return int(float(text))
    except (TypeError, ValueError):
        return None


def _safe_name(value: Any) -> str:
    return "".join(char if char.isalnum() or char in {"-", "_"} else "_" for char in str(value or "").strip()) or "unknown"

from __future__ import annotations

import hashlib
import html
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from market_data_types import ProviderIssue, ProviderResult


YuantaFetcher = Callable[[str, float], str]


@dataclass
class YuantaEtfHoldingsProvider:
    provider_id: str = "yuanta_etf_holdings"
    tickers: tuple[str, ...] = ("0050", "0056")
    url_template: str = "https://www.yuantaetfs.com/product/detail/{ticker}/ratio"
    timeout_seconds: float = 15
    display_name: str = ""
    issuer: str = "Yuanta"
    provider_type: str = "yuanta"
    fetcher: YuantaFetcher | None = None

    parser_version = "1"
    source = "yuanta_etfs_html"

    def supports(self, ticker: str) -> bool:
        normalized = _ticker(ticker)
        supported = {_ticker(item) for item in self.tickers}
        return bool(normalized and ("*" in supported or normalized in supported))

    def fetch(self, ticker: str) -> str:
        normalized = _ticker(ticker)
        url = self.url_template.replace("{ticker}", normalized)
        fetcher = self.fetcher or _default_fetch
        return fetcher(url, float(self.timeout_seconds or 15))

    def load(self, ticker: str) -> ProviderResult[dict[str, Any]]:
        normalized = _ticker(ticker)
        fetched_at = datetime.now().astimezone()
        if not self.supports(normalized):
            return self._result(
                fetched_at,
                issues=(
                    self._issue(
                        "provider_unsupported_ticker",
                        "Yuanta ETF holdings provider does not support this ticker.",
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
                        f"Yuanta ETF holdings fetch failed: {type(exc).__name__}",
                        instrument_id=normalized,
                        retryable=True,
                    ),
                ),
            )

        checksum = hashlib.sha256(raw.encode("utf-8")).hexdigest()
        try:
            parsed = self.parse(raw)
            snapshot = self.normalize(parsed)
        except (TypeError, ValueError) as exc:
            return self._result(
                fetched_at,
                issues=(
                    self._issue(
                        "provider_parse_failed",
                        f"Yuanta ETF holdings response could not be parsed: {type(exc).__name__}",
                        instrument_id=normalized,
                    ),
                ),
            )

        snapshot["etf_ticker"] = snapshot.get("etf_ticker") or normalized
        snapshot["source_url"] = snapshot.get("source_url") or self.url_template.replace("{ticker}", normalized)
        snapshot["fetched_at"] = fetched_at.isoformat()
        snapshot["parser_version"] = self.parser_version
        snapshot["checksum"] = checksum
        snapshot["message"] = "Fetched from Yuanta public ETF ratio page."
        issues = self.validate(snapshot)
        return self._result(
            fetched_at,
            items=() if any(issue.severity == "error" for issue in issues) else (snapshot,),
            issues=issues,
        )

    def parse(self, raw: Any) -> dict[str, Any]:
        text = _visible_text(str(raw or ""))
        section = _stock_weight_section(text)
        as_of_date = _parse_date(section) or _parse_date(text)
        rows = [
            {
                "constituent_ticker": match.group("ticker"),
                "constituent_name": match.group("name").strip(),
                "shares": match.group("shares"),
                "weight": match.group("weight"),
            }
            for match in _YUANTA_ROW_RE.finditer(section)
        ]
        return {
            "as_of_date": as_of_date,
            "rows": rows,
        }

    def normalize(self, parsed: Any) -> dict[str, Any]:
        payload = dict(parsed or {})
        rows = list(payload.get("rows") or [])
        components = [
            {
                "constituent_ticker": _ticker(row.get("constituent_ticker")),
                "constituent_name": str(row.get("constituent_name") or "").strip(),
                "weight": _float_or_none(row.get("weight")),
                "shares": _float_or_none(row.get("shares")),
                "market_value": None,
                "industry": "",
                "sort_order": index,
            }
            for index, row in enumerate(rows, 1)
        ]
        return {
            "etf_ticker": _ticker(payload.get("etf_ticker")),
            "as_of_date": str(payload.get("as_of_date") or "").strip()[:10],
            "source": self.source,
            "source_url": str(payload.get("source_url") or "").strip(),
            "status": "ok",
            "row_count": len(components),
            "notes": "Yuanta public ratio page HTML parser; manual-trigger only.",
            "components": components,
            "message": "",
        }

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


def _default_fetch(url: str, timeout_seconds: float) -> str:
    request = Request(url, headers={"User-Agent": "stock-daily-helper/yuanta-etf-holdings-manual"})
    with urlopen(request, timeout=timeout_seconds) as response:
        return response.read().decode("utf-8-sig")


def _visible_text(raw_html: str) -> str:
    text = re.sub(r"(?is)<(script|style).*?</\1>", " ", raw_html)
    text = re.sub(r"(?i)<br\s*/?>", " ", text)
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def _stock_weight_section(text: str) -> str:
    start = text.find("基金權重-股票")
    if start < 0:
        return text
    next_section = text.find("基金權重-", start + len("基金權重-股票"))
    return text[start:next_section] if next_section > start else text[start:]


def _parse_date(text: str) -> str:
    match = re.search(r"交易日期[:：]?\s*(\d{4})[/-](\d{1,2})[/-](\d{1,2})", text)
    if not match:
        return ""
    year, month, day = (int(part) for part in match.groups())
    return f"{year:04d}-{month:02d}-{day:02d}"


_YUANTA_ROW_RE = re.compile(
    r"商品代碼\s*(?P<ticker>[A-Z0-9]+)\s*"
    r"商品名稱\s*(?P<name>.*?)\s*"
    r"商品數量\s*(?P<shares>[-+]?[0-9,]+(?:\.\d+)?)\s*"
    r"商品權重\s*(?P<weight>[-+]?\d+(?:\.\d+)?)",
)


def _ticker(value: Any) -> str:
    return str(value or "").strip().upper()


def _float_or_none(value: Any) -> float | None:
    text = str(value or "").strip().replace(",", "")
    if not text:
        return None
    try:
        return float(text)
    except (TypeError, ValueError):
        return None

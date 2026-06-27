from __future__ import annotations

import hashlib
import re
import ssl
from dataclasses import dataclass
from datetime import datetime
from html import unescape
from html.parser import HTMLParser
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from market_data_types import ProviderIssue, ProviderResult


FubonFetcher = Callable[[str, float], str]


@dataclass
class FubonEtfHoldingsProvider:
    provider_id: str = "fubon_etf_holdings"
    tickers: tuple[str, ...] = ("00900",)
    url_template: str = "https://websys.fsit.com.tw/FubonETF/Fund/Assets.aspx?stkId={ticker}"
    timeout_seconds: float = 15
    display_name: str = ""
    issuer: str = "Fubon"
    provider_type: str = "fubon"
    fetcher: FubonFetcher | None = None

    parser_version = "1"
    source = "fubon_assets_html"

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
                        "Fubon ETF holdings provider does not support this ticker.",
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
                        f"Fubon ETF holdings fetch failed: {type(exc).__name__}",
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
                        f"Fubon ETF holdings response could not be parsed: {type(exc).__name__}",
                        instrument_id=normalized,
                    ),
                ),
            )

        snapshot["etf_ticker"] = snapshot.get("etf_ticker") or normalized
        snapshot["source_url"] = snapshot.get("source_url") or self.url_template.replace("{ticker}", normalized)
        snapshot["fetched_at"] = fetched_at.isoformat()
        snapshot["parser_version"] = self.parser_version
        snapshot["checksum"] = checksum
        snapshot["message"] = "Fetched from Fubon public ETF fund assets page."
        issues = self.validate(snapshot)
        return self._result(
            fetched_at,
            items=() if any(issue.severity == "error" for issue in issues) else (snapshot,),
            issues=issues,
        )

    def parse(self, raw: Any) -> dict[str, Any]:
        text = str(raw or "")
        tables = _TableParser.parse_tables(text)
        stock_rows: list[dict[str, Any]] = []
        non_stock_rows: list[dict[str, Any]] = []
        stock_total_weight: float | None = None

        for table in tables:
            if not table:
                continue
            header = [_cell_key(cell) for cell in table[0]]
            if header == ["股票代碼", "股票名稱", "股數", "金額", "權重(%)"]:
                for row in table[1:]:
                    if len(row) < 5:
                        continue
                    code = str(row[0] or "").strip()
                    if code == "股票合計":
                        stock_total_weight = _float_or_none(row[4])
                        continue
                    if not re.fullmatch(r"[0-9A-Z]{4,6}", code):
                        continue
                    stock_rows.append(
                        {
                            "constituent_ticker": code,
                            "constituent_name": row[1],
                            "shares": row[2],
                            "market_value": row[3],
                            "weight": row[4],
                        }
                    )
            elif header in (["期貨代碼", "期貨名稱", "口數", "金額", "權重(%)"], ["項目", "金額"]):
                non_stock_rows.extend({"label": row[0], "weight": row[4] if len(row) > 4 else ""} for row in table[1:] if row)

        return {
            "as_of_date": _parse_date(_visible_text(text)),
            "stock_rows": stock_rows,
            "stock_total_weight": stock_total_weight,
            "non_stock_row_count": len(non_stock_rows),
        }

    def normalize(self, parsed: Any) -> dict[str, Any]:
        payload = dict(parsed or {})
        rows = list(payload.get("stock_rows") or [])
        components = [
            {
                "constituent_ticker": _ticker(row.get("constituent_ticker")),
                "constituent_name": str(row.get("constituent_name") or "").strip(),
                "weight": _float_or_none(row.get("weight")),
                "shares": _float_or_none(row.get("shares")),
                "market_value": _float_or_none(row.get("market_value")),
                "industry": "",
                "sort_order": index,
            }
            for index, row in enumerate(rows, 1)
        ]
        total_weight = _float_or_none(payload.get("stock_total_weight"))
        notes = "Fubon public fund assets page parser; stock holdings only."
        if payload.get("non_stock_row_count"):
            notes += f" Non-stock asset rows summarized but not included as components: {int(payload['non_stock_row_count'])}."
        if len(components) >= 20 and total_weight is not None:
            notes += f" Stock total weight from source: {total_weight:.4f}%."
        elif components:
            notes += " Parsed row count is low; review preview before confirming."
        return {
            "etf_ticker": "",
            "as_of_date": str(payload.get("as_of_date") or "").strip()[:10],
            "source": self.source,
            "source_url": "",
            "status": "ok",
            "row_count": len(components),
            "notes": notes,
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
                    "At least one stock component with ticker or name is required.",
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


class _TableParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.table_depth = 0
        self.tables: list[list[list[str]]] = []
        self.current_table: list[list[str]] | None = None
        self.current_row: list[str] | None = None
        self.current_cell: list[str] | None = None

    @classmethod
    def parse_tables(cls, html_text: str) -> list[list[list[str]]]:
        parser = cls()
        parser.feed(html_text)
        return parser.tables

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        name = tag.lower()
        if name == "table":
            if self.table_depth == 0:
                self.current_table = []
            self.table_depth += 1
        elif self.table_depth > 0 and name == "tr":
            self.current_row = []
        elif self.table_depth > 0 and name in {"td", "th"}:
            self.current_cell = []
        elif self.current_cell is not None and name == "br":
            self.current_cell.append(" ")

    def handle_endtag(self, tag: str) -> None:
        name = tag.lower()
        if name in {"td", "th"} and self.current_cell is not None and self.current_row is not None:
            self.current_row.append(_clean_text(" ".join(self.current_cell)))
            self.current_cell = None
        elif name == "tr" and self.current_row is not None and self.current_table is not None:
            if any(cell for cell in self.current_row):
                self.current_table.append(self.current_row)
            self.current_row = None
        elif name == "table" and self.table_depth > 0:
            self.table_depth -= 1
            if self.table_depth == 0 and self.current_table is not None:
                self.tables.append(self.current_table)
                self.current_table = None

    def handle_data(self, data: str) -> None:
        if self.current_cell is not None:
            self.current_cell.append(data)


def _default_fetch(url: str, timeout_seconds: float) -> str:
    request = Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) stock-daily-helper/fubon-etf-holdings-manual",
            "Accept-Language": "zh-TW,zh;q=0.9,en;q=0.7",
        },
    )
    context = ssl.create_default_context()
    if hasattr(ssl, "VERIFY_X509_STRICT"):
        context.verify_flags &= ~ssl.VERIFY_X509_STRICT
    with urlopen(request, timeout=timeout_seconds, context=context) as response:
        encoding = response.headers.get_content_charset() or "utf-8-sig"
        return response.read().decode(encoding, "replace")


def _visible_text(raw_html: str) -> str:
    text = re.sub(r"(?is)<(script|style).*?</\1>", " ", raw_html)
    text = re.sub(r"(?i)<br\s*/?>", " ", text)
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    text = unescape(text)
    return _clean_text(text)


def _parse_date(text: str) -> str:
    match = re.search(r"資料日期[:：]?\s*(\d{4})[/-](\d{1,2})[/-](\d{1,2})", text)
    if not match:
        match = re.search(r"(\d{4})[/-](\d{1,2})[/-](\d{1,2})", text)
    if not match:
        return ""
    year, month, day = (int(part) for part in match.groups())
    return f"{year:04d}-{month:02d}-{day:02d}"


def _cell_key(value: Any) -> str:
    return _clean_text(str(value or ""))


def _clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", unescape(value or "")).strip()


def _ticker(value: Any) -> str:
    return str(value or "").strip().upper()


def _float_or_none(value: Any) -> float | None:
    text = str(value or "").strip().replace(",", "").replace("%", "")
    if not text:
        return None
    try:
        return float(text)
    except (TypeError, ValueError):
        return None

from __future__ import annotations

import html
import re
import ssl
import urllib.parse
import urllib.request
from dataclasses import dataclass
from html.parser import HTMLParser
from typing import Any


TWSE_ETF_DIVIDEND_LIST_URL = "https://www.twse.com.tw/zh/ETFortune/dividendList"
YAHOO_DIVIDEND_URL_TEMPLATE = "https://tw.stock.yahoo.com/quote/{symbol}/dividend"


@dataclass
class EtfDividendRecord:
    ticker: str
    name: str
    ex_dividend_date: str
    record_date: str
    payout_date: str
    dividend: float | None
    announcement_year: str
    composition_text: str
    source_url: str
    source: str = "twse_etfortune"

    def as_dict(self) -> dict[str, Any]:
        return {
            "ticker": self.ticker,
            "name": self.name,
            "ex_dividend_date": self.ex_dividend_date,
            "record_date": self.record_date,
            "payout_date": self.payout_date,
            "dividend": self.dividend,
            "announcement_year": self.announcement_year,
            "composition_text": self.composition_text,
            "source_url": self.source_url,
            "source": self.source,
        }


class _DividendTableParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.rows: list[dict[str, Any]] = []
        self._in_row = False
        self._in_cell = False
        self._cell_chunks: list[str] = []
        self._cells: list[str] = []
        self._detail_chunks: list[str] = []
        self._detail_depth = 0
        self._capture_detail = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_map = dict(attrs)
        if tag == "tr":
            self._in_row = True
            self._cells = []
            self._detail_chunks = []
        elif self._in_row and tag == "td":
            self._in_cell = True
            self._cell_chunks = []
        elif self._in_row and tag == "div" and "percentage-data" in str(attr_map.get("class", "")):
            self._capture_detail = True
            self._detail_depth = 1
        elif self._capture_detail and tag == "div":
            self._detail_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if self._capture_detail and tag == "div":
            self._detail_depth -= 1
            if self._detail_depth <= 0:
                self._capture_detail = False
        if self._in_row and self._in_cell and tag == "td":
            self._cells.append(_normalize_space("".join(self._cell_chunks)))
            self._in_cell = False
        elif self._in_row and tag == "tr":
            if len(self._cells) >= 8 and self._cells[0].strip():
                self.rows.append(
                    {
                        "cells": self._cells[:8],
                        "composition_text": _normalize_space(" ".join(self._detail_chunks)),
                    }
                )
            self._in_row = False

    def handle_data(self, data: str) -> None:
        if self._in_cell:
            self._cell_chunks.append(data)
        if self._capture_detail:
            self._detail_chunks.append(data)


def fetch_twse_etf_dividends(
    ticker: str,
    start_year: int | None = None,
    end_year: int | None = None,
) -> list[EtfDividendRecord]:
    ticker = str(ticker).strip().upper()
    if not ticker:
        raise ValueError("ticker is required")
    params: dict[str, str] = {"stkNo": ticker}
    if start_year is not None:
        params["startDate"] = str(start_year)
    if end_year is not None:
        params["endDate"] = str(end_year)
    source_url = TWSE_ETF_DIVIDEND_LIST_URL + "?" + urllib.parse.urlencode(params)
    page = _fetch_text(source_url)

    parser = _DividendTableParser()
    parser.feed(page)

    records: list[EtfDividendRecord] = []
    seen: set[tuple[str, str, str, str, float | None]] = set()
    for row in parser.rows:
        cells = row["cells"]
        if cells[0].upper() != ticker:
            continue
        dividend = _parse_float(cells[5])
        key = (cells[0], cells[2], cells[3], cells[4], dividend)
        if key in seen:
            continue
        seen.add(key)
        records.append(
            EtfDividendRecord(
                ticker=cells[0],
                name=cells[1],
                ex_dividend_date=_parse_twse_minguo_date(cells[2]),
                record_date=_parse_twse_minguo_date(cells[3]),
                payout_date=_parse_twse_minguo_date(cells[4]),
                dividend=dividend,
                announcement_year=cells[7],
                composition_text=str(row.get("composition_text") or ""),
                source_url=source_url,
                source="twse_etfortune",
            )
        )
    return records


def fetch_yahoo_stock_dividends(ticker: str, suffix: str = ".TW") -> list[EtfDividendRecord]:
    ticker = str(ticker).strip().upper()
    if not ticker:
        raise ValueError("ticker is required")
    symbol = ticker if "." in ticker else f"{ticker}{suffix}"
    source_url = YAHOO_DIVIDEND_URL_TEMPLATE.format(symbol=urllib.parse.quote(symbol, safe="."))
    page = _fetch_text(source_url)
    name = _parse_yahoo_name(page, ticker)
    rows = _parse_yahoo_dividend_rows(page)
    records: list[EtfDividendRecord] = []
    seen: set[tuple[str, str, float | None]] = set()
    for row in rows:
        ex_date = _parse_slash_date(row["ex_dividend_date"])
        if not ex_date:
            continue
        dividend = _parse_float(row["dividend"])
        key = (ticker, ex_date, dividend)
        if key in seen:
            continue
        seen.add(key)
        records.append(
            EtfDividendRecord(
                ticker=ticker,
                name=name,
                ex_dividend_date=ex_date,
                record_date="",
                payout_date=_parse_slash_date(row.get("payout_date", "")),
                dividend=dividend,
                announcement_year=_period_to_year(row.get("period", "")),
                composition_text=f"period={row.get('period', '')}; yield={row.get('cash_yield', '')}; fill_days={row.get('fill_days', '')}",
                source_url=source_url,
                source="yahoo_historical",
            )
        )
    return sorted(records, key=lambda record: record.ex_dividend_date, reverse=True)


def parse_twse_etf_dividend_tsv(text: str, source: str = "manual") -> list[EtfDividendRecord]:
    records: list[EtfDividendRecord] = []
    seen: set[tuple[str, str, str, str, float | None]] = set()
    for raw_line in str(text or "").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        cells = [cell.strip() for cell in line.split("\t")]
        if len(cells) < 8:
            continue
        dividend = _parse_float(cells[5])
        key = (cells[0].upper(), cells[2], cells[3], cells[4], dividend)
        if key in seen:
            continue
        seen.add(key)
        records.append(
            EtfDividendRecord(
                ticker=cells[0].upper(),
                name=cells[1],
                ex_dividend_date=_parse_twse_minguo_date(cells[2]),
                record_date=_parse_twse_minguo_date(cells[3]),
                payout_date=_parse_twse_minguo_date(cells[4]),
                dividend=dividend,
                announcement_year=cells[7],
                composition_text="",
                source_url="",
                source=source,
            )
        )
    return records


def _parse_yahoo_dividend_rows(page: str) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    pattern = re.compile(r">\s*(\d{4}(?:Q[1-4]|H[12]|M(?:1[0-2]|[1-9]))?)\s*<")
    for match in pattern.finditer(page):
        chunk = page[match.start() : match.start() + 2400]
        values = [html.unescape(value).strip() for value in re.findall(r">([^<>]+)<", chunk)]
        values = [_normalize_space(value) for value in values if _normalize_space(value)]
        try:
            index = values.index(match.group(1))
        except ValueError:
            continue
        fields = values[index : index + 10]
        if len(fields) < 8:
            continue
        row = {
            "period": fields[0],
            "dividend": fields[1],
            "stock_dividend": fields[2] if len(fields) > 2 else "",
            "cash_yield": fields[3] if len(fields) > 3 else "",
            "prev_close": fields[4] if len(fields) > 4 else "",
            "ex_dividend_date": fields[5] if len(fields) > 5 else "",
            "ex_right_date": fields[6] if len(fields) > 6 else "",
            "payout_date": fields[7] if len(fields) > 7 else "",
            "stock_payout_date": fields[8] if len(fields) > 8 else "",
            "fill_days": fields[9] if len(fields) > 9 else "",
        }
        if re.match(r"^\d{4}/\d{2}/\d{2}$", row["ex_dividend_date"]):
            rows.append(row)
    return rows


def _parse_yahoo_name(page: str, ticker: str) -> str:
    title_match = re.search(r"<title>([^<]+)", page)
    if title_match:
        title = html.unescape(title_match.group(1))
        title = re.sub(r"\([^)]*\).*", "", title).strip()
        if title:
            return title
    return ticker


def _parse_slash_date(value: str) -> str:
    text = _normalize_space(value)
    match = re.match(r"^(\d{4})/(\d{2})/(\d{2})$", text)
    if not match:
        return ""
    return f"{match.group(1)}-{match.group(2)}-{match.group(3)}"


def _period_to_year(value: str) -> str:
    match = re.match(r"^(\d{4})", str(value or ""))
    return match.group(1) if match else ""


def _fetch_text(url: str) -> str:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) StockDailyHelper/1.0",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=25) as response:
            return response.read().decode("utf-8", errors="replace")
    except ssl.SSLError:
        context = ssl._create_unverified_context()
        with urllib.request.urlopen(request, timeout=25, context=context) as response:
            return response.read().decode("utf-8", errors="replace")
    except urllib.error.URLError as exc:
        if "CERTIFICATE_VERIFY_FAILED" not in str(exc):
            raise
        context = ssl._create_unverified_context()
        with urllib.request.urlopen(request, timeout=25, context=context) as response:
            return response.read().decode("utf-8", errors="replace")


def _parse_twse_minguo_date(value: str) -> str:
    text = _normalize_space(value)
    match = re.match(r"^(\d{2,3})年(\d{1,2})月(\d{1,2})日$", text)
    if not match:
        return ""
    year = int(match.group(1)) + 1911
    month = int(match.group(2))
    day = int(match.group(3))
    return f"{year:04d}-{month:02d}-{day:02d}"


def _parse_float(value: str) -> float | None:
    text = _normalize_space(value).replace(",", "")
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _normalize_space(value: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(str(value))).strip()

#!/usr/bin/env python3
"""Build static KOSPI/KOSDAQ market-cap heatmaps from Naver Finance PC ranking.

Uses publicly readable, undocumented HTML; subject to availability and use terms.
No credentials, secrets or user information are used or transmitted.
Never publish fabricated values or overwrite snapshots after a failed collection.
"""
from __future__ import annotations

import datetime as dt
from html.parser import HTMLParser
import html
import json
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data"
PAGE_URL = "https://finance.naver.com/sise/sise_market_sum.naver?sosok={sosok}&page={page}"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.5",
}
CODE_RE = re.compile(r"(?:[?&]code=)([0-9]{6})(?:&|$)")
PAGE_RE = re.compile(r"(?:[?&]|&amp;)page=(\d+)")


class NaverRankingParser(HTMLParser):
    """Parse the public '시가총액' table, independent of presentation classes."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.rows = []
        self.in_tr = False
        self.cells = []
        self.cell = None
        self.cell_type = None
        self.cell_depth = 0
        self.current_code = None
        self.name_cell_index = None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "tr":
            self.in_tr = True
            self.cells = []
            self.current_code = None
            self.name_cell_index = None
        elif self.in_tr and tag in ("td", "th") and self.cell is None:
            self.cell = []
            self.cell_type = tag
            self.cell_depth = 1
        elif self.cell is not None:
            if tag in ("td", "th"):
                self.cell_depth += 1
            if tag == "a":
                href = html.unescape(attrs.get("href", ""))
                m = CODE_RE.search(href)
                if m and self.current_code is None:
                    self.current_code = m.group(1)
                    self.name_cell_index = len(self.cells)

    def handle_data(self, data):
        if self.cell is not None:
            self.cell.append(data)

    def handle_endtag(self, tag):
        if self.cell is not None and tag in ("td", "th"):
            self.cell_depth -= 1
            if self.cell_depth == 0:
                content = " ".join("".join(self.cell).split())
                self.cells.append((self.cell_type, content))
                self.cell = None
                self.cell_type = None
        elif tag == "tr" and self.in_tr:
            if self.current_code and self.name_cell_index is not None:
                stock = self._parse_row()
                if stock:
                    self.rows.append(stock)
            self.in_tr = False
            self.cells = []

    def _parse_row(self):
        vals = [text for _, text in self.cells]
        # PC 시가총액 목록: N | 종목명 | 현재가 | 전일비 | 등락률 | 액면가 | 시가총액(억원)...
        if len(vals) < 7:
            return None
        code = self.current_code
        name_idx = self.name_cell_index
        if name_idx is None or name_idx >= len(vals):
            return None
        name = vals[name_idx]
        if not name or len(name) > 70 or not re.fullmatch(r"\d{6}", code):
            return None
        rate = None
        for candidate in vals[name_idx + 1 : min(len(vals), name_idx + 6)]:
            value = candidate.replace("−", "-").replace("＋", "+").replace(" ", "")
            if re.fullmatch(r"[+-]?\d+(?:\.\d+)?%", value):
                rate = float(value[:-1])
                break
        if rate is None or not -100 <= rate <= 100:
            return None
        # Known Naver ranking layout: market cap is two cells after fluctuation %.
        # Name at 1, % at 4, market cap at 6; fallback uses header-independent % position.
        pct_idx = next((i for i, s in enumerate(vals) if s.replace(" ", "").replace("−", "-").endswith("%") and i > name_idx), None)
        if pct_idx is None:
            return None
        cap_idx = pct_idx + 2
        if cap_idx >= len(vals):
            return None
        cap_str = vals[cap_idx].replace(",", "").replace(" ", "")
        if not cap_str.isdecimal():
            return None
        cap = int(cap_str)
        if cap <= 0:
            return None
        price_str = vals[name_idx + 1].replace(",", "")
        price = int(price_str) if price_str.isdecimal() else None
        result = {"code": code, "name": name, "marketCap": cap, "change": round(rate, 3)}
        if price is not None:
            result["price"] = price
        return result


def get_page(market: str, page: int) -> str:
    url = PAGE_URL.format(sosok=(0 if market == "KOSPI" else 1), page=page)
    req = urllib.request.Request(url, headers={**HEADERS, "Referer": "https://finance.naver.com/sise/"})
    errors = []
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=22) as res:
                if res.status != 200:
                    raise ValueError(f"HTTP {res.status}")
                raw = res.read(900_000)
                if len(raw) >= 900_000:
                    raise ValueError("Unexpected oversized HTML response")
                # Classic Naver Finance PC pages use EUC-KR.
                charset = res.headers.get_content_charset() or "euc-kr"
                try:
                    return raw.decode(charset)
                except (LookupError, UnicodeDecodeError):
                    return raw.decode("euc-kr", errors="replace")
        except (urllib.error.URLError, ValueError, TimeoutError) as ex:
            errors.append(f"{type(ex).__name__}: {ex}")
            if attempt != 2:
                time.sleep(1.4 * (attempt + 1))
    raise RuntimeError(f"{market} page {page}: {' / '.join(errors)}")


def last_page_number(html_source: str) -> int | None:
    # Last-page navigation control in Naver PC list (pgRR).
    match = re.search(r'<td\b[^>]*class=["\'][^"\']*\bpgRR\b[^"\']*["\'][^>]*>(.*?)</td>', html_source, re.I | re.S)
    if not match:
        return None
    nums = [int(n) for n in PAGE_RE.findall(html.unescape(match.group(1)))]
    return max(nums) if nums else None


def collect(market: str):
    first_html = get_page(market, 1)
    parser = NaverRankingParser()
    parser.feed(first_html)
    if len(parser.rows) < 10:
        raise ValueError(f"{market}: Could not parse Naver market-cap ranking (page 1; {len(parser.rows)} valid rows)")
    end = last_page_number(first_html)
    if end is not None and not 1 <= end <= 100:
        raise ValueError(f"{market}: Unexpected last page {end}")
    stocks = {}
    for row in parser.rows:
        stocks[row["code"]] = row
    # If pgRR is unavailable, stop at the first empty page; otherwise collect every
    # page to the advertised last page so '전체' truly covers the scraped market.
    limit = end if end is not None else 100
    page = 2
    while page <= limit:
        time.sleep(.15)
        source = get_page(market, page)
        p = NaverRankingParser()
        p.feed(source)
        if not p.rows:
            if end is not None:
                raise ValueError(f"{market}: Missing rows on page {page} of {end}")
            break
        was = len(stocks)
        for row in p.rows:
            stocks[row["code"]] = row
        if len(stocks) == was:
            if end is not None:
                raise ValueError(f"{market}: Duplicate page {page} of {end}")
            break
        if len(p.rows) < 40:
            if end is not None and page < end:
                raise ValueError(f"{market}: Unexpectedly short page {page} of {end}")
            break
        page += 1
    else:
        if end is None:
            raise ValueError(f"{market}: Reached 100 pages without verifying list completion")
    ordered = sorted(stocks.values(), key=lambda row: row["marketCap"], reverse=True)
    if len(ordered) < 200:
        raise ValueError(f"{market}: Only {len(ordered)} rows. Refusing partial '전체' market list")
    print(f"{market}: {len(ordered)} distinct stocks scraped; final page={end or page}, total cap={sum(x['marketCap'] for x in ordered)} (100m KRW)")
    return ordered


def main():
    result = {}
    timestamp = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    for market in ("KOSPI", "KOSDAQ"):
        rows = collect(market)
        result[market] = {
            "market": market,
            "updatedAt": timestamp,
            "source": "Naver Finance PC market capitalization ranking (unofficial)",
            "unit": "100millionKRW",
            "realtime": False,
            "stocks": rows,
        }
    # Write only after *both* markets succeeded. Failed runs preserve old data.
    OUT.mkdir(parents=True, exist_ok=True)
    for market, value in result.items():
        (OUT / f"{market.lower()}.json").write_text(json.dumps(value, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"DATA COLLECTION FAILED (snapshot not overwritten): {exc}", file=sys.stderr)
        raise SystemExit(1)

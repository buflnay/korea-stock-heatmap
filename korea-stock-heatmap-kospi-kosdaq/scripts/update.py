#!/usr/bin/env python3
"""KOSPI/KOSDAQ heatmap snapshots from Naver's public, undocumented JSON feeds.

No passwords, cookies or API keys. No synthetic stock values are ever published.
A successful *complete* fetch for BOTH markets is required before files change.
"""
from __future__ import annotations

import datetime as dt
import json
import math
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlencode

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'data'
PAGE_SIZE = 100
MAX_PAGES = 80
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                  'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36',
    'Accept': 'application/json, text/plain, */*',
    'Accept-Language': 'ko-KR,ko;q=0.9,en;q=0.7',
    'Referer': 'https://m.stock.naver.com/',
}


def number(value):
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, dict):
        value = value.get('value', value.get('closePrice'))
    value = str(value).strip().replace(',', '').replace(' ', '')
    value = value.replace('−', '-').replace('＋', '+').replace('%', '')
    if not re.fullmatch(r'[+-]?(?:\d+\.?\d*|\.\d+)', value):
        return None
    n = float(value)
    return n if math.isfinite(n) else None


def market_cap_in_100m(raw_value, displayed_value=None):
    """Convert Naver market caps to 100-million KRW units.

    IMPORTANT: Naver's current ``marketValueRaw`` is in *won* (KRW).
    The human-readable marketValue/marketValueHangeul fields are for display
    and must NOT be blindly assumed to use the same unit.
    """
    raw = number(raw_value)
    if raw is not None and raw >= 100_000_000:
        return round(raw / 100_000_000, 4)

    value = displayed_value
    if isinstance(value, str) and ('조' in value or '억' in value):
        trillion = re.search(r'([\d,]+(?:\.\d+)?)\s*조', value)
        hundred_million = re.search(r'([\d,]+(?:\.\d+)?)\s*억', value)
        cap = (float(trillion.group(1).replace(',', '')) * 10000 if trillion else 0)
        cap += float(hundred_million.group(1).replace(',', '')) if hundred_million else 0
        return round(cap, 4) if cap > 0 else None

    # Only used if rawValue is absent: the displayed Naver marketValue
    # numeric field is in 100-million-won units, not plain KRW.
    n = number(value)
    return round(n, 4) if n is not None and n > 0 else None


def parse_stock(record):
    if not isinstance(record, dict):
        return None
    code = str(record.get('itemCode') or record.get('stockCode') or record.get('symbolCode') or record.get('code') or '')
    if code.startswith('A') and re.fullmatch(r'A\d{6}', code):
        code = code[1:]
    if not re.fullmatch(r'\d{6}', code):
        return None
    name = str(record.get('stockName') or record.get('itemName') or record.get('name') or '').strip()
    if not (1 <= len(name) <= 80):
        return None
    cap = market_cap_in_100m(
        record.get('marketValueRaw'),
        record.get('marketValueHangeul') or record.get('marketValue'),
    )
    if cap is None:
        return None
    change = number(record.get('fluctuationsRatio', record.get('changeRate', record.get('changeRatio'))))
    if change is None or abs(change) > 100:
        return None
    # Some feeds express the magnitude as a positive number, and direction separately.
    direction = record.get('compareToPreviousPrice') or record.get('fluctuationsType')
    if isinstance(direction, dict):
        direction = direction.get('name', direction.get('code'))
    direction = str(direction or '').upper()
    if direction in {'FALLING', 'DOWN', 'LOWER', '5', '하락'} and change > 0:
        change = -change
    price = number(record.get('closePriceRaw') or record.get('closePrice') or record.get('currentPrice'))
    stock = {'code': code, 'name': name, 'marketCap': cap, 'change': round(change, 3)}
    if price is not None and price >= 0:
        stock['price'] = round(price, 3)
    return stock


def get_json(url):
    request = urllib.request.Request(url, headers=HEADERS)
    failures = []
    for attempt in range(3):
        try:
            with urllib.request.urlopen(request, timeout=22) as response:
                body = response.read(3_000_001)
                if len(body) > 3_000_000:
                    raise ValueError('Unexpectedly large API response')
                if response.status != 200:
                    raise ValueError(f'HTTP {response.status}')
            return json.loads(body.decode('utf-8-sig'))
        except (urllib.error.URLError, TimeoutError, ValueError, UnicodeDecodeError) as exc:
            failures.append(f'{type(exc).__name__}: {str(exc)[:200]}')
            if attempt < 2:
                time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(' | '.join(failures))


def extract(payload):
    """Accept the documented stocks[] response and a few wrapper variations."""
    if isinstance(payload, list):
        return payload, None
    if not isinstance(payload, dict):
        raise ValueError(f'Unexpected JSON type: {type(payload).__name__}')
    candidates = [payload]
    for key in ('result', 'data', 'output'):
        if isinstance(payload.get(key), dict):
            candidates.append(payload[key])
    for section in candidates:
        for key in ('stocks', 'items', 'stockList', 'list'):
            if isinstance(section.get(key), list):
                raw_total = section.get('totalCount', payload.get('totalCount'))
                total = number(raw_total)
                return section[key], int(total) if total is not None else None
    raise ValueError('Cannot find stocks[]/items[]. JSON keys: ' + ','.join(payload.keys()))


def market_url(market, page, api):
    if api == 'mobile':
        return f'https://m.stock.naver.com/api/stocks/marketValue/{market}?' + urlencode({'page': page, 'pageSize': PAGE_SIZE})
    return 'https://m.stock.naver.com/front-api/stock/domestic/stockList?' + urlencode({
        'sortType': 'marketValue', 'category': market, 'page': page, 'pageSize': PAGE_SIZE,
    })


def collect_from_api(market, api):
    found = {}
    expected = None
    for page in range(1, MAX_PAGES + 1):
        if page != 1:
            time.sleep(0.25)
        url = market_url(market, page, api)
        payload = get_json(url)
        items, total = extract(payload)
        if expected is None and total is not None:
            expected = total
        if not items:
            if expected is not None and len(found) >= expected * 0.95:
                break
            raise ValueError(f'{market} page {page}: empty listing; got {len(found)} of expected {expected}')
        added = 0
        for item in items:
            parsed = parse_stock(item)
            if parsed is not None:
                if parsed['code'] not in found:
                    added += 1
                found[parsed['code']] = parsed
        print(f'{market} {api} page {page}: {len(items)} raw, {added} new valid, total {len(found)}, API count {expected}', flush=True)
        if page == 1 and added < 10:
            sample = items[0] if items and isinstance(items[0], dict) else {}
            safe_fields = ('itemCode', 'stockName', 'itemName', 'marketValueRaw',
                           'marketValue', 'marketValueHangeul', 'fluctuationsRatio',
                           'closePriceRaw')
            sample_values = {key: sample.get(key) for key in safe_fields if key in sample}
            raise ValueError(f'Cannot parse Naver stocks; first record PUBLIC fields={sample_values}')
        if added == 0:
            raise ValueError(f'{market}: duplicate/unparseable API page {page}')
        if expected is not None:
            if len(found) >= expected:
                break
            # Some returned entries may be malformed or halted; never silently
            # claim an incomplete list as 'all'.
            if page * PAGE_SIZE >= expected and len(items) < PAGE_SIZE:
                break
        elif len(items) < PAGE_SIZE:
            break
    else:
        raise ValueError(f'{market}: more than {MAX_PAGES} pages; refusing incomplete list')

    if len(found) < 200:
        raise ValueError(f'{market}: only {len(found)} parseable rows, need at least 200')
    if expected is not None and len(found) < expected * .95:
        raise ValueError(f'{market}: incomplete listing: {len(found)} of {expected} items (<95%)')
    ordered = sorted(found.values(), key=lambda item: item['marketCap'], reverse=True)
    print(f'{market}: complete snapshot, {len(ordered)} companies via {api}', flush=True)
    return ordered


def collect(market):
    errors = []
    for api in ('mobile', 'front'):
        try:
            return collect_from_api(market, api)
        except Exception as exc:
            errors.append(f'{api}: {exc}')
            print(f'{market} {api} unavailable: {exc}', file=sys.stderr, flush=True)
    raise RuntimeError(f'{market}: both public JSON routes failed. ' + ' ; '.join(errors))


def main():
    generated = {}
    timestamp = dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds')
    for market in ('KOSPI', 'KOSDAQ'):
        stocks = collect(market)
        generated[market] = {
            'market': market,
            'updatedAt': timestamp,
            'source': 'Naver mobile market-cap JSON (unofficial)',
            'unit': '100millionKRW',
            'realtime': False,
            'stocks': stocks,
        }
    OUT.mkdir(parents=True, exist_ok=True)
    # Do not modify either snapshot until BOTH markets have been validated.
    for market, data in generated.items():
        dest = OUT / f'{market.lower()}.json'
        dest.write_text(json.dumps(data, ensure_ascii=False, separators=(',', ':')) + '\n', encoding='utf-8')
    print('Both KOSPI and KOSDAQ snapshots generated successfully.', flush=True)


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print('DATA COLLECTION FAILED (existing snapshots preserved):', exc, file=sys.stderr)
        raise SystemExit(1)

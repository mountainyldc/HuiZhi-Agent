# -*- coding: utf-8 -*-
"""港交所披露易爬虫：分窗抓取最近 N 天公告标题入资讯中心。
输出 data/crawled/YYYY-MM-DD-hkex.json
用法: python crawl_hkex.py [--days 45] [--window 10]
"""
import argparse
import datetime
import hashlib
import json
import os
import re
import sys

import requests

from common import project_path

SEARCH_URL = "https://www1.hkexnews.hk/search/titleSearchServlet.do"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"}


def fetch_window(from_date, to_date):
    params = {
        "sortDir": 0, "sortByOptions": "DateTime", "category": 0, "market": "SEHK",
        "stockId": -1, "documentType": -1,
        "fromDate": from_date, "toDate": to_date,
        "title": "", "searchType": 1, "t1code": -2, "t2Gcode": -2, "t2code": -2,
        "rowRange": 100, "lang": "zh",
    }
    r = requests.get(SEARCH_URL, params=params, headers=HEADERS, timeout=25)
    r.raise_for_status()
    res = r.json().get("result")
    if isinstance(res, str) and res and res != "null":
        return json.loads(res)
    return []


def _first_line(s):
    return (re.sub(r"<[^>]+>", "", s or "").strip().splitlines() or [""])[0].strip()


def to_items(rows, default_date):
    out = []
    for it in rows:
        title = _first_line(it.get("LONG_TEXT") or it.get("TITLE") or "")
        if not title:
            continue
        dt = it.get("DATE_TIME") or ""
        m = re.match(r"(\d{2})/(\d{2})/(\d{4})", dt)
        pub = f"{m.group(3)}-{m.group(2)}-{m.group(1)}" if m else default_date
        stock_name = _first_line(it.get("STOCK_NAME") or "")
        key = hashlib.md5((title + dt).encode("utf-8")).hexdigest()
        out.append({
            "id": "hkex_" + key[:10],
            "stock_code": "", "stock_name": stock_name,
            "title": title[:120],
            "url": "",
            "publish_date": pub,
            "source": "港交所披露易",
            "region_hint": "", "keywords_hit": ["资讯"],
            "raw_text": title[:300],
        })
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=45)
    ap.add_argument("--window", type=int, default=10)
    args = ap.parse_args()
    today = datetime.date.today()
    start = today - datetime.timedelta(days=args.days)
    rows = []
    cur = start
    while cur < today:
        end = min(cur + datetime.timedelta(days=args.window), today)
        try:
            page_rows = fetch_window(cur.strftime("%Y%m%d"), end.strftime("%Y%m%d"))
            print(f"[info] {cur}~{end}: {len(page_rows)} 条")
            rows.extend(page_rows)
        except Exception as exc:
            print(f"[warn] {cur}~{end} 失败: {exc}", file=sys.stderr)
        cur = end + datetime.timedelta(days=1)
    items = to_items(rows, start.isoformat())
    out = project_path("data/crawled", today.isoformat() + "-hkex.json")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=2)
    print(f"[result] 港交所披露易 {len(items)} 条 -> {out}")


if __name__ == "__main__":
    main()

# -*- coding: utf-8 -*-
"""商务部机电产品国际招标（中国国际招标网）爬虫：抓取公告/资讯列表。
输出 data/crawled/YYYY-MM-DD-mofcom.json
用法: python crawl_mofcom.py [--columns 67 86]
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

BASE = "http://chinabidding.mofcom.gov.cn"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"}


def fetch_column(column, page=1):
    url = f"{BASE}/channel/column/articleSearch.shtml"
    params = {"column": column, "pageNum": page}
    r = requests.get(url, params=params, headers=HEADERS, timeout=25)
    r.encoding = "gbk"
    r.raise_for_status()
    return r.text


def parse_page(html, source):
    items = []
    seen = set()
    for m in re.finditer(r'<a[^>]+href="(/article/[^"]+)"[^>]*>(.*?)</a>', html, re.S):
        href, inner = m.group(1), m.group(2)
        title = re.sub(r"<[^>]+>", "", inner).strip()
        title = re.sub(r"\s+", " ", title)
        if not title or title in seen:
            continue
        seen.add(title)
        date_m = re.search(r"(\d{4})[-/年](\d{1,2})[-/月](\d{1,2})", html[max(0, m.start() - 300):m.start() + 50])
        if date_m:
            pub = f"{date_m.group(1)}-{int(date_m.group(2)):02d}-{int(date_m.group(3)):02d}"
        else:
            pub = datetime.date.today().isoformat()
        key = hashlib.md5(title.encode("utf-8")).hexdigest()
        items.append({
            "id": "mofcom_" + key[:10],
            "stock_code": "", "stock_name": "",
            "title": title[:120],
            "url": BASE + href if href.startswith("/") else href,
            "publish_date": pub,
            "source": source,
            "region_hint": "", "keywords_hit": ["资讯"],
            "raw_text": title[:300],
        })
    return items


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--columns", nargs="*", default=["67", "86", "82"])
    args = ap.parse_args()
    items = []
    for col in args.columns:
        try:
            html = fetch_column(col)
            col_items = parse_page(html, "商务部机电产品国际招标")
            print(f"[info] column {col}: {len(col_items)} 条")
            items.extend(col_items)
        except Exception as exc:
            print(f"[warn] column {col} 失败: {exc}", file=sys.stderr)
    out = project_path("data/crawled", datetime.date.today().isoformat() + "-mofcom.json")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=2)
    print(f"[result] 商务部国际招标 {len(items)} 条 -> {out}")


if __name__ == "__main__":
    main()

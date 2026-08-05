# -*- coding: utf-8 -*-
"""同花顺财经直播爬虫：全量直播快讯入资讯中心，外汇+粤企命中标记为快讯信号。
输出 data/crawled/YYYY-MM-DD-ths.json
用法: python crawl_ths.py [--pages 8]
"""
import argparse
import csv
import datetime
import hashlib
import json
import os
import re
import sys

import requests

from common import load_config, project_path

FEED_URL = "https://news.10jqka.com.cn/tapp/news/push/stock/"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"}

SIGNAL_KEYWORDS = ["外汇", "汇率", "汇兑", "结售汇", "套保", "套期保值", "出口", "进口", "海外", "境外", "跨境", "美元", "欧元", "日元"]
FX_TAG = "外汇相关"


def load_company_names():
    cfg = load_config()
    names = {}
    with open(project_path(cfg["region"]["allowlist"]), encoding="utf-8") as f:
        for row in csv.DictReader(f):
            code, name = row["stock_code"].strip(), row["stock_name"].strip()
            if code.isdigit():
                names[name] = row["city"].strip()
    return names


def fetch_feed(pages):
    items = []
    for p in range(1, pages + 1):
        try:
            r = requests.get(FEED_URL, params={"page": p, "tag": "", "track": "stock"}, headers=HEADERS, timeout=25)
            r.raise_for_status()
            lst = ((r.json().get("data") or {}).get("list")) or []
            items.extend(lst)
            if len(lst) < 20:
                break
        except Exception as exc:
            print(f"[warn] 第{p}页失败: {exc}", file=sys.stderr)
            break
    return items


def to_items(raw, names):
    today = datetime.date.today().isoformat()
    seen = set()
    out = []
    for it in raw:
        text = (it.get("digest") or it.get("title") or "").strip()
        if not text:
            continue
        clean = re.sub(r"<[^>]+>", "", text)
        key = hashlib.md5(clean.encode("utf-8")).hexdigest()
        if key in seen:
            continue
        seen.add(key)
        hit_name = next((n for n in names if n in clean), "")
        is_signal = any(k in clean for k in SIGNAL_KEYWORDS)
        out.append({
            "id": "ths_" + key[:10],
            "stock_code": "",
            "stock_name": hit_name,
            "title": clean[:120],
            "url": it.get("url") or "",
            "publish_date": today,
            "source": "同花顺财经直播·快讯" if (hit_name and is_signal) else "同花顺财经直播",
            "region_hint": names.get(hit_name, "") if hit_name else "",
            "keywords_hit": (["资讯", FX_TAG] if is_signal else ["资讯"]),
            "raw_text": clean[:500],
        })
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pages", type=int, default=8)
    args = ap.parse_args()
    names = load_company_names()
    raw = fetch_feed(args.pages)
    items = to_items(raw, names)
    out = project_path("data/crawled", datetime.date.today().isoformat() + "-ths.json")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=2)
    n_sig = sum(1 for i in items if "快讯" in i["source"])
    print(f"[result] 同花顺 {len(items)} 条（快讯信号 {n_sig} 条）-> {out}")


if __name__ == "__main__":
    main()

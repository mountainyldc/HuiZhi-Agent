"""抓取引擎：从巨潮资讯抓取公告，归一化为 Announcement JSON。

用法:
  python crawl_cninfo.py                 # 按 config 抓取，写入 data/crawled/YYYY-MM-DD.json
  python crawl_cninfo.py --force-sample  # 强制使用样例数据（兜底/离线演示）
  python crawl_cninfo.py --days 45       # 覆盖日期窗口

失败或零结果时自动回退 data/sample/sample_announcements.json（source=sample）。
"""
import argparse
import datetime
import hashlib
import html
import json
import os
import re
import sys
import time

import requests

from common import load_config, project_path
import settings


QUERY_URL = "http://www.cninfo.com.cn/new/hisAnnouncement/query"
STATIC_PREFIX = "http://static.cninfo.com.cn/"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    "X-Requested-With": "XMLHttpRequest",
    "Referer": "http://www.cninfo.com.cn/new/fulltextSearch",
}


def _clean_title(title):
    """去掉巨潮返回标题里的 <em> 高亮标签。"""
    title = re.sub(r"</?em>", "", title or "")
    return html.unescape(title).strip()


def _query_page(keyword, se_date, page_num, page_size, retries=3):
    last_exc = None
    for attempt in range(1, retries + 1):
        try:
            return _query_page_once(keyword, se_date, page_num, page_size)
        except Exception as exc:
            last_exc = exc
            print(f"[warn] 查询失败(第{attempt}次): {exc}", file=sys.stderr)
            time.sleep(2 * attempt)
    raise last_exc


def _query_page_once(keyword, se_date, page_num, page_size):
    data = {
        "pageNum": str(page_num), "pageSize": str(page_size),
        "column": "szse", "tabName": "fulltext", "plate": "", "stock": "",
        "searchkey": keyword, "secid": "", "category": "", "trade": "",
        "seDate": se_date, "sortName": "", "sortType": "", "isHLtitle": "true",
    }
    resp = requests.post(QUERY_URL, data=data, headers=HEADERS, timeout=25)
    resp.raise_for_status()
    return resp.json()


def _to_announcement(item, keyword):
    ts = item.get("announcementTime")
    pub = datetime.datetime.fromtimestamp(ts / 1000).strftime("%Y-%m-%d") if ts else ""
    adjunct = item.get("adjunctUrl") or ""
    raw_id = f"{item.get('orgId', '')}:{adjunct}"
    ann_id = "cninfo_" + hashlib.md5(raw_id.encode("utf-8")).hexdigest()[:10]
    return {
        "id": ann_id,
        "stock_code": item.get("secCode", ""),
        "stock_name": item.get("secName", ""),
        "title": _clean_title(item.get("announcementTitle", "")),
        "url": STATIC_PREFIX + adjunct if adjunct else "",
        "publish_date": pub,
        "source": "巨潮资讯·公司公告",
        "region_hint": "",
        "keywords_hit": [keyword],
        "raw_text": None,
    }


def crawl(keywords=None, days=None, max_pages=None, column="szse"):
    cfg = load_config()
    crawl_cfg = cfg["crawl"]
    keywords = keywords or settings.effective_keywords(crawl_cfg["keywords"])
    days = days or settings.effective_days_window(crawl_cfg["days_window"])
    max_pages = max_pages or crawl_cfg["max_pages"]
    today = datetime.date.today()
    start = today - datetime.timedelta(days=days)
    se_date = f"{start.isoformat()}~{today.isoformat()}"

    seen = {}
    for kw in keywords:
        for page in range(1, max_pages + 1):
            try:
                j = _query_page(kw, se_date, page, 30)
            except Exception as exc:
                print(f"[warn] 关键词 '{kw}' 第{page}页失败: {exc}", file=sys.stderr)
                break
            items = j.get("announcements") or []
            for it in items:
                ann = _to_announcement(it, kw)
                key = (ann["stock_code"], ann["title"])
                if key in seen:
                    seen[key]["keywords_hit"] = sorted(set(seen[key]["keywords_hit"] + [kw]))
                else:
                    seen[key] = ann
            total = j.get("totalAnnouncement") or 0
            if len(items) < 30 or page * 30 >= total:
                break
        print(f"[info] 关键词 '{kw}': 累计 {len(seen)} 条去重公告")
    return list(seen.values())


def load_sample():
    path = project_path("data/sample/sample_announcements.json")
    with open(path, encoding="utf-8") as f:
        items = json.load(f)
    for it in items:
        it["source"] = "样例数据（非实时抓取）"
    return items


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=None)
    ap.add_argument("--force-sample", action="store_true")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    anns = []
    if not args.force_sample:
        try:
            anns = crawl(days=args.days)
            if not anns:
                print("[warn] 抓取结果为空，回退样例数据", file=sys.stderr)
        except Exception as exc:
            print(f"[warn] 抓取失败({exc})，回退样例数据", file=sys.stderr)

    used_sample = not anns
    if used_sample:
        anns = load_sample()

    out = args.out or project_path(
        "data/crawled", datetime.date.today().isoformat() + ".json"
    )
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(anns, f, ensure_ascii=False, indent=2)

    n_hit = len(anns)
    print(f"[result] source={'sample' if used_sample else 'cninfo'} | {n_hit} 条公告 -> {out}")


if __name__ == "__main__":
    main()
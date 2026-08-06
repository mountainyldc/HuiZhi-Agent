# -*- coding: utf-8 -*-
"""广东省政务/监管类公开信息爬虫（资讯中心补充）：
  - 广东省生态环境厅（建设项目环评公示）
  - 广州市商务局 / 佛山市商务局（通知公示）
  - 广东省投资项目在线审批监管平台（项目公示）
输出 data/crawled/YYYY-MM-DD-gdee.json / -gzsw.json / -fssw.json / -gdtz.json
用法: python crawl_gov_gd.py [--source gdee gzsw fssw gdtz]
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

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"}

SOURCES = {
    "gdee": {
        "name": "广东省生态环境厅",
        "pages": ["https://gdee.gd.gov.cn/hp5629/index.html", "https://gdee.gd.gov.cn/spq5642/index.html"],
        "encoding": "utf-8",
        "date_re": r"\d{4}-\d{2}-\d{2}",
        "verify": True,
    },
    "gzsw": {
        "name": "广州市商务局",
        "pages": ["http://sw.gz.gov.cn/xxgk/tzgg/ywgs/index.html", "http://sw.gz.gov.cn/xxgk/tzgg/tzgg/index.html"],
        "encoding": "utf-8",
        "date_re": r"\d{4}-\d{2}-\d{2}",
        "verify": True,
    },
    "fssw": {
        "name": "佛山市商务局",
        "pages": ["http://fscom.foshan.gov.cn/zwgk/tzgg/index.html", "http://fscom.foshan.gov.cn/"],
        "encoding": "utf-8",
        "date_re": r"\d{4}-\d{2}-\d{2}",
        "verify": True,
    },
    "gdtz": {
        "name": "广东省投资项目在线审批监管平台",
        "pages": ["https://tzxm.gd.gov.cn/shb/tybm/apply2!indexUtilsPage4.action"],
        "encoding": "utf-8",
        "date_re": r"\d{4}-\d{2}-\d{2}",
        "verify": False,
    },
}


def _clean(s):
    s = re.sub(r"<[^>]+>", "", s or "")
    return re.sub(r"\s+", " ", s).strip()


def _extract(html, cfg, base):
    """通用列表解析：抓 <a href> 标题 + 邻近日期。"""
    items, seen = [], set()
    for m in re.finditer(r"<a[^>]+href=[\"']([^\"']+)[\"'][^>]*>(.*?)</a>", html, re.S):
        href, inner = m.group(1), m.group(2)
        title = _clean(inner)
        if not title or len(title) < 4:
            continue
        if not (title.startswith(("关于", "拟对", "公示", "公告", "受理", "批准", "广东省", "广州市", "佛山市", "项目", "202"))):
            continue
        if title in seen:
            continue
        seen.add(title)
        window = html[max(0, m.start() - 260):m.start() + 40]
        dm = re.search(cfg["date_re"], window)
        pub = dm.group(0) if dm else ""
        if not pub:
            # 尝试标题后 60 字符内找日期
            after = html[m.end():m.end() + 80]
            dm2 = re.search(cfg["date_re"], after)
            pub = dm2.group(0) if dm2 else ""
        url = href if href.startswith("http") else (base.rstrip("/") + href if href.startswith("/") else base + href)
        key = hashlib.md5(title.encode("utf-8")).hexdigest()
        items.append({
            "id": f"{cfg['name'][:6]}_{key[:10]}",
            "stock_code": "", "stock_name": "",
            "title": title[:120],
            "url": url,
            "publish_date": pub or datetime.date.today().isoformat(),
            "source": cfg["name"],
            "region_hint": "", "keywords_hit": ["资讯"],
            "raw_text": title[:300],
        })
    return items


def crawl_source(key):
    cfg = SOURCES[key]
    items = []
    for page in cfg["pages"]:
        try:
            r = requests.get(page, headers=HEADERS, timeout=25, verify=cfg.get("verify", True))
            r.encoding = cfg["encoding"]
            r.raise_for_status()
            page_items = _extract(r.text, cfg, page)
            print(f"[info] {key} {page}: {len(page_items)} 条")
            items.extend(page_items)
        except Exception as exc:
            print(f"[warn] {key} {page} 失败: {exc}", file=sys.stderr)
    return items


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", nargs="*", default=list(SOURCES.keys()))
    args = ap.parse_args()
    today = datetime.date.today().isoformat()
    for key in args.source:
        if key not in SOURCES:
            print(f"[warn] 未知来源 {key}", file=sys.stderr)
            continue
        items = crawl_source(key)
        if not items:
            print(f"[warn] {key} 未抓到内容，跳过写入", file=sys.stderr)
            continue
        out = project_path("data/crawled", f"{today}-{key}.json")
        with open(out, "w", encoding="utf-8") as f:
            json.dump(items, f, ensure_ascii=False, indent=2)
        print(f"[result] {SOURCES[key]['name']} {len(items)} 条 -> {out}")


if __name__ == "__main__":
    main()

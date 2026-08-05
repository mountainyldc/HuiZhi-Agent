"""舆情引擎：东方财富全球财经快讯 -> 外汇/汇率相关新闻 -> 匹配广东企业 -> 舆情线索。

产出 Announcement 形状数据（source=东方财富·7x24快讯），写入 data/crawled/YYYY-MM-DD-em.json。
舆情线索为"软信号"：命中广东企业 + 外汇/汇率/出口/海外等关键词即生成，供 rule_screen 走舆情评分路径。

用法:
  python eastmoney_news.py                    # 抓取最近快讯（默认3页）
  python eastmoney_news.py --pages 5
"""
import argparse
import datetime
import hashlib
import json
import os
import re
import sys

import requests

from common import load_config, project_path

FEED_URL = "https://newsapi.eastmoney.com/kuaixun/v1/getlist_102_ajaxResult_50_{page}_.html"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    "Referer": "https://finance.eastmoney.com/",
}

# 舆情关键词：出现即认为与外汇/跨境业务相关
SIGNAL_KEYWORDS = [
    "外汇", "汇率", "汇兑", "结售汇", "套保", "套期保值",
    "出口", "进口", "海外", "境外", "跨境", "美元", "欧元", "日元",
]


def load_company_names():
    cfg = load_config()
    names = set()
    with open(project_path(cfg["region"]["allowlist"]), encoding="utf-8") as f:
        for line in f:
            parts = line.strip().split(",")
            if len(parts) >= 2 and parts[0].isdigit():
                names.add(parts[1].strip())
    return names


def fetch_feed(pages=3):
    items = []
    for page in range(1, pages + 1):
        try:
            r = requests.get(FEED_URL.format(page=page), headers=HEADERS, timeout=25)
            r.raise_for_status()
            text = r.text
            if text.startswith("\ufeff"):
                text = text[1:]
            m = re.search(r"var ajaxResult\s*=\s*(\{.*\})\s*;?\s*$", text, re.S)
            if not m:
                m = re.search(r"(\{.*\})", text, re.S)
            j = json.loads(m.group(1)) if m else {}
            lst = j.get("LivesList") or []
            items.extend(lst)
            if len(lst) < 50:
                break
        except Exception as exc:
            print(f"[warn] 快讯第{page}页失败: {exc}", file=sys.stderr)
            break
    return items


def to_signals(items, names):
    today = datetime.date.today().isoformat()
    seen = set()
    out = []
    for it in items:
        text = (it.get("digest") or it.get("title") or "").strip()
        if not text:
            continue
        if not any(k in text for k in SIGNAL_KEYWORDS):
            continue
        hit_name = next((n for n in names if n in text), None)
        if not hit_name:
            continue
        key = (hit_name, text[:60])
        if key in seen:
            continue
        seen.add(key)
        raw = re.sub(r"<[^>]+>", "", text)
        sig_id = "em_" + hashlib.md5(raw.encode("utf-8")).hexdigest()[:10]
        out.append({
            "id": sig_id,
            "stock_code": "",
            "stock_name": hit_name,
            "title": raw[:80],
            "url": it.get("url_w") or it.get("url_unique") or it.get("url_m") or "",
            "publish_date": today,
            "source": "东方财富·7x24快讯",
            "region_hint": "",
            "keywords_hit": ["舆情"],
            "raw_text": raw,
        })
    return out


def _sample_signals(names):
    """实时快讯无命中时的样例兜底（source 标注样例，避免误导）。"""
    today = datetime.date.today().isoformat()
    samples = [
        ("格力电器", "格力电器：海外自主品牌收入占比提升，公司表示将强化外汇风险管理"),
        ("TCL科技", "TCL科技：半导体显示海外收入占比扩大，汇率波动影响部分被套保对冲"),
        ("迈瑞医疗", "迈瑞医疗：国际业务收入稳步增长，美元结算占比高，公司持续开展远期结汇"),
        ("中兴通讯", "中兴通讯：全球市场收入以美元计价为主，公司通过外汇衍生品管理汇率风险"),
    ]
    out = []
    for name, text in samples:
        if name not in names:
            continue
        sig_id = "em_sample_" + hashlib.md5(text.encode("utf-8")).hexdigest()[:8]
        out.append({
            "id": sig_id, "stock_code": "", "stock_name": name,
            "title": text[:80], "url": "", "publish_date": today,
            "source": "东方财富·7x24快讯（样例）", "region_hint": "",
            "keywords_hit": ["舆情"], "raw_text": text,
        })
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pages", type=int, default=5)
    args = ap.parse_args()
    names = load_company_names()
    items = fetch_feed(args.pages)
    sigs = to_signals(items, names)
    out = project_path("data/crawled", datetime.date.today().isoformat() + "-em.json")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    if not sigs:
        sigs = _sample_signals(names)
        print("[warn] 实时快讯无命中，回退样例舆情（source 已标注样例）", file=sys.stderr)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(sigs, f, ensure_ascii=False, indent=2)
    print(f"[result] 快讯{len(items)}条 -> 舆情线索 {len(sigs)} 条 -> {out}")
    for sig in sigs:
        print(f"  - {sig['stock_name']} | {sig['title'][:50]} | {sig['source']}")


if __name__ == "__main__":
    main()

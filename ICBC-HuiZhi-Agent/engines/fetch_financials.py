"""财报引擎：从巨潮抓取上市公司最近一期定期报告(年报优先)，提取外汇相关财务指标。

用法:
  python fetch_financials.py --company 东鹏饮料
  python fetch_financials.py --company 东鹏饮料 --json
  python fetch_financials.py --company 东鹏饮料 --force   # 忽略缓存重新抓取
"""
import argparse
import datetime
import json
import os
import re

import requests
from pypdf import PdfReader

from common import load_config, project_path

QUERY_URL = "http://www.cninfo.com.cn/new/hisAnnouncement/query"
STATIC_PREFIX = "http://static.cninfo.com.cn/"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    "X-Requested-With": "XMLHttpRequest",
    "Referer": "http://www.cninfo.com.cn/new/fulltextSearch",
}

# 关键词 -> 指标名
KW_RULES = [
    ("汇兑损益", "汇兑损益"),
    ("汇兑收益", "汇兑收益"),
    ("汇兑损失", "汇兑损失"),
    ("境外收入", "境外收入"),
    ("海外收入", "海外收入"),
    ("出口收入", "出口收入"),
    ("境外业务收入", "境外业务收入"),
    ("境外营业收入", "境外营业收入"),
    ("外币报表折算差额", "外币报表折算差额"),
]

AMOUNT_RE = re.compile(r"([-+]?\d[\d,.]*)\s*(万元|亿元|元)")


def _find_report_ann(company):
    """查询巨潮：返回最近一期定期报告公告（优先年度报告，其次半年度报告）。"""
    start = (datetime.date.today() - datetime.timedelta(days=730)).isoformat()
    end = datetime.date.today().isoformat()
    data = {
        "pageNum": "1", "pageSize": "30", "column": "",
        "tabName": "fulltext", "plate": "", "stock": "",
        "searchkey": company, "secid": "", "category": "",
        "trade": "", "seDate": f"{start}~{end}",
        "sortName": "", "sortType": "", "isHLtitle": "true",
    }
    resp = requests.post(QUERY_URL, data=data, headers=HEADERS, timeout=25)
    resp.raise_for_status()
    anns = resp.json().get("announcements") or []
    picked = None
    for it in anns:
        title = re.sub(r"</?em>", "", it.get("announcementTitle") or "")
        if "年度报告" in title and "半年度" not in title and "摘要" not in title and "更正" not in title:
            picked = (it, title, 2)
            break
    if not picked:
        for it in anns:
            title = re.sub(r"</?em>", "", it.get("announcementTitle") or "")
            if "半年度报告" in title and "摘要" not in title:
                picked = (it, title, 1)
                break
    if not picked:
        for it in anns:
            title = re.sub(r"</?em>", "", it.get("announcementTitle") or "")
            if "季度报告" in title and "摘要" not in title:
                picked = (it, title, 0)
                break
    return picked


def _download_pdf(url, dest):
    r = requests.get(url, headers=HEADERS, timeout=60)
    r.raise_for_status()
    with open(dest, "wb") as f:
        f.write(r.content)
    return dest


def _scan_pdf(pdf_path):
    """逐页扫描关键词，返回 {keyword: [(page_no, text)]}。"""
    reader = PdfReader(pdf_path)
    hits = {kw: [] for kw, _ in KW_RULES}
    for i, page in enumerate(reader.pages, start=1):
        try:
            text = page.extract_text() or ""
        except Exception:
            continue
        for kw, _ in KW_RULES:
            if kw in text:
                hits[kw].append((i, text))
    return hits


def _extract_value(text):
    m = AMOUNT_RE.search(text)
    if not m:
        return None
    num = float(m.group(1).replace(",", ""))
    unit = m.group(2)
    if unit == "亿元":
        num = num * 10000
    elif unit == "元":
        num = num / 10000
    return round(num, 2)  # 统一为万元


def _extract_huidui(hits):
    """汇兑类专提取：找财务表格数值，跳过解释性文字页。"""
    for kw in ("汇兑损益", "汇兑收益", "汇兑损失"):
        for pg, text in hits.get(kw, []):
            for m in re.finditer(kw, text):
                ctx = text[max(0, m.start() - 80):m.start() + 150]
                if any(x in ctx for x in ("主要原因", "导致", "变动原因", "同比增长")):
                    continue  # 解释性文字，跳过
                after = text[m.end():m.end() + 34]
                m2 = re.search(r"([-+]?\d[\d,.]*)", after)
                if m2:
                    num = float(m2.group(1).replace(",", ""))
                    um = re.search(r"(万元|亿元|元)", after[:10])
                    unit = um.group(1) if um else "元"
                    if unit == "亿元":
                        num = num * 10000
                    elif unit == "元":
                        num = num / 10000
                    num = round(num, 2)
                    if num < 0 or "损失" in text[max(0, m.start() - 12):m.end()]:
                        prefix = "损失"
                    elif "收益" in text[max(0, m.start() - 12):m.end()] or "收益" in kw:
                        prefix = "收益"
                    else:
                        prefix = ""
                    val = f"{prefix} {abs(num)} 万元".strip() if prefix else f"{num} 万元"
                    return {"name": "汇兑损益", "value": val,
                            "note": "财务费用中的汇兑损益", "page": pg}
    return None


def _build_indicators(hits):
    out = []
    hd = _extract_huidui(hits)
    if hd:
        out.append(hd)
    for kw, label in KW_RULES:
        if kw.startswith("汇兑"):
            continue  # 已单独提取
        pages = hits.get(kw, [])
        if not pages:
            continue
        best_val = None
        best_page = pages[0][0]
        for pg, text in pages:
            for m in re.finditer(kw, text):
                ctx = text[max(0, m.start() - 30): m.start() + 120]
                v = _extract_value(ctx)
                if v is not None:
                    best_val, best_page = v, pg
                    break
            if best_val is not None:
                break
        item = {"name": label, "value": f"{best_val} 万元" if best_val is not None else "详见财报",
                "note": "财报披露口径", "page": best_page}
        out.append(item)
    return out


def fetch_financials(company, force=False, cache_dir=None):
    cache_dir = cache_dir or project_path("data/financials")
    os.makedirs(cache_dir, exist_ok=True)
    cache_path = os.path.join(cache_dir, f"{company}.json")
    if not force and os.path.exists(cache_path):
        with open(cache_path, encoding="utf-8") as f:
            return json.load(f)

    picked = _find_report_ann(company)
    if not picked:
        result = {"status": "no_report", "company": company,
                  "message": "未在巨潮找到该公司的定期报告", "indicators": [],
                  "updated_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M")}
    else:
        ann, title, prio = picked
        url = STATIC_PREFIX + ann["adjunctUrl"]
        pdf_path = os.path.join(cache_dir, f"{company}_report.pdf")
        try:
            _download_pdf(url, pdf_path)
            hits = _scan_pdf(pdf_path)
            indicators = _build_indicators(hits)
            year = re.search(r"(20\d{2})年", title)
            result = {
                "status": "ok",
                "company": company,
                "report_year": year.group(1) + (" 年报" if prio == 2 else (" 半年报" if prio == 1 else " 季报")),
                "source": {"title": title, "url": url,
                           "publish_date": datetime.datetime.fromtimestamp(ann.get("announcementTime", 0) / 1000).strftime("%Y-%m-%d") if ann.get("announcementTime") else ""},
                "indicators": indicators,
                "message": "" if indicators else "已解析年报，但未提取到外汇相关指标（可能为扫描件）。",
                "updated_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
            }
        except Exception as exc:
            result = {"status": "error", "company": company,
                      "message": f"年报抓取失败：{exc}", "indicators": [],
                      "updated_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M")}

    with open(cache_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    return result


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--company", required=True)
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    res = fetch_financials(args.company, force=args.force)
    if args.json:
        print(json.dumps(res, ensure_ascii=False))
    else:
        print(f"公司: {res.get('company')} | 报告: {res.get('report_year','-')}")
        print(f"状态: {res.get('status')} {res.get('message','')}")
        for it in res.get("indicators", []):
            print(f"  - {it['name']}: {it['value']} | {it['note']} | 年报第{it['page']}页")
        if res.get("source"):
            print(f"来源: {res['source']['title']}")
            print(f"  {res['source']['url']}")


if __name__ == "__main__":
    main()

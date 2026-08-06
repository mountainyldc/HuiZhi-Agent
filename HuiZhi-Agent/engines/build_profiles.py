# -*- coding: utf-8 -*-
"""企业档案引擎：解析上市公司定期报告中的「公司信息」块，生成企业档案入库。

数据来源：巨潮资讯定期报告（复用 fetch_financials 的下载/缓存）。
字段：法定代表人、注册地址、办公地址、邮编、网址、邮箱、股票代码、注册资本。

用法:
  python build_profiles.py                 # 解析最新队列快照中的 Top 公司
  python build_profiles.py --top 10
  python build_profiles.py --company 东鹏饮料
"""
import argparse
import datetime
import json
import os
import re
import sys

from pypdf import PdfReader

from common import project_path
import fetch_financials
import store

# 已知字段标签（用于截断多行取值与判断字段边界）
LABEL_KEYS = [
    "公司的中文名称", "公司的中文简称", "公司的外文名称缩写", "公司的外文名称",
    "公司的法定代表人", "董事会秘书", "证券事务代表", "姓名", "联系地址",
    "电话", "传真", "电子信箱", "公司注册地址历史变更情况", "公司注册地址的历史变更情况",
    "公司注册地址", "公司办公地址历史变更情况", "公司办公地址的邮政编码", "公司办公地址",
    "公司网址", "报告期内变更情况查询索引",
    "公司选定的信息披露报纸名称", "登载半年度报告的网站地址", "公司半年度报告备置地点",
    "公司股票简况", "股票种类", "股票上市交易所", "股票简称", "股票代码",
    "企业类型", "上市日期", "上市时间", "签字会计师", "会计师事务所办公地址",
    "统一社会信用代码", "公司组织形式", "企业性质",
    "变更前股票简称", "注册地址的邮政编码", "注册地址", "办公地址的邮政编码",
    "办公地址", "A股", "H股",
]


_SECTION_RE = re.compile(r"^[一二三四五六七八九十]+、|^第[一二三四五六七八九十]+节")


def _grab(lines, start_label, exclude_startswith=()):
    """取 start_label 起始的多行值，直到空行、下一个字段标签或章节标题。"""
    idx = None
    for i, ln in enumerate(lines):
        st = ln.strip()
        if st.startswith(start_label) and not any(
            st.startswith(x) for x in exclude_startswith
        ):
            idx = i
            break
    if idx is None:
        return ""
    head = lines[idx]
    rest = head[len(start_label):].strip()
    out = [rest] if rest else []
    for ln in lines[idx + 1:]:
        s = ln.strip()
        if not s:
            break
        if _SECTION_RE.match(s):
            break
        if re.match(r"^\d+\s*/\s*\d+$", s):
            break
        if ("年度报告" in s or "半年度报告" in s) and len(s) < 45:
            break
        if any(s.startswith(k) for k in LABEL_KEYS):
            break
        if len(out) >= 2:
            break
        out.append(s)
    return "".join(out).strip().lstrip("：:")


def _clean_space(s):
    return re.sub(r"\s+", "", s or "").strip()


def _infer_suffix(code):
    if code.startswith(("600", "601", "603", "605", "688", "689")):
        return "SH"
    if code.startswith(("000", "001", "002", "003", "300", "301")):
        return "SZ"
    if code.startswith(("8", "4", "92")):
        return "BJ"
    return ""


def _extract_stock_codes(lines):
    """从「股票代码」/「股票简况」行提取股票代码：支持 605499.SH 与 300438 两种写法。"""
    codes = []
    seen = set()

    def add(code, suffix):
        full = f"{code}.{suffix}" if suffix else code
        if full not in seen:
            seen.add(full)
            codes.append(full)

    for ln in lines:
        if "股票简称" in ln and "股票代码" in ln:
            m = re.search(r"股票代码\s*[:：]?\s*(\d{4,6})(?:\.(SH|SZ|BJ|HK))?", ln)
            if m:
                add(m.group(1), m.group(2) or _infer_suffix(m.group(1)))
                continue
        if re.match(r"^[AH]股", ln) and "交易所" in ln:
            m = re.search(r"[AH]股.{0,40}?(\d{4,6})(?:\.(SH|SZ|BJ|HK))?", ln)
            if m:
                suffix = m.group(2)
                if not suffix:
                    if "上海" in ln or "上交所" in ln:
                        suffix = "SH"
                    elif "深圳" in ln or "深交所" in ln:
                        suffix = "SZ"
                    elif "北京" in ln or "北交所" in ln:
                        suffix = "BJ"
                    elif "香港" in ln or "联交所" in ln:
                        suffix = "HK"
                add(m.group(1), suffix or _infer_suffix(m.group(1)))
    return codes


def parse_report_pdf(pdf_path):
    """解析年报/半年报 PDF 的公司信息块，返回 profile dict（缺字段留空）。"""
    reader = PdfReader(pdf_path)
    lines_all = []
    text_all = []
    for page in reader.pages:
        try:
            t = page.extract_text() or ""
        except Exception:
            t = ""
        text_all.append(t)
        lines_all.extend(t.splitlines())
    lines = [ln.strip() for ln in lines_all if ln.strip()]
    full = "\n".join(text_all)

    def g(label, **kw):
        return _clean_space(_grab(lines, label, **kw))

    def _first_token(v, pattern=None):
        v = v.strip()
        if not v:
            return ""
        if pattern:
            m = re.search(pattern, v)
            return m.group(0) if m else v.split()[0]
        return v.split()[0]

    def _first_email(lines):
        """扫描所有「电子信箱」行，取第一个只含一个 @ 的干净邮箱（跳过两栏粘连行）。"""
        for ln in lines:
            st = ln.strip()
            if not st.startswith("电子信箱"):
                continue
            rest = st[len("电子信箱"):].strip()
            if rest.count("@") == 1:
                m = re.search(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,6}$", rest)
                if m:
                    return m.group(0)
        v = _clean_space(_grab(lines, "电子信箱"))
        m = re.search(r"([\w.+-]+)@([\w.-]+\.[A-Za-z]{2,6})$", v)
        if m:
            return m.group(1) + "@" + m.group(2)
        return ""

    profile = {
        "legal_rep": g("公司的法定代表人"),
        "registered_address": (
            g("公司注册地址", exclude_startswith=("公司注册地址历史变更情况", "公司注册地址的历史变更情况"))
            or g("注册地址")
        ),
        "office_address": (
            g("公司办公地址", exclude_startswith=("公司办公地址历史变更情况", "公司办公地址的历史变更情况"))
            or g("办公地址")
        ),
        "zip_code": g("公司办公地址的邮政编码"),
        "website": _first_token(g("公司网址"), r"https?://[^\s]+"),
        "email": _first_email(lines),
        "stock_codes": "",
        "registered_capital": "",
    }
    codes = _extract_stock_codes(lines)
    if codes:
        profile["stock_codes"] = ", ".join(codes)
    cap = re.search(r"注册资本[:：]?\s*[人民币]*\s*([\d,\.]+)\s*(万亿元|亿元|万元|元)", full)
    if cap:
        profile["registered_capital"] = f"{cap.group(1)} {cap.group(2)}"
    return profile


def build_for_company(company, force=False):
    res = fetch_financials.fetch_financials(company, force=force)
    if res.get("status") != "ok":
        return {"company": company, "status": "no_report", "profile": None,
                "message": res.get("message", "")}
    pdf_path = os.path.join(project_path("data/financials"), f"{company}_report.pdf")
    if not os.path.exists(pdf_path):
        return {"company": company, "status": "no_pdf", "profile": None}
    profile = parse_report_pdf(pdf_path)
    profile["company"] = company
    resolved = fetch_financials.resolve_company(company)
    if resolved:
        code, _org, _zwjc = resolved
        suffix = _infer_suffix(code)
        primary = f"{code}.{suffix}" if suffix else code
        existing = profile.get("stock_codes") or ""
        parts = [x.strip() for x in existing.split(",") if x.strip()]
        if primary not in parts:
            parts.insert(0, primary)
        profile["stock_codes"] = ", ".join(parts)
    src = res.get("source") or {}
    profile.update({
        "source_title": src.get("title", ""),
        "source_url": src.get("url", ""),
        "report_date": src.get("publish_date", ""),
        "updated_at": datetime.datetime.now().isoformat(timespec="seconds"),
    })
    store.upsert_profile(profile)
    return {"company": company, "status": "ok", "profile": profile}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--top", type=int, default=30)
    ap.add_argument("--company", default=None)
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    if args.company:
        companies = [args.company]
    else:
        import ingest_docs
        queue = ingest_docs.load_queue()
        items = sorted(queue.get("items", []), key=lambda x: x.get("score", 0), reverse=True)[:args.top]
        companies = list(dict.fromkeys((it.get("company_name") or "").strip() for it in items if it.get("company_name")))

    out = {"ok": 0, "no_report": 0, "no_pdf": 0, "error": 0, "items": []}
    for c in companies:
        try:
            r = build_for_company(c, force=args.force)
        except Exception as exc:
            r = {"company": c, "status": "error", "profile": None, "message": str(exc)}
        out["items"].append(r)
        out[r.get("status") if r.get("status") in out else "error"] += 1
        print(f"[{r.get('status')}] {c} {r.get('message', '')}")
    print(f"[result] ok {out['ok']} | 无报告 {out['no_report']} | 无PDF {out['no_pdf']} | 失败 {out['error']}")
    manifest = project_path("data/rag/profiles_manifest.json")
    os.makedirs(os.path.dirname(manifest), exist_ok=True)
    with open(manifest, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
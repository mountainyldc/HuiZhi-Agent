# -*- coding: utf-8 -*-
"""P0 文档摄入引擎：下载商机队列 Top 公司的公告 PDF，提取正文入库 documents。

用法:
  python ingest_docs.py                 # 默认最新队列快照 Top 30
  python ingest_docs.py --top 10
  python ingest_docs.py --date 2026-08-05
  python ingest_docs.py --force         # 忽略已入库去重，强制重抓
"""
import argparse
import datetime
import hashlib
import json
import os
import sys
import time

import requests
from pypdf import PdfReader

from common import load_config, project_path
import store

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    "X-Requested-With": "XMLHttpRequest",
    "Referer": "http://www.cninfo.com.cn/new/fulltextSearch",
}
MAX_RAW_CHARS = 500_000  # 单篇正文入库上限，防止 DB 过大


def latest_snapshot():
    snaps_dir = project_path("data/queue_snapshots")
    snaps = sorted(
        (f for f in os.listdir(snaps_dir) if f.endswith(".json")),
        reverse=True,
    )
    if not snaps:
        raise FileNotFoundError("未找到队列快照 data/queue_snapshots/*.json")
    return os.path.join(snaps_dir, snaps[0])


def load_queue(date=None):
    path = latest_snapshot() if not date else project_path(
        "data/queue_snapshots", f"{date}.json"
    )
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def doc_id_for(company, url):
    raw = f"{company}:{url}".encode("utf-8")
    return "doc_" + hashlib.md5(raw).hexdigest()[:12]


def download_pdf(url, dest):
    r = requests.get(url, headers=HEADERS, timeout=60)
    r.raise_for_status()
    with open(dest, "wb") as f:
        f.write(r.content)
    return dest


def extract_pdf_text(pdf_path):
    reader = PdfReader(pdf_path)
    parts = []
    for i, page in enumerate(reader.pages, start=1):
        try:
            txt = page.extract_text() or ""
        except Exception:
            txt = ""
        if txt.strip():
            parts.append(f"\n===== 第{i}页 =====\n" + txt.strip())
    return "\n".join(parts)


def ingest(queue, top=30, force=False):
    items = sorted(
        queue.get("items", []), key=lambda x: x.get("score", 0), reverse=True
    )[:top]
    out = {"ingested": 0, "skipped": 0, "failed": 0, "docs": []}
    for it in items:
        company = (it.get("company_name") or "").strip()
        url = (it.get("evidence_url") or "").strip()
        if not company or not url:
            out["skipped"] += 1
            continue
        doc_id = doc_id_for(company, url)
        if not force and store.get_document(doc_id):
            out["skipped"] += 1
            continue
        pdf_path = os.path.join(project_path("data/rag/pdf"), doc_id + ".pdf")
        os.makedirs(os.path.dirname(pdf_path), exist_ok=True)
        try:
            download_pdf(url, pdf_path)
            text = extract_pdf_text(pdf_path)
            if not text.strip():
                out["failed"] += 1
                print(f"[skip] {company} 正文为空（可能为扫描件），跳过入库", file=sys.stderr)
                continue
            store.upsert_document(
                {
                    "id": doc_id,
                    "company": company,
                    "title": it.get("title", ""),
                    "url": url,
                    "publish_date": it.get("publish_date", ""),
                    "source": it.get("source", "公告"),
                    "doc_type": "announcement",
                    "raw_text": text[:MAX_RAW_CHARS],
                    "created_at": datetime.datetime.now().isoformat(timespec="seconds"),
                }
            )
            out["ingested"] += 1
            out["docs"].append({"id": doc_id, "company": company, "chars": len(text)})
            print(f"[ok] {company} 已入库 {len(text)} 字")
        except Exception as exc:
            out["failed"] += 1
            print(f"[fail] {company} 失败: {exc}", file=sys.stderr)
        time.sleep(0.5)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--top", type=int, default=30)
    ap.add_argument("--date", default=None)
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()
    queue = load_queue(args.date)
    res = ingest(queue, top=args.top, force=args.force)
    print(f"[result] 入库 {res['ingested']} | 跳过 {res['skipped']} | 失败 {res['failed']}")
    manifest = project_path("data/rag/ingest_manifest.json")
    os.makedirs(os.path.dirname(manifest), exist_ok=True)
    with open(manifest, "w", encoding="utf-8") as f:
        json.dump(res, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
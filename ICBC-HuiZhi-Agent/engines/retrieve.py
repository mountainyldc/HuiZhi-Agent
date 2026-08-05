# -*- coding: utf-8 -*-
"""P1 混合检索引擎：SQLite FTS5(BM25) + FAISS 向量 TopK，RRF 融合输出 TopN 证据块。

用法:
  python retrieve.py --query "外汇套保"                  # 全局检索
  python retrieve.py --company 比亚迪 --query "外汇需求"  # 限定公司
  python retrieve.py --company 比亚迪                     # 默认查询=公司名+外汇
  python retrieve.py --top 10 --verbose
"""
import argparse
import json
import os
import re
import sys

import requests

from common import load_config, project_path
import store
from index_docs import _load_embed_key, faiss_read

RRF_K = 60


def embed_query(text, cfg, api_key):
    """查询向量：text_type=query。失败返回 None（降级为纯 BM25）。"""
    try:
        resp = requests.post(
            cfg["rag"]["embedding"]["base_url"],
            json={"model": cfg["rag"]["embedding"]["model"],
                  "input": [text],
                  "parameters": {"text_type": "query",
                                 "dimension": cfg["rag"]["embedding"]["dimension"]}},
            headers={"Authorization": "Bearer " + api_key, "Content-Type": "application/json"},
            timeout=30,
        )
        resp.raise_for_status()
        embs = resp.json().get("data") or []
        return embs[0]["embedding"] if embs else None
    except Exception as exc:
        print(f"[warn] 查询向量化失败，降级为纯 BM25：{exc}", file=sys.stderr)
        return None


def build_fts_query(text):
    """把自然语言查询拆成 >=3 字词元，OR 连接；无词元返回空（跳过 BM25）。"""
    tokens = re.findall(r"[\u4e00-\u9fff]{3,}|[A-Za-z0-9]{3,}", text or "")
    tokens = list(dict.fromkeys(tokens))
    return " OR ".join(tokens) if tokens else ""


def fts_search(cfg, query, company=None, limit=10):
    fts_q = build_fts_query(query)
    if not fts_q:
        return []
    try:
        return store.search_chunks_fts(fts_q, company=company, limit=limit)
    except Exception as exc:
        print(f"[warn] FTS 检索失败：{exc}", file=sys.stderr)
        return []


def vec_search(cfg, api_key, query, company=None, top_k=10):
    """FAISS 向量检索，返回 [(chunk_row, score), ...]，公司过滤在外部完成。"""
    index_path = project_path("data/rag/faiss.index")
    ids_path = project_path("data/rag/faiss_ids.json")
    if not os.path.exists(index_path) or not os.path.exists(ids_path):
        print("[warn] 未找到 FAISS 索引，跳过向量检索", file=sys.stderr)
        return []
    import faiss
    import numpy as np

    vec = embed_query(query, cfg, api_key)
    if vec is None:
        return []
    index = faiss_read(index_path)
    with open(ids_path, encoding="utf-8") as f:
        ids = json.load(f)
    xq = np.asarray([vec], dtype="float32")
    faiss.normalize_L2(xq)
    scores, idxs = index.search(xq, min(top_k, index.ntotal))
    out = []
    for score, pos in zip(scores[0], idxs[0]):
        if pos < 0 or pos >= len(ids):
            continue
        chunk = store.get_chunk_by_id(ids[pos])
        if chunk:
            out.append((chunk, float(score)))
    return out


def fuse(fts_hits, vec_hits, top_n=5):
    scores = {}
    for rank, hit in enumerate(fts_hits):
        cid = hit["id"]
        scores[cid] = scores.get(cid, 0.0) + 1.0 / (RRF_K + rank + 1)
    for rank, (chunk, _score) in enumerate(vec_hits):
        cid = chunk["id"]
        scores[cid] = scores.get(cid, 0.0) + 1.0 / (RRF_K + rank + 1)
    ranked = sorted(scores.items(), key=lambda x: -x[1])
    return [(cid, sc) for cid, sc in ranked[:top_n]]


def retrieve(query, company=None, top_n=5, verbose=False):
    cfg = load_config()
    api_key = _load_embed_key(cfg)
    if not api_key:
        print("[warn] 无 Embedding Key，仅 BM25 检索", file=sys.stderr)

    fts_hits = fts_search(cfg, query, company=company, limit=10)
    vec_hits = []
    if api_key:
        vec_hits = vec_search(cfg, api_key, query, company=company, top_k=10)
        if company and vec_hits:
            vec_hits = [c for c in vec_hits if (c[0].get("company") or "") == company][:10]

    fused = fuse(fts_hits, vec_hits, top_n=top_n)
    chunks_by_id = {}
    for hit in fts_hits:
        chunks_by_id[hit["id"]] = hit
    for chunk, _s in vec_hits:
        chunks_by_id.setdefault(chunk["id"], chunk)

    docs_cache = {}
    results = []
    for cid, sc in fused:
        chunk = chunks_by_id.get(cid)
        if not chunk:
            continue
        doc = docs_cache.get(chunk["doc_id"])
        if doc is None:
            doc = store.get_document(chunk["doc_id"])
            docs_cache[chunk["doc_id"]] = doc
        results.append({
            "chunk_id": cid,
            "score": round(sc, 4),
            "company": chunk.get("company", ""),
            "doc_id": chunk.get("doc_id", ""),
            "title": (doc or {}).get("title", ""),
            "url": (doc or {}).get("url", ""),
            "publish_date": (doc or {}).get("publish_date", ""),
            "source": (doc or {}).get("source", ""),
            "text": chunk.get("text", "")[:600],
        })
    return results


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--query", default=None)
    ap.add_argument("--company", default=None)
    ap.add_argument("--top", type=int, default=5)
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()
    query = args.query or (args.company + " 外汇" if args.company else "")
    if not query:
        print("请提供 --query 或 --company", file=sys.stderr)
        sys.exit(1)
    results = retrieve(query, company=args.company, top_n=args.top, verbose=args.verbose)
    if not results:
        print("[result] 无检索结果")
        sys.exit(0)
    for i, r in enumerate(results, start=1):
        print(f"[{i}] {r['company']} | {r['publish_date']} | {r['title'][:44]}")
        print(f"    score={r['score']} url={r['url'][:80]}")
        print(f"    {r['text'][:120].strip()}")
    print(f"[result] 命中 {len(results)} 条")


if __name__ == "__main__":
    main()
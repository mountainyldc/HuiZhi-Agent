# -*- coding: utf-8 -*-
"""P1 索引引擎：公告正文分块 + 百炼 Embedding + FAISS 向量库 + SQLite FTS5 全文索引。

用法:
  python index_docs.py                  # 全量重建索引（chunks + FTS + FAISS）
  python index_docs.py --company 东鹏饮料
  python index_docs.py --dry-run        # 只打印分块统计，不调用 Embedding API
"""
import argparse
import base64
import json
import os
import re
import sys

import numpy as np
import requests

from common import load_config, project_path
import store

def chunk_text(raw_text, size=800, overlap=120):
    """按段落累积切块，超长段再按字符二次切分（中文按字符近似计 token）。"""
    text = re.sub(r"===== 第\d+页 =====\n?", "", raw_text or "")
    paras = [p.strip() for p in text.splitlines() if p.strip()]
    chunks = []
    buf = ""
    for para in paras:
        if not buf or len(buf) + len(para) + 1 <= size:
            buf = (buf + "\n" + para).strip()
        else:
            chunks.append(buf)
            buf = para
    if buf:
        chunks.append(buf)
    out = []
    for c in chunks:
        while len(c) > size:
            out.append(c[:size])
            c = c[size - overlap:]
        out.append(c)
    return [c for c in out if c.strip()]


def embed_texts(texts, api_key, cfg):
    """调用百炼 text-embedding-v4，分批返回向量列表。"""
    url = cfg["rag"]["embedding"]["base_url"]
    model = cfg["rag"]["embedding"]["model"]
    dim = cfg["rag"]["embedding"]["dimension"]
    batch = cfg["rag"]["embedding"]["batch_size"]
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    vectors = []
    for i in range(0, len(texts), batch):
        batch_texts = texts[i:i + batch]
        body = {
            "model": model,
            "input": batch_texts,
            "parameters": {"text_type": "document", "dimension": dim},
        }
        resp = requests.post(url, json=body, headers=headers, timeout=60)
        resp.raise_for_status()
        data = resp.json()
        embs = data.get("data") or []
        embs.sort(key=lambda x: x.get("index", 0))
        vectors.extend(e.get("embedding") for e in embs)
    return vectors


def faiss_write(index, path):
    """faiss 不兼容中文路径（fopen 按 ANSI 处理），先写 ASCII 临时路径再复制。"""
    import shutil
    import tempfile

    path = os.path.normpath(path)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = os.path.join(tempfile.gettempdir(), "faiss_index_" + os.path.basename(path))
    import faiss
    faiss.write_index(index, tmp)
    shutil.copyfile(tmp, path)


def faiss_read(path):
    import shutil
    import tempfile

    path = os.path.normpath(path)
    tmp = os.path.join(tempfile.gettempdir(), "faiss_index_" + os.path.basename(path))
    shutil.copyfile(path, tmp)
    import faiss
    return faiss.read_index(tmp)


def build_faiss(index_path, ids_path):
    """从全量 doc_chunks 重建 FAISS（IndexFlatIP，L2 归一化）。"""
    index_path = os.path.normpath(index_path)
    ids_path = os.path.normpath(ids_path)
    os.makedirs(os.path.dirname(index_path), exist_ok=True)
    rows = store.get_chunks(limit=100000)
    if not rows:
        for fp in (index_path, ids_path):
            if os.path.exists(fp):
                os.remove(fp)
        return 0
    vecs = []
    ids = []
    for r in rows:
        meta = r.get("meta") or {}
        b64 = meta.get("vec_b64")
        if not b64:
            continue
        v = np.frombuffer(base64.b64decode(b64), dtype="float32")
        vecs.append(v)
        ids.append(r["id"])
    if not vecs:
        return 0
    mat = np.vstack(vecs).astype("float32")
    import faiss
    faiss.normalize_L2(mat)
    index = faiss.IndexFlatIP(mat.shape[1])
    index.add(mat)
    faiss_write(index, index_path)
    with open(ids_path, "w", encoding="utf-8") as f:
        json.dump(ids, f)
    return len(ids)


def _load_embed_key(cfg):
    env = cfg["rag"]["embedding"]["api_key_env"]
    key = os.environ.get(env) or os.environ.get("EMBEDDING_API_KEY")
    if key:
        return key.strip()
    # 兼容：vision skill .env
    candidates = [
        os.path.expanduser(r"~\.codex\skills\claude-vision-skill\.env"),
        os.path.expanduser(r"~\.agents\skills\claude-vision-skill\.env"),
    ]
    for p in candidates:
        if os.path.exists(p):
            for ln in open(p, encoding="utf-8"):
                if ln.strip().startswith("DASHSCOPE_API_KEY="):
                    return ln.strip().split("=", 1)[1].strip()
    return ""


def index_docs(company=None, dry_run=False, force=False):
    cfg = load_config()
    api_key = _load_embed_key(cfg)
    if not api_key and not dry_run:
        print("[error] 未找到 Embedding API Key（环境变量或 vision skill .env）", file=sys.stderr)
        return 1

    docs = store.get_documents(company=company, limit=1000)
    if not docs:
        print("[warn] 没有可索引的公告正文，请先运行 ingest_docs.py", file=sys.stderr)
        return 0

    chunk_size = cfg["rag"]["embedding"]["chunk_size"]
    chunk_overlap = cfg["rag"]["embedding"]["chunk_overlap"]
    total_chunks = 0
    for doc in docs:
        doc_id = doc["id"]
        if not force:
            existing = store.get_chunks(doc_id=doc_id)
            if existing:
                total_chunks += len(existing)
                continue
        store.clear_chunks(doc_id)
        texts = chunk_text(doc.get("raw_text"), size=chunk_size, overlap=chunk_overlap)
        if not texts:
            continue
        if dry_run:
            print(f"[dry] {doc['company']} -> {len(texts)} 块")
            total_chunks += len(texts)
            continue
        try:
            vectors = embed_texts(texts, api_key, cfg)
        except Exception as exc:
            print(f"[fail] {doc['company']} 向量化失败: {exc}", file=sys.stderr)
            continue
        chunks = []
        for i, (text, vec) in enumerate(zip(texts, vectors)):
            chunks.append({
                "doc_id": doc_id,
                "company": doc.get("company", ""),
                "chunk_index": i,
                "text": text,
                "meta": {"vec_b64": base64.b64encode(
                    np.asarray(vec, dtype="float32").tobytes()
                ).decode("ascii")},
            })
        store.upsert_chunks(chunks)
        total_chunks += len(chunks)
        print(f"[ok] {doc['company']} -> {len(chunks)} 块")
    if not dry_run:
        n = build_faiss(project_path("data/rag/faiss.index"), project_path("data/rag/faiss_ids.json"))
        print(f"[result] 索引完成：{total_chunks} 块，FAISS {n} 向量")
    else:
        print(f"[result] dry-run：共 {total_chunks} 块（未调用 API）")
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--company", default=None)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()
    sys.exit(index_docs(company=args.company, dry_run=args.dry_run, force=args.force))


if __name__ == "__main__":
    main()
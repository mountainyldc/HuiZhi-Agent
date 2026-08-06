# -*- coding: utf-8 -*-
"""retrieve.py：FTS 查询构建、RRF 融合、FTS5 检索（样例数据断言）。"""
import store
from retrieve import build_fts_query, fts_search, fuse


def test_build_fts_query_chinese_tokens():
    q = build_fts_query("帮我分析东鹏饮料的外汇需求")
    assert "东鹏饮料" in q
    assert "外汇需求" in q
    assert build_fts_query("ab") == ""


def test_build_fts_query_dedup():
    q = build_fts_query("外汇套保 外汇套保 汇率风险 汇率风险")
    tokens = q.split(" OR ")
    assert tokens.count("外汇套保") == 1
    assert tokens.count("汇率风险") == 1


def test_fuse_dual_hit_ranks_first():
    fts = [{"id": 1}, {"id": 2}]
    vec = [({"id": 2}, 0.9), ({"id": 3}, 0.8)]
    out = fuse(fts, vec, top_n=5)
    ids = [cid for cid, _ in out]
    assert ids[0] == 2  # 双路命中（BM25+向量）排第一
    assert set(ids) == {1, 2, 3}


def test_fuse_top_n_limit():
    fts = [{"id": i} for i in range(10)]
    out = fuse(fts, [], top_n=3)
    assert len(out) == 3


def test_fts_search_with_seeded_chunks(tmp_project):
    store.init_db()
    store.upsert_document({
        "id": "d1", "company": "东鹏饮料", "title": "关于开展外汇衍生品交易的公告",
        "url": "http://example.com/d1", "publish_date": "2026-07-31",
        "source": "cninfo", "doc_type": "公告", "raw_text": "", "created_at": "2026-08-01",
    })
    store.upsert_chunks([{
        "doc_id": "d1", "company": "东鹏饮料", "chunk_index": 0,
        "text": "东鹏饮料开展外汇衍生品交易业务进行套期保值，交易期限一年。", "meta": {},
    }])
    hits = fts_search({}, "东鹏饮料 套期保值", company="东鹏饮料", limit=5)
    assert hits
    assert hits[0]["doc_id"] == "d1"

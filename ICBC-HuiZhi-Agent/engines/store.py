"""SQLite 访问层：公告 / 商机 / 复核 / 生命周期状态机。

生命周期：new(新发现) -> verifying(待核实) -> contacted(已联系)；另有 invalid(标记无效)。
"""
import datetime
import json
import os
import sqlite3

from common import load_config, project_path


def _conn(db_path=None):
    if db_path is None:
        cfg = load_config()
        db_path = project_path(cfg["store"]["db_path"])
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(db_path=None):
    conn = _conn(db_path)
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS announcements(
            id TEXT PRIMARY KEY,
            stock_code TEXT, stock_name TEXT, title TEXT,
            url TEXT, publish_date TEXT, source TEXT,
            region_hint TEXT, keywords_hit TEXT, raw_text TEXT
        );
        CREATE TABLE IF NOT EXISTS opportunities(
            id TEXT PRIMARY KEY,
            announcement_id TEXT,
            company_name TEXT, city TEXT,
            tags TEXT, trigger_event TEXT, rule_hits TEXT,
            score REAL, score_breakdown TEXT,
            lifecycle TEXT, owner TEXT, created_date TEXT,
            biz TEXT
        );
        CREATE TABLE IF NOT EXISTS reviews(
            opportunity_id TEXT PRIMARY KEY,
            review TEXT, reviewed_at TEXT
        );
        CREATE TABLE IF NOT EXISTS documents(
            id TEXT PRIMARY KEY,
            company TEXT, title TEXT, url TEXT, publish_date TEXT,
            source TEXT, doc_type TEXT, raw_text TEXT, created_at TEXT
        );
        CREATE TABLE IF NOT EXISTS doc_chunks(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            doc_id TEXT, company TEXT, chunk_index INTEGER,
            text TEXT, meta TEXT
        );
        CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
            text, company, tokenize='trigram'
        );
        CREATE TABLE IF NOT EXISTS company_profiles(
            company TEXT PRIMARY KEY,
            legal_rep TEXT, registered_address TEXT, office_address TEXT,
            zip_code TEXT, website TEXT, email TEXT, stock_codes TEXT,
            registered_capital TEXT, credit_code TEXT,
            source_title TEXT, source_url TEXT, report_date TEXT, updated_at TEXT
        );
                CREATE TABLE IF NOT EXISTS company_insights(
            company TEXT PRIMARY KEY,
            revenue_scale TEXT, export_ratio TEXT, overseas_subsidiaries TEXT,
            fx_exposure_direction TEXT, hedge_history TEXT, recommended_products TEXT,
            confidence TEXT, source_note TEXT, updated_at TEXT
        );
        CREATE TABLE IF NOT EXISTS conversation_memory(
            id INTEGER PRIMARY KEY, data TEXT, updated_at TEXT
        );
        """
    )
    try:
        conn.execute("ALTER TABLE opportunities ADD COLUMN biz TEXT")
        conn.commit()
    except Exception:
        pass  # 列已存在
    conn.close()


# ---------- 公告 ----------

def upsert_announcements(items):
    conn = _conn()
    for it in items:
        conn.execute(
            """INSERT OR REPLACE INTO announcements
               (id, stock_code, stock_name, title, url, publish_date,
                source, region_hint, keywords_hit, raw_text)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (
                it.get("id"), it.get("stock_code"), it.get("stock_name"),
                it.get("title"), it.get("url"), it.get("publish_date"),
                it.get("source"), it.get("region_hint"),
                json.dumps(it.get("keywords_hit", []), ensure_ascii=False),
                it.get("raw_text"),
            ),
        )
    conn.commit()
    conn.close()
    return len(items)


def list_announcements():
    conn = _conn()
    rows = conn.execute("SELECT * FROM announcements ORDER BY publish_date DESC").fetchall()
    conn.close()
    out = []
    for r in rows:
        d = dict(r)
        d["keywords_hit"] = json.loads(d["keywords_hit"] or "[]")
        out.append(d)
    return out


# ---------- 资讯中心 ----------

def search_announcements(q="", source="", days=45, page=1, page_size=50):
    """资讯中心：按关键词/来源/时间窗口分页查询公告与舆情。"""
    import datetime
    conn = _conn()
    where, args = [], []
    if q:
        like = f"%{q}%"
        where.append("(title LIKE ? OR stock_name LIKE ? OR COALESCE(raw_text,'') LIKE ?)")
        args += [like, like, like]
    if source:
        where.append("source LIKE ?")
        args.append(source + "%")  # 来源用短前缀匹配（如 巨潮资讯）
    if days:
        cutoff = (datetime.date.today() - datetime.timedelta(days=days)).isoformat()
        where.append("COALESCE(publish_date,'') >= ?")
        args.append(cutoff)
    cond = (" WHERE " + " AND ".join(where)) if where else ""
    total = conn.execute("SELECT COUNT(*) FROM announcements" + cond, args).fetchone()[0]
    rows = conn.execute(
        "SELECT * FROM announcements" + cond
        + " ORDER BY publish_date DESC, id DESC LIMIT ? OFFSET ?",
        args + [page_size, (page - 1) * page_size],
    ).fetchall()
    src_rows = conn.execute(
        """SELECT CASE WHEN instr(source,'·')>0 THEN substr(source,1,instr(source,'·')-1)
                       ELSE source END AS src, COUNT(*) c
           FROM announcements GROUP BY src ORDER BY c DESC"""
    ).fetchall()
    conn.close()
    items = []
    for r in rows:
        d = dict(r)
        d["keywords_hit"] = json.loads(d["keywords_hit"] or "[]")
        d["region"] = d.pop("region_hint", "") or ""
        items.append(d)
    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "sources": [{"source": s["src"], "count": s["c"]} for s in src_rows],
        "items": items,
    }


# ---------- 商机 ----------

def insert_opportunity(opp):
    conn = _conn()
    conn.execute(
        """INSERT OR REPLACE INTO opportunities
           (id, announcement_id, company_name, city, tags, trigger_event,
            rule_hits, score, score_breakdown, lifecycle, owner, created_date, biz)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            opp["id"], opp.get("announcement_id"), opp["company_name"],
            opp.get("city"), json.dumps(opp.get("tags", []), ensure_ascii=False),
            opp.get("trigger_event"),
            json.dumps(opp.get("rule_hits", []), ensure_ascii=False),
            opp.get("score", 0),
            json.dumps(opp.get("score_breakdown", {}), ensure_ascii=False),
            opp.get("lifecycle", "new"), opp.get("owner"),
            opp.get("created_date"),
            json.dumps(opp.get("biz", {}), ensure_ascii=False),
        ),
    )
    conn.commit()
    conn.close()
    return opp["id"]


def list_opportunities(lifecycle=None, db_path=None):
    conn = _conn(db_path)
    if lifecycle:
        rows = conn.execute(
            "SELECT * FROM opportunities WHERE lifecycle=? ORDER BY score DESC", (lifecycle,)
        ).fetchall()
    else:
        rows = conn.execute("SELECT * FROM opportunities ORDER BY score DESC").fetchall()
    conn.close()
    out = []
    for r in rows:
        d = dict(r)
        d["tags"] = json.loads(d["tags"] or "[]")
        d["rule_hits"] = json.loads(d["rule_hits"] or "[]")
        d["score_breakdown"] = json.loads(d["score_breakdown"] or "{}")
        d["biz"] = json.loads(d["biz"] or "{}")
        out.append(d)
    return out


def get_opportunity(opp_id):
    conn = _conn()
    r = conn.execute("SELECT * FROM opportunities WHERE id=?", (opp_id,)).fetchone()
    conn.close()
    if not r:
        return None
    d = dict(r)
    d["tags"] = json.loads(d["tags"] or "[]")
    d["rule_hits"] = json.loads(d["rule_hits"] or "[]")
    d["score_breakdown"] = json.loads(d["score_breakdown"] or "{}")
    d["biz"] = json.loads(d["biz"] or "{}")
    return d


def set_lifecycle(opp_id, lifecycle, owner=None):
    conn = _conn()
    if lifecycle not in ("new", "verifying", "contacted", "invalid"):
        raise ValueError(f"非法生命周期: {lifecycle}")
    conn.execute(
        "UPDATE opportunities SET lifecycle=?, owner=COALESCE(?, owner) WHERE id=?",
        (lifecycle, owner, opp_id),
    )
    conn.commit()
    conn.close()


# ---------- 复核 ----------

def delete_opportunity(opp_id):
    """删除指定商机及其复核记录。"""
    conn = _conn()
    conn.execute("DELETE FROM reviews WHERE opportunity_id=?", (opp_id,))
    conn.execute("DELETE FROM opportunities WHERE id=?", (opp_id,))
    conn.commit()
    conn.close()


def clear_opportunities():
    """清空商机与复核记录（切换数据源时使用）。"""
    conn = _conn()
    conn.execute("DELETE FROM reviews")
    conn.execute("DELETE FROM opportunities")
    conn.commit()
    conn.close()


def save_review(opp_id, review):
    import datetime
    conn = _conn()
    conn.execute(
        "INSERT OR REPLACE INTO reviews(opportunity_id, review, reviewed_at) VALUES (?,?,?)",
        (opp_id, json.dumps(review, ensure_ascii=False),
         datetime.datetime.now().isoformat(timespec="seconds")),
    )
    conn.commit()
    conn.close()


def get_review(opp_id):
    conn = _conn()
    r = conn.execute("SELECT * FROM reviews WHERE opportunity_id=?", (opp_id,)).fetchone()
    conn.close()
    if not r:
        return None
    d = dict(r)
    d["review"] = json.loads(d["review"])
    return d


# ---------- 文档（RAG 语料） ----------

def upsert_document(doc):
    conn = _conn()
    conn.execute(
        """INSERT OR REPLACE INTO documents
           (id, company, title, url, publish_date, source, doc_type, raw_text, created_at)
           VALUES (?,?,?,?,?,?,?,?,?)""",
        (
            doc["id"], doc.get("company"), doc.get("title"), doc.get("url"),
            doc.get("publish_date"), doc.get("source"), doc.get("doc_type"),
            doc.get("raw_text"), doc.get("created_at"),
        ),
    )
    conn.commit()
    conn.close()
    return doc["id"]


def get_documents(company=None, limit=100):
    conn = _conn()
    if company:
        rows = conn.execute(
            "SELECT * FROM documents WHERE company=? ORDER BY created_at DESC LIMIT ?",
            (company, limit),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM documents ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_document(doc_id):
    conn = _conn()
    r = conn.execute("SELECT * FROM documents WHERE id=?", (doc_id,)).fetchone()
    conn.close()
    return dict(r) if r else None


def upsert_chunks(chunks):
    """写入分块：doc_chunks + chunks_fts（trigram）。chunks: list[dict]。"""
    if not chunks:
        return
    conn = _conn()
    conn.execute("BEGIN")
    for c in chunks:
        conn.execute(
            """INSERT INTO doc_chunks(doc_id, company, chunk_index, text, meta)
               VALUES (?,?,?,?,?)""",
            (
                c["doc_id"], c.get("company"), c.get("chunk_index", 0),
                c["text"], json.dumps(c.get("meta", {}), ensure_ascii=False),
            ),
        )
        conn.execute(
            "INSERT INTO chunks_fts(text, company) VALUES (?,?)",
            (c["text"], c.get("company") or ""),
        )
    conn.commit()
    conn.close()


def clear_chunks(doc_id=None):
    """清空分块（doc_id 为空则全清）。返回删除条数。"""
    conn = _conn()
    if doc_id:
        rows = conn.execute(
            "SELECT id FROM doc_chunks WHERE doc_id=?", (doc_id,)
        ).fetchall()
        ids = [r["id"] for r in rows]
        if ids:
            marks = ",".join("?" * len(ids))
            conn.execute(
                f"DELETE FROM chunks_fts WHERE rowid IN ({marks})", ids
            )
            conn.execute("DELETE FROM doc_chunks WHERE doc_id=?", (doc_id,))
        conn.commit()
        conn.close()
        return len(ids)
    conn.execute("DELETE FROM doc_chunks")
    conn.execute("DELETE FROM chunks_fts")
    conn.commit()
    conn.close()
    return 0


def get_chunks(doc_id=None, company=None, limit=1000):
    conn = _conn()
    sql = "SELECT * FROM doc_chunks"
    args = []
    conds = []
    if doc_id:
        conds.append("doc_id=?")
        args.append(doc_id)
    if company:
        conds.append("company=?")
        args.append(company)
    if conds:
        sql += " WHERE " + " AND ".join(conds)
    sql += " ORDER BY id LIMIT ?"
    args.append(limit)
    rows = conn.execute(sql, args).fetchall()
    conn.close()
    out = []
    for r in rows:
        d = dict(r)
        d["meta"] = json.loads(d["meta"] or "{}")
        out.append(d)
    return out


def get_chunk_by_id(chunk_id):
    conn = _conn()
    r = conn.execute("SELECT * FROM doc_chunks WHERE id=?", (chunk_id,)).fetchone()
    conn.close()
    if not r:
        return None
    d = dict(r)
    d["meta"] = json.loads(d["meta"] or "{}")
    return d


def search_chunks_fts(query, company=None, limit=20):
    """FTS5 trigram 检索。query 需为合法 MATCH 表达式（外部已转义）。"""
    conn = _conn()
    sql = """SELECT c.id, c.doc_id, c.company, c.chunk_index, c.text, c.meta
             FROM chunks_fts f JOIN doc_chunks c ON c.id = f.rowid
             WHERE chunks_fts MATCH ?"""
    args = [query]
    if company:
        sql += " AND c.company=?"
        args.append(company)
    sql += " ORDER BY bm25(chunks_fts) LIMIT ?"
    args.append(limit)
    rows = conn.execute(sql, args).fetchall()
    conn.close()
    out = []
    for r in rows:
        d = dict(r)
        d["meta"] = json.loads(d["meta"] or "{}")
        out.append(d)
    return out


# ---------- 企业档案 ----------

def upsert_profile(profile):
    conn = _conn()
    conn.execute(
        """INSERT OR REPLACE INTO company_profiles
           (company, legal_rep, registered_address, office_address, zip_code,
            website, email, stock_codes, registered_capital, credit_code,
            source_title, source_url, report_date, updated_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            profile["company"], profile.get("legal_rep"),
            profile.get("registered_address"), profile.get("office_address"),
            profile.get("zip_code"), profile.get("website"), profile.get("email"),
            profile.get("stock_codes"), profile.get("registered_capital"),
            profile.get("credit_code"), profile.get("source_title"),
            profile.get("source_url"), profile.get("report_date"),
            profile.get("updated_at"),
        ),
    )
    conn.commit()
    conn.close()


def get_profile(company):
    conn = _conn()
    r = conn.execute("SELECT * FROM company_profiles WHERE company=?", (company,)).fetchone()
    conn.close()
    return dict(r) if r else None


def list_profiles(limit=200):
    conn = _conn()
    rows = conn.execute(
        "SELECT * FROM company_profiles ORDER BY updated_at DESC LIMIT ?", (limit,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ---------- 企业画像（company_insights） ----------

def upsert_insight(insight):
    conn = _conn()
    conn.execute(
        """INSERT OR REPLACE INTO company_insights
           (company, revenue_scale, export_ratio, overseas_subsidiaries,
            fx_exposure_direction, hedge_history, recommended_products,
            confidence, source_note, updated_at)
           VALUES (?,?,?,?,?,?,?,?,?,?)""",
        (
            insight["company"], insight.get("revenue_scale") or "",
            insight.get("export_ratio") or "", insight.get("overseas_subsidiaries") or "",
            insight.get("fx_exposure_direction") or "", insight.get("hedge_history") or "",
            insight.get("recommended_products") or "", insight.get("confidence") or "",
            insight.get("source_note") or "", insight.get("updated_at"),
        ),
    )
    conn.commit()
    conn.close()


def get_insight(company):
    conn = _conn()
    r = conn.execute("SELECT * FROM company_insights WHERE company=?", (company,)).fetchone()
    conn.close()
    return dict(r) if r else None


def list_insights(limit=200):
    conn = _conn()
    rows = conn.execute(
        "SELECT * FROM company_insights ORDER BY updated_at DESC LIMIT ?", (limit,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ---------- 会话记忆（conversation_memory，单行 JSON） ----------

def memory_get():
    conn = _conn()
    r = conn.execute("SELECT data FROM conversation_memory WHERE id=1").fetchone()
    conn.close()
    if r is None:
        return {"recent_companies": [], "last_company": None, "regions": [], "updated_at": None}
    try:
        return json.loads(r["data"] or "{}")
    except Exception:
        return {"recent_companies": [], "last_company": None, "regions": [], "updated_at": None}


def memory_set(data):
    data["updated_at"] = datetime.datetime.now().isoformat(timespec="seconds")
    conn = _conn()
    conn.execute(
        "INSERT OR REPLACE INTO conversation_memory(id, data, updated_at) VALUES (1,?,?)",
        (json.dumps(data, ensure_ascii=False), data["updated_at"]),
    )
    conn.commit()
    conn.close()




if __name__ == "__main__":
    import sys
    if "--init" in sys.argv:
        init_db()
        print("DB initialized")
    else:
        print(__doc__)
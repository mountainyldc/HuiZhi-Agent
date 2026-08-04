"""SQLite 访问层：公告 / 商机 / 复核 / 生命周期状态机。

生命周期：new(新发现) -> verifying(待核实) -> contacted(已联系)；另有 invalid(标记无效)。
"""
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
            lifecycle TEXT, owner TEXT, created_date TEXT
        );
        CREATE TABLE IF NOT EXISTS reviews(
            opportunity_id TEXT PRIMARY KEY,
            review TEXT, reviewed_at TEXT
        );
        """
    )
    conn.commit()
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


# ---------- 商机 ----------

def insert_opportunity(opp):
    conn = _conn()
    conn.execute(
        """INSERT OR REPLACE INTO opportunities
           (id, announcement_id, company_name, city, tags, trigger_event,
            rule_hits, score, score_breakdown, lifecycle, owner, created_date)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            opp["id"], opp.get("announcement_id"), opp["company_name"],
            opp.get("city"), json.dumps(opp.get("tags", []), ensure_ascii=False),
            opp.get("trigger_event"),
            json.dumps(opp.get("rule_hits", []), ensure_ascii=False),
            opp.get("score", 0),
            json.dumps(opp.get("score_breakdown", {}), ensure_ascii=False),
            opp.get("lifecycle", "new"), opp.get("owner"),
            opp.get("created_date"),
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


if __name__ == "__main__":
    import sys
    if "--init" in sys.argv:
        init_db()
        print("DB initialized")
    else:
        print(__doc__)
"""队列引擎：从 SQLite 生成"今日商机队列"快照（含详情与复核，供 Web 渲染）。

用法:
  python build_queue.py              # 生成今天的队列快照
  python build_queue.py --date 2026-08-04
  python build_queue.py --out <path>
"""
import argparse
import datetime
import json
import os

from common import load_config, project_path
import store


def build_queue(date=None, out=None):
    cfg = load_config()
    store.init_db()
    date = date or datetime.date.today().isoformat()
    anns = {a["id"]: a for a in store.list_announcements()}
    opps = [o for o in store.list_opportunities() if o["lifecycle"] != "invalid"]
    opps.sort(key=lambda o: o["score"], reverse=True)

    items = []
    for rank, o in enumerate(opps, start=1):
        ann = anns.get(o["announcement_id"], {})
        rev = store.get_review(o["id"])
        items.append({
            "rank": rank,
            "opportunity_id": o["id"],
            "company_name": o["company_name"],
            "city": o["city"],
            "title": ann.get("title", o["trigger_event"]),
            "tags": o["tags"],
            "score": o["score"],
            "score_breakdown": o["score_breakdown"],
            "lifecycle": o["lifecycle"],
            "owner": o["owner"],
            "trigger_event": o["trigger_event"],
            "rule_hits": o["rule_hits"],
            "publish_date": ann.get("publish_date", ""),
            "source": ann.get("source", ""),
            "review": (rev or {}).get("review") if rev else None,
        })

    snapshot = {
        "date": date,
        "generated_at": datetime.datetime.now().isoformat(timespec="seconds"),
        "region": cfg["region"]["default"],
        "items": items,
    }
    out = out or project_path("data/queue_snapshots", f"{date}.json")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(snapshot, f, ensure_ascii=False, indent=2)
    return snapshot


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=None)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    snap = build_queue(args.date, args.out)
    print(f"[result] 队列 {len(snap['items'])} 条 -> 已写入快照")
    for it in snap["items"]:
        print(f"  #{it['rank']} {it['company_name']}({it['city']}) score={it['score']} "
              f"lifecycle={it['lifecycle']}")


if __name__ == "__main__":
    main()
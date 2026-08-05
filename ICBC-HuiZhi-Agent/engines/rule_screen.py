"""规则初筛 + 5 维评分引擎（支持多数据源）。

数据源:
  - 巨潮公告（cninfo_*）：广东企业 + 外汇与套保 + 近45天 三项硬规则
  - 舆情（新浪快讯 sina_*）：广东企业 + 外汇/汇率/海外关键词 = 软信号，走舆情评分

用法:
  python rule_screen.py                    # 读取 data/crawled/ 全部文件，写入 SQLite
  python rule_screen.py --input <path>     # 指定单个公告文件
  python rule_screen.py --region 广东      # 指定地区
  python rule_screen.py --reset            # 清空已有商机/复核后重建
"""
import argparse
import csv
import datetime
import hashlib
import json
import os

from common import load_config, project_path
import store

HEDGE_KEYWORDS = ["套保", "套期保值", "衍生品", "结售汇", "避险", "汇率风险", "远期", "掉期", "期权"]
OVERSEAS_KEYWORDS = ["境外", "海外", "子公司", "增资", "香港", "泰国", "越南", "新加坡", "记账本位币"]
NEWS_SOURCE_MARK = "快讯"  # 匹配 新浪财经·7x24快讯 / 东方财富·7x24快讯


def load_allowlist(path):
    """返回 {code: (name, city)} 与 {name: (code, city)} 两个索引。"""
    by_code, by_name = {}, {}
    with open(path, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            code, name, city = row["stock_code"].strip(), row["stock_name"].strip(), row["city"].strip()
            by_code[code] = (name, city)
            by_name[name] = (code, city)
    return by_code, by_name



COUNTRIES = ["中国香港", "香港", "美国", "越南", "泰国", "新加坡", "德国", "日本",
             "马来西亚", "印度尼西亚", "墨西哥", "巴西", "英国", "法国", "荷兰"]
CURRENCIES = ["美元", "欧元", "港币", "日元", "英镑", "新加坡元", "人民币"]


def infer_biz(title, tags):
    """从公告标题与标签推断潜在业务（对外付款/对外收款/汇率避险/跨境结算）。"""
    biz_type, biz_sub = "", ""
    if "外汇与套保" in tags or any(k in title for k in ("套保", "套期保值", "衍生品", "远期", "期权", "掉期", "结售汇")):
        biz_type, biz_sub = "汇率避险", "套保/衍生品管理汇率敞口"
    elif any(k in title for k in ("对外投资", "设立", "增资", "收购", "境外投资", "子公司")):
        biz_type, biz_sub = "对外付款", "境外投资或子公司出资"
    if any(k in title for k in ("出口", "境外收入", "海外收入", "收汇", "销售")):
        biz_type, biz_sub = "对外收款", "出口或境外收入"
    if any(k in title for k in ("跨境", "贸易", "结算", "进口")):
        biz_type, biz_sub = "跨境结算", "进出口贸易结算"
    if not biz_type:
        biz_type, biz_sub = "待判断", ""
    country = next((c for c in COUNTRIES if c in title), "待核实")
    currency = next((c for c in CURRENCIES if c in title), "待核实")
    event_type = ("外汇与套保" if "外汇与套保" in tags
                  else ("境外投资/子公司" if "境外投资/子公司" in tags else "外汇相关事件"))
    return {"biz_type": biz_type, "biz_sub": biz_sub,
            "event_type": event_type, "country": country, "currency": currency}

def classify(title):
    tags = []
    if any(k in title for k in HEDGE_KEYWORDS):
        tags.append("外汇与套保")
    if any(k in title for k in OVERSEAS_KEYWORDS):
        tags.append("境外投资/子公司")
    if any(k in title for k in ("境外", "海外", "香港", "泰国", "越南", "新加坡")):
        tags.append("境外市场")
    tags.append("币种待核实")
    return tags


def _days_ago(pub_date, today):
    try:
        d = datetime.date.fromisoformat(pub_date)
    except (TypeError, ValueError):
        return None
    return (today - d).days


def _score_announcement(ann, cfg, city, today):
    """公告型 5 维评分。"""
    w = cfg["score"]["weights"]
    b = {}
    title = ann["title"]
    if any(k in title for k in ("可行性分析", "管理制度", "进展", "更正")):
        b["event_credibility"] = 80
    else:
        b["event_credibility"] = 95
    if any(k in title for k in ("套期保值", "衍生品交易", "远期结售汇", "外汇衍生品")):
        b["capital_scale"] = 60
    else:
        b["capital_scale"] = 45
    d = _days_ago(ann.get("publish_date"), today)
    b["timeliness"] = 95 if d is None or d <= 7 else (85 if d <= 15 else (70 if d <= 30 else 60))
    b["coverage"] = cfg.get("score", {}).get("coverage_placeholder", 55)
    comp = 40
    if ann.get("url"):
        comp += 10
    if ann.get("publish_date"):
        comp += 10
    if city:
        comp += 10
    if ann.get("keywords_hit"):
        comp += 5
    b["info_completeness"] = min(comp, 95)
    return round(sum(w[k] * b[k] for k in w)), b


def _score_news(ann, cfg, city, today):
    """舆情型（软信号）5 维评分：可信度低、时效性高。"""
    w = cfg["score"]["weights"]
    b = {
        "event_credibility": 60,   # 舆情未经公司公告证实
        "capital_scale": 55,
        "timeliness": 95,          # 快讯即最新
        "coverage": cfg.get("score", {}).get("coverage_placeholder", 55),
        "info_completeness": 60,
    }
    return round(sum(w[k] * b[k] for k in w)), b


def _build_opportunity(ann, name, code, city, tags, rule_hits, trigger, total, breakdown, today):
    opp_id = "opp_" + hashlib.md5(ann["id"].encode("utf-8")).hexdigest()[:8]
    return {
        "id": opp_id,
        "announcement_id": ann["id"],
        "company_name": name,
        "city": city,
        "tags": tags,
        "trigger_event": trigger,
        "rule_hits": rule_hits,
        "score": total,
        "score_breakdown": breakdown,
        "lifecycle": "new",
        "owner": None,
        "created_date": today.isoformat(),
        "biz": infer_biz(ann.get("title", ""), tags),
    }


def rule_screen(input_path=None, region=None):
    cfg = load_config()
    region = region or cfg["region"]["default"]
    by_code, by_name = load_allowlist(project_path(cfg["region"]["allowlist"]))
    today = datetime.date.today()

    if input_path is None:
        crawled_dir = project_path("data/crawled")
        files = sorted(f for f in os.listdir(crawled_dir) if f.endswith(".json"))
        if not files:
            raise FileNotFoundError("data/crawled 下没有数据文件，请先运行 crawl_cninfo.py / sina_news.py")
        anns = []
        for fn in files:
            with open(os.path.join(crawled_dir, fn), encoding="utf-8") as f:
                anns.extend(json.load(f))
    else:
        with open(input_path, encoding="utf-8") as f:
            anns = json.load(f)

    store.upsert_announcements(anns)  # 公告/舆情入库，供队列与页面联查

    created = []
    for ann in anns:
        source = ann.get("source", "")
        is_news = NEWS_SOURCE_MARK in source
        code = ann.get("stock_code", "")
        name = ann.get("stock_name", "")
        if code and code in by_code:
            pass
        elif name and name in by_name:
            code, name = by_name[name]
        else:
            continue  # 非广东企业
        stock_name, city = by_code[code]

        if is_news:
            tags = ["境外市场", "舆情", "币种待核实"]
            rule_hits = ["广东企业", "舆情信号"]
            total, breakdown = _score_news(ann, cfg, city, today)
            trigger = f"{ann['source'].split('·')[0]}快讯：{ann['title']}"
        else:
            tags = classify(ann.get("title", ""))
            if "外汇与套保" not in tags:
                continue  # 硬规则2
            d = _days_ago(ann.get("publish_date"), today)
            if d is None or d > cfg["crawl"]["days_window"] or d < 0:
                continue  # 硬规则3
            total, breakdown = _score_announcement(ann, cfg, city, today)
            rule_hits = ["广东企业", "外汇与套保", "近45天官方公告"]
            trigger = f"巨潮资讯公告：{ann['title']}"

        opp = _build_opportunity(ann, stock_name, code, city, tags, rule_hits,
                                 trigger, total, breakdown, today)
        store.insert_opportunity(opp)
        created.append(opp)

    return created


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", default=None)
    ap.add_argument("--region", default=None)
    ap.add_argument("--reset", action="store_true", help="清空已有商机/复核后重建")
    args = ap.parse_args()
    store.init_db()
    if args.reset:
        store.clear_opportunities()
        print("[info] 已清空商机与复核记录")
    opps = rule_screen(args.input, args.region)
    print(f"[result] 命中 {len(opps)} 条商机（同公司多公告均保留）")
    for o in opps:
        print(f"  - {o['company_name']}({o['city']}) score={o['score']} "
              f"tags={o['tags']} rule={o['rule_hits']}")


if __name__ == "__main__":
    main()
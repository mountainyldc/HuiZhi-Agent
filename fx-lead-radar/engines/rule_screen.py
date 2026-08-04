"""规则初筛 + 5 维评分引擎。

规则命中（全部满足才成为商机）:
  1. 广东企业：股票代码在 engines/region_allowlist.csv 名单内
  2. 外汇与套保：标题命中套保/衍生品/结售汇/避险等关键词
  3. 近45天官方公告：publish_date 在 config 窗口内

5 维评分（0-100，可解释，权重见 config.yaml）:
  事件可信度 / 资金体量 / 时效性 / 我行覆盖度 / 信息完整度
  说明: 我行覆盖度无行内数据，使用占位规则值【边界不稳】。

用法:
  python rule_screen.py                    # 读取最新 data/crawled/*.json，写入 SQLite
  python rule_screen.py --input <path>     # 指定公告文件
  python rule_screen.py --region 广东      # 指定地区
"""
import argparse
import csv
import datetime
import hashlib
import json
import os
import re

from common import load_config, project_path
import store

HEDGE_KEYWORDS = ["套保", "套期保值", "衍生品", "结售汇", "避险", "汇率风险", "远期", "掉期", "期权"]
OVERSEAS_KEYWORDS = ["境外", "海外", "子公司", "增资", "香港", "泰国", "越南", "新加坡", "记账本位币"]


def load_allowlist(path):
    """stock_code -> (stock_name, city)"""
    out = {}
    with open(path, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            out[row["stock_code"].strip()] = (row["stock_name"].strip(), row["city"].strip())
    return out


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


def score_opportunity(ann, cfg, city, today):
    w = cfg["score"]["weights"]
    b = {}

    # 事件可信度：官方公告基础 95；辅助性文档（可行性分析/管理制度/进展）降分
    title = ann["title"]
    if any(k in title for k in ("可行性分析", "管理制度", "进展", "更正")):
        b["event_credibility"] = 80
    else:
        b["event_credibility"] = 95

    # 资金体量：无具体金额数据，用业务类型近似（实际套保/衍生品交易 > 一般公告）
    if any(k in title for k in ("套期保值", "衍生品交易", "远期结售汇", "外汇衍生品")):
        b["capital_scale"] = 60
    else:
        b["capital_scale"] = 45

    # 时效性：近45天窗口，越近越高
    d = _days_ago(ann.get("publish_date"), today)
    if d is None:
        b["timeliness"] = 50
    elif d <= 7:
        b["timeliness"] = 95
    elif d <= 15:
        b["timeliness"] = 85
    elif d <= 30:
        b["timeliness"] = 70
    else:
        b["timeliness"] = 60

    # 我行覆盖度：占位规则值【边界不稳：无行内数据】
    b["coverage"] = cfg.get("score", {}).get("coverage_placeholder", 55)

    # 信息完整度：按可用字段累加
    comp = 40
    if ann.get("url"):
        comp += 10
    if ann.get("publish_date"):
        comp += 10
    if ann.get("region_hint") or city:
        comp += 10
    if ann.get("keywords_hit"):
        comp += 5
    b["info_completeness"] = min(comp, 95)

    total = round(sum(w[k] * b[k] for k in w))
    return total, b


def rule_screen(input_path=None, region=None):
    cfg = load_config()
    region = region or cfg["region"]["default"]
    allowlist = load_allowlist(project_path(cfg["region"]["allowlist"]))
    today = datetime.date.today()

    if input_path is None:
        crawled_dir = project_path("data/crawled")
        files = sorted(f for f in os.listdir(crawled_dir) if f.endswith(".json"))
        if not files:
            raise FileNotFoundError("data/crawled 下没有公告文件，请先运行 crawl_cninfo.py")
        input_path = os.path.join(crawled_dir, files[-1])
    with open(input_path, encoding="utf-8") as f:
        anns = json.load(f)

    created = []
    for ann in anns:
        code = ann.get("stock_code", "")
        if code not in allowlist:
            continue  # 规则1：非广东企业
        stock_name, city = allowlist[code]
        title = ann.get("title", "")

        tags = classify(title)
        if "外汇与套保" not in tags:
            continue  # 规则2：非外汇套保相关

        d = _days_ago(ann.get("publish_date"), today)
        if d is None or d > cfg["crawl"]["days_window"] or d < 0:
            continue  # 规则3：不在近45天窗口

        total, breakdown = score_opportunity(ann, cfg, city, today)
        opp_id = "opp_" + hashlib.md5(ann["id"].encode("utf-8")).hexdigest()[:8]
        opp = {
            "id": opp_id,
            "announcement_id": ann["id"],
            "company_name": stock_name,
            "city": city,
            "tags": tags,
            "trigger_event": f"巨潮资讯公告：{title}",
            "rule_hits": ["广东企业", "外汇与套保", "近45天官方公告"],
            "score": total,
            "score_breakdown": breakdown,
            "lifecycle": "new",
            "owner": None,
            "created_date": today.isoformat(),
        }
        store.insert_opportunity(opp)
        created.append(opp)

    store.init_db()
    return created


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", default=None)
    ap.add_argument("--region", default=None)
    args = ap.parse_args()
    store.init_db()
    opps = rule_screen(args.input, args.region)
    print(f"[result] 命中 {len(opps)} 条商机")
    for o in opps:
        print(f"  - {o['company_name']}({o['city']}) score={o['score']} "
              f"tags={o['tags']} date={o.get('created_date')}")


if __name__ == "__main__":
    main()
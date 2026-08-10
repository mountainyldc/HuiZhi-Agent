# -*- coding: utf-8 -*-
"""意图路由引擎（P1-2 动态规划）：把用户问法路由到对应工具链。

规则判断（非 LLM，稳定可解释）：分析公司 / 跑全流程 / 查画像 / 查队列 / 实时搜索 / 普通问答。

用法:
  python dispatch.py --query "帮我分析东鹏饮料的外汇需求"
  python dispatch.py --query "今天队列有多少条" --json
"""
import argparse
import json
import re
import sys

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def route(query):
    q = query or ""
    lower = q.lower()
    # 1) 跑全流程（更新/雷达/流程）
    if re.search(r"(跑|执行|运行|更新|刷新).{0,4}(流程|雷达|全流程|数据)", q) or \
       "雷达" in q and re.search(r"(跑|运行|更新|全流程)", q) or \
       re.search(r"(重跑|重新跑|整一轮|流程跑一遍)", q):
        return {
            "intent": "pipeline",
            "reason": "命中全流程/更新关键词",
            "suggested_tools": ["crawl_cninfo", "crawl_news", "rule_screen", "review_opportunity(all=true)", "build_daily_queue", "render_web", "start_server"],
            "command_hint": "/radar",
        }
    # 2) 实时搜索（政策/走势/新闻/最新/竞品）
    if re.search(r"(新政策|最新|走势|行情|政策解读|竞品|行业动态|新闻|消息|汇率.*(走势|变化))", q):
        return {
            "intent": "web_search",
            "reason": "命中时效性信息关键词，语料库通常查不到",
            "suggested_tools": ["web_search"],
            "command_hint": None,
        }
    # 3) 邮件发送（日报/公司摘要）
    if re.search(r"(发|发送|发到).{0,8}(邮件|邮箱|日报|报告)", q) or re.search(r"(邮件|邮箱).{0,6}(发|发送)", q):
        return {
            "intent": "send_mail",
            "reason": "命中邮件/发送关键词",
            "suggested_tools": ["send_daily_report", "send_company_report"],
            "command_hint": None,
        }
    # 4) 企业画像
    if re.search(r"(画像|企业档案|基本情况|拜访前必看)", q):
        company = _company(q)
        return {
            "intent": "company_insight",
            "reason": "命中画像/档案关键词",
            "suggested_tools": ["company_insight"],
            "command_hint": None,
            "company": company,
        }
    # 5) 队列统计/结构化查询
    if re.search(r"(队列|多少条|排名|前\s*\d+|统计|分布|几家|哪些公司)", q):
        return {
            "intent": "queue_query",
            "reason": "命中队列/统计关键词",
            "suggested_tools": ["build_daily_queue(若队列过期)", "ask_insights"],
            "command_hint": None,
        }
    # 6) 分析公司
    if re.search(r"(分析|评估|研究|深度|为什么|怎么看|风险敞口|外汇需求)", q):
        company = _company(q)
        return {
            "intent": "analyze_company",
            "reason": "命中分析类关键词",
            "suggested_tools": ["analyze_company", "company_insight"],
            "command_hint": None,
            "company": company,
        }
    # 7) 兜底：普通问答
    return {
        "intent": "ask",
        "reason": "未命中任何专用意图，走普通问答兜底",
        "suggested_tools": ["ask_insights"],
        "command_hint": None,
    }


_COMPANY_RE = re.compile(r"(?:分析|画像|看看|了解|查|评估)?\s*([\u4e00-\u9fffA-Za-z0-9]{2,12}?)(?:的|的外汇|公司|企业)?")


def _company(q):
    """尽力从问句中提取公司名（与商机/档案公司名匹配）。"""
    try:
        import store
        names = []
        for p in store.list_profiles(limit=500):
            names.append(p["company"])
        for o in store.list_opportunities():
            n = (o.get("company_name") or "").strip()
            if n and n not in names:
                names.append(n)
        names.sort(key=len, reverse=True)
        for n in names:
            if n and n in q:
                return n
    except Exception:
        pass
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--query", required=True)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    res = route(args.query)
    if args.json:
        print(json.dumps(res, ensure_ascii=False, indent=2))
        return
    print(f"意图：{res['intent']} | 原因：{res['reason']}")
    print("建议工具：" + " -> ".join(res["suggested_tools"]))
    if res.get("company"):
        print("识别公司：" + res["company"])
    if res.get("command_hint"):
        print("快捷命令：" + res["command_hint"])


if __name__ == "__main__":
    main()
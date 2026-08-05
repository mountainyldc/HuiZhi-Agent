# -*- coding: utf-8 -*-
"""P2 生成引擎：混合检索证据 -> DeepSeek -> 带 [来源N] 角标的引用回答。

用法:
  python rag_answer.py --query "帮我分析东鹏饮料的外汇需求"
  python rag_answer.py --company 东鹏饮料 --query "外汇风险敞口如何"
  python rag_answer.py --query "..." --top 5 --dry-run    # 只打印 Prompt
  python rag_answer.py --query "..." --json               # 输出 JSON（供扩展调用）
"""
import argparse
import json
import os
import re
import sys

from common import load_config
from retrieve import retrieve
import store

SYSTEM_PROMPT = (
    "你是工商银行深圳分行金融市场部的外汇业务分析师，服务对象是客户经理。"
    "回答必须基于给定的检索证据，不得编造证据中不存在的信息。"
    "引用证据时用 [来源N] 标注（N 对应证据列表编号）。"
    "如果证据不足以回答，明确列出需要向客户核实的未知项。"
    "用中文回答，先给结论，再给依据，最后给建议行动。"
)


def detect_company(query):
    """从提问文本中识别公司名（商机/档案公司名子串匹配）。"""
    names = []
    for p in store.list_profiles(limit=500):
        names.append(p["company"])
    for opp in store.list_opportunities():
        n = (opp.get("company_name") or "").strip()
        if n and n not in names:
            names.append(n)
    for n in names:
        if n and n in (query or ""):
            return n
    return None


def build_messages(query, evidence):
    blocks = []
    for i, e in enumerate(evidence, start=1):
        blocks.append(
            f"[来源{i}] 公司：{e['company']}\n"
            f"标题：{e['title']}\n日期：{e['publish_date']}\n链接：{e['url']}\n"
            f"内容：{e['text']}"
        )
    user = "以下是检索到的公开公告证据：\n\n" + "\n\n".join(blocks) + "\n\n问题：" + query
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user},
    ]


_SRC_RE = re.compile(r"\[来源\s*(\d+)(?:\s*[-–—]\s*(\d+))?\]")


def linkify_sources(text, evidence):
    urls = [e.get("url", "") or "" for e in evidence]

    def _repl(m):
        n1 = int(m.group(1))
        n2 = int(m.group(2)) if m.group(2) else n1
        for idx in range(n1, n2 + 1):
            if 1 <= idx <= len(urls) and urls[idx - 1]:
                label = m.group(0).strip("[]")
                return f"[{label}]({urls[idx - 1]})"
        return m.group(0)

    return _SRC_RE.sub(_repl, text)


def answer(query, company=None, top_n=5, dry_run=False, verbose=False):
    cfg = load_config()
    llm = cfg["rag"]["llm"]
    key = os.environ.get(llm["api_key_env"])
    if not key:
        print("[error] 未设置 DEEPSEEK_API_KEY 环境变量", file=sys.stderr)
        return None
    if company is None:
        company = detect_company(query)
    evidence = retrieve(query, company=company, top_n=top_n, verbose=verbose)
    if not evidence:
        print("[result] 无检索证据，无法回答")
        return None
    messages = build_messages(query, evidence)
    if dry_run:
        print(json.dumps(messages, ensure_ascii=False, indent=2))
        return {"company": company, "dry_run": True, "messages": messages}

    from openai import OpenAI
    client = OpenAI(base_url=llm["base_url"], api_key=key)
    try:
        resp = client.chat.completions.create(
            model=llm["model"], messages=messages, temperature=0.3, timeout=120
        )
        content = resp.choices[0].message.content
    except Exception as exc:
        print(f"[error] 生成失败: {exc}", file=sys.stderr)
        return None
    content = linkify_sources(content, evidence)
    return {"company": company, "answer": content, "evidence": evidence}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--query", required=True)
    ap.add_argument("--company", default=None)
    ap.add_argument("--top", type=int, default=5)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    res = answer(args.query, company=args.company, top_n=args.top, dry_run=args.dry_run)
    if res is None:
        sys.exit(1)
    if args.dry_run:
        return
    if args.json:
        print(json.dumps(res, ensure_ascii=False, indent=2))
        return
    print("=" * 60)
    print("回答：")
    print(res["answer"])
    print("=" * 60)
    for i, e in enumerate(res["evidence"], start=1):
        print(f"[来源{i}] {e['company']} | {e['publish_date']} | {e['title'][:40]}")
        print(f"    {e['url']}")


if __name__ == "__main__":
    main()
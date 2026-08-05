"""大模型复核引擎：生成证据摘要 / 已知事实 / 未知事实 / 建议沟通问题 / 复核分。

使用 OpenAI 兼容接口（默认 DeepSeek）。无 key、调用失败或返回不可解析时
降级为 skipped，不影响主链路。

用法:
  python llm_review.py              # 复核全部未复核商机
  python llm_review.py --id opp_xx  # 复核指定商机
  python llm_review.py --dry-run    # 只打印提示词，不调用
"""
import argparse
import json
import os
import re
import sys
import datetime

from common import load_config, project_path
import store

SYSTEM_PROMPT = (
    "你是工商银行深圳分行金融市场部的外汇业务专家，负责对上市公司公告产生的"
    "结售汇/外汇套保商机线索进行复核。你只输出 JSON，不输出任何其他内容。"
)

REVIEW_SCHEMA = {
    "evidence_summary": {"doc_title": "触发公告标题", "source": "来源", "publish_time": "发布时间"},
    "known_facts": ["从公告可知的事实，如证券代码、属地依据、命中事件"],
    "unknown_facts": ["待向客户核实的未知项，如跨境资金金额、计价币种敞口、现有结算银行、联系人触达窗口"],
    "suggested_questions": ["建议客户沟通问题，2-3条，结合外汇业务专业"],
    "reviewed_score": 0,
    "review_note": "一句话复核结论",
}


def build_prompt(opp):
    return (
        "请复核以下商机线索，输出严格符合以下 JSON 结构的对象：\n"
        + json.dumps(REVIEW_SCHEMA, ensure_ascii=False, indent=2)
        + "\n\n其中 reviewed_score 为 0-100 的整数（若证据不足可给 null），"
          "其余字段为字符串数组或对象。\n\n"
          "商机信息：\n"
        + json.dumps(
            {
                "公司": opp["company_name"],
                "城市": opp["city"],
                "触发事件": opp["trigger_event"],
                "标签": opp["tags"],
                "规则命中": opp["rule_hits"],
                "规则商机分": opp["score"],
                "评分明细": opp["score_breakdown"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


def parse_json_text(text):
    """从模型输出中提取 JSON（容忍代码围栏与前后杂讯）。"""
    if not text:
        return None
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if fence:
        text = fence.group(1).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{[\s\S]*\}", text)
        if m:
            try:
                return json.loads(m.group(0))
            except json.JSONDecodeError:
                return None
    return None


def review_one(opp, client, cfg, dry_run=False):
    if dry_run:
        return {"skipped": False, "dry_run": True, "prompt": build_prompt(opp)}
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": build_prompt(opp)},
    ]
    try:
        resp = client.chat.completions.create(
            model=cfg["review"]["model"],
            messages=messages,
            response_format={"type": "json_object"},
            temperature=0.3,
            timeout=cfg["review"].get("timeout_seconds", 60),
        )
        content = resp.choices[0].message.content
    except Exception as exc:
        return {"skipped": True, "reason": f"调用失败: {exc}"}
    parsed = parse_json_text(content)
    if not parsed:
        return {"skipped": True, "reason": "模型输出无法解析为 JSON"}
    return {"skipped": False, "review": parsed, "raw": content}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--id", default=None)
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    cfg = load_config()
    rev = cfg["review"]
    store.init_db()

    if args.id:
        opps = [store.get_opportunity(args.id)]
        opps = [o for o in opps if o]
    elif args.all or True:
        opps = store.list_opportunities()
        opps = [o for o in opps if o["lifecycle"] != "invalid"]
        # 默认只复核还没有复核记录的
        if not args.all:
            opps = [o for o in opps if store.get_review(o["id"]) is None]
    else:
        opps = []

    if not opps:
        print("[result] 没有待复核商机")
        return

    key = os.environ.get(rev["api_key_env"])
    client = None
    if key:
        from openai import OpenAI
        client = OpenAI(base_url=rev["base_url"], api_key=key)
    else:
        print(f"[warn] 环境变量 {rev['api_key_env']} 未设置，全部跳过复核", file=sys.stderr)

    ok = skipped = 0
    for opp in opps:
        out = review_one(opp, client, cfg, dry_run=args.dry_run)
        if out.get("skipped"):
            skipped += 1
            print(f"[skip] {opp['id']} {opp['company_name']}: {out.get('reason')}")
            continue
        if args.dry_run:
            print(f"[dry-run] {opp['id']} {opp['company_name']} prompt 已生成")
            ok += 1
            continue
        store.save_review(opp["id"], out["review"])
        ok += 1
        r = out["review"]
        print(f"[ok] {opp['id']} {opp['company_name']} "
              f"reviewed_score={r.get('reviewed_score')} "
              f"questions={len(r.get('suggested_questions', []))}")

    print(f"[result] 复核成功 {ok} 条，跳过 {skipped} 条")


if __name__ == "__main__":
    main()
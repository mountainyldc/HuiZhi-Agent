# -*- coding: utf-8 -*-
"""企业画像引擎：聚合公告+年报+舆情，经 DeepSeek 生成「拜访前必看画像卡」字段。

字段口径（未披露一律标「未披露」，禁止用舆情/推断冒充事实）：
  revenue_scale 营收规模 / export_ratio 出口或境外收入占比 / overseas_subsidiaries 境外子公司
  fx_exposure_direction 外汇敞口方向（收款/付款/双向/未知） / hedge_history 历史套保记录
  recommended_products 建议切入产品 / confidence 置信度 / source_note 综合来源说明

每个业务字段存为 JSON 对象 {"value","source","date"}，用于页面标注来源与披露日期。

用法:
  python build_insights.py              # 默认队列 Top 20
  python build_insights.py --top 10
  python build_insights.py --company 东鹏饮料
  python build_insights.py --dry-run    # 只打印提示词，不调用模型
"""
import argparse
import datetime
import json
import os
import re
import sys

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from common import load_config, project_path
import store

SYSTEM_PROMPT = (
    "你是工商银行深圳分行金融市场部的外汇业务研究分析师，为客户经理生成上市公司"
    "「拜访前必看画像卡」。你只输出 JSON，不输出任何其他内容。"
    "硬性要求：1) 每个字段的 value 只能来自提供的证据（公告/年报/舆情），"
    "证据中没有的一律写「未披露」，禁止用舆情或推断冒充事实；"
    "2) 每个字段必须给出 source（来源：公告名/年报名/舆情快讯）与 date（披露日期），"
    "date 未知写空字符串；3) 画像内容与公告原文矛盾时以公告原文为准；"
    "4) 金融产品建议保持审慎，不承诺收益。"
)

FIELD_SCHEMA = {
    "revenue_scale": {"value": "营收规模，如 约100-150亿元（2025年报）", "source": "来源", "date": "披露日期"},
    "export_ratio": {"value": "出口占比/境外收入占比，未披露则写未披露", "source": "来源", "date": "披露日期"},
    "overseas_subsidiaries": {"value": "境外子公司/海外布局概况", "source": "来源", "date": "披露日期"},
    "fx_exposure_direction": {"value": "外汇敞口方向：对外收款/对外付款/双向/未披露", "source": "来源", "date": "披露日期"},
    "hedge_history": {"value": "历史套保/衍生品业务记录", "source": "来源", "date": "披露日期"},
    "recommended_products": {"value": "建议切入产品（远期/掉期/期权/跨境结算等），无依据则写待评估", "source": "来源", "date": "披露日期"},
}
OUTPUT_SCHEMA = dict(FIELD_SCHEMA)
OUTPUT_SCHEMA["confidence"] = {"value": "高/中/低（依据充足程度）", "source": "", "date": ""}
OUTPUT_SCHEMA["source_note"] = {"value": "一句话说明画像依据与局限", "source": "", "date": ""}


def _gather(company):
    """聚合该公司的档案、商机、公告、年报与 RAG 证据。"""
    profile = store.get_profile(company)
    opps = [o for o in store.list_opportunities() if (o.get("company_name") or "") == company]
    anns = [a for a in store.list_announcements() if (a.get("stock_name") or "") == company]
    fin = None
    try:
        import fetch_financials
        fin = fetch_financials.fetch_financials(company)  # 命中缓存；无缓存不强制联网
    except Exception as exc:
        fin = {"status": "error", "message": str(exc)}
    evidence = []
    try:
        from retrieve import retrieve
        evidence = retrieve("外汇需求 风险敞口 套期保值 境外收入 海外布局", company=company, top_n=5)
    except Exception:
        evidence = []
    return profile, opps, anns, fin, evidence


def build_prompt(company):
    profile, opps, anns, fin, evidence = _gather(company)
    parts = []
    parts.append(f"目标公司：{company}")
    if profile:
        parts.append("企业档案（来源：巨潮定期报告）：")
        parts.append(json.dumps({k: v for k, v in profile.items()
                                 if k in ("legal_rep", "registered_address", "office_address",
                                          "registered_capital", "stock_codes", "report_date")},
                                ensure_ascii=False))
    if opps:
        parts.append("商机线索（规则命中）：")
        for o in opps[:10]:
            parts.append(f"- {o.get('trigger_event','')} | 规则:{','.join(o.get('rule_hits') or [])} | 分:{o.get('score')}")
    if anns:
        parts.append("该公司的公开公告标题（前 20 条）：")
        for a in anns[:20]:
            parts.append(f"- {a.get('publish_date','')} | {a.get('title','')} | {a.get('url','')}")
    if fin and fin.get("status") == "ok":
        parts.append("年报财务指标（巨潮年报解析）：")
        for it in fin.get("indicators", []):
            parts.append(f"- {it.get('name')}: {it.get('value')}（{it.get('note','')}，年报第{it.get('page')}页）")
        src = fin.get("source") or {}
        if src:
            parts.append(f"年报来源：{src.get('title','')} | {src.get('url','')}")
    elif fin:
        parts.append(f"年报状态：{fin.get('status')} {fin.get('message','')}")
    if evidence:
        parts.append("检索证据片段：")
        for i, e in enumerate(evidence, start=1):
            parts.append(f"[来源{i}] {e.get('company','')} | {e.get('publish_date','')} | {e.get('title','')}\n{e.get('text','')[:800]}")
    user = (
        "请生成以下公司的「拜访前必看画像卡」，输出严格符合此 JSON 结构的对象：\n"
        + json.dumps(OUTPUT_SCHEMA, ensure_ascii=False, indent=2)
        + "\n\n证据材料：\n" + "\n".join(parts)
        + "\n\n要求：每个字段 value 必须可溯源，无证据写「未披露」；"
          "source/date 取自证据，未知留空字符串。"
    )
    return user


def parse_json_text(text):
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


def build_one(company, client, cfg, dry_run=False):
    prompt = build_prompt(company)
    if dry_run:
        return {"company": company, "dry_run": True, "prompt": prompt}
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": prompt},
    ]
    try:
        resp = client.chat.completions.create(
            model=cfg["rag"]["llm"]["model"],
            messages=messages,
            response_format={"type": "json_object"},
            temperature=0.2,
            timeout=90,
        )
        content = resp.choices[0].message.content
    except Exception as exc:
        return {"company": company, "skipped": True, "reason": f"调用失败: {exc}"}
    parsed = parse_json_text(content)
    if not parsed:
        return {"company": company, "skipped": True, "reason": "模型输出无法解析为 JSON"}
    return {"company": company, "skipped": False, "insight": parsed}


def _norm_field(v):
    if isinstance(v, dict):
        return {
            "value": str(v.get("value") or "未披露"),
            "source": str(v.get("source") or ""),
            "date": str(v.get("date") or ""),
        }
    return {"value": str(v or "未披露"), "source": "", "date": ""}


def save_insight(company, parsed):
    record = {"company": company}
    for k in ("revenue_scale", "export_ratio", "overseas_subsidiaries",
              "fx_exposure_direction", "hedge_history", "recommended_products"):
        record[k] = json.dumps(_norm_field(parsed.get(k)), ensure_ascii=False)
    conf = parsed.get("confidence")
    if isinstance(conf, dict):
        conf = conf.get("value")
    record["confidence"] = str(conf or "未披露")
    record["source_note"] = str(parsed.get("source_note") or "")
    record["updated_at"] = datetime.datetime.now().isoformat(timespec="seconds")
    store.upsert_insight(record)
    return record


def top_companies(n):
    """按队列分数取 Top N 公司名（去重，保留评分最高）。"""
    seen = {}
    for o in store.list_opportunities():
        name = (o.get("company_name") or "").strip()
        if not name:
            continue
        if name not in seen or o.get("score", 0) > seen[name]:
            seen[name] = o.get("score", 0)
    ranked = sorted(seen, key=lambda k: -seen[k])
    return ranked[:n]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--top", type=int, default=20)
    ap.add_argument("--company", default=None)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--show", action="store_true", help="仅查询已生成的画像卡并打印 JSON")
    args = ap.parse_args()

    cfg = load_config()
    store.init_db()
    if args.show:
        if not args.company:
            print(json.dumps({"error": "--show 需要 --company"}, ensure_ascii=False))
            sys.exit(1)
        ins = store.get_insight(args.company)
        if not ins:
            print(json.dumps({"company": args.company, "exists": False,
                              "message": f"暂无 {args.company} 的画像卡，可运行 python engines/build_insights.py --company {args.company} 生成"},
                             ensure_ascii=False))
            sys.exit(0)
        print(json.dumps(ins, ensure_ascii=False, indent=2))
        sys.exit(0)
    companies = [args.company] if args.company else top_companies(args.top)
    if not companies:
        print("[result] 队列为空，无可生成画像的公司")
        return

    key = os.environ.get(cfg["rag"]["llm"]["api_key_env"])
    client = None
    if key:
        from openai import OpenAI
        client = OpenAI(base_url=cfg["rag"]["llm"]["base_url"], api_key=key)
    else:
        print(f"[warn] 环境变量 {cfg['rag']['llm']['api_key_env']} 未设置，使用 dry-run 模式输出提示词", file=sys.stderr)

    ok = skipped = 0
    for company in companies:
        out = build_one(company, client, cfg, dry_run=(args.dry_run or client is None))
        if out.get("dry_run"):
            print(f"[dry-run] {company} 提示词已生成（{len(out['prompt'])} 字符）")
            ok += 1
            continue
        if out.get("skipped"):
            skipped += 1
            print(f"[skip] {company}: {out.get('reason')}")
            continue
        save_insight(company, out["insight"])
        ok += 1
        i = out["insight"]
        conf = i.get("confidence") or {}
        conf = conf.get("value") if isinstance(conf, dict) else conf
        print(f"[ok] {company} | confidence={conf}")
    print(f"[result] 画像成功 {ok} 条，跳过 {skipped} 条")


if __name__ == "__main__":
    main()
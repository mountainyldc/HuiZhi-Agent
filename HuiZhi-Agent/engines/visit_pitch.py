# -*- coding: utf-8 -*-
"""拜访话术生成器：输入公司名 -> 检索公告/年报证据 + 画像 -> DeepSeek 生成客户经理可直接照读的话术。

输出结构（JSON）：
  opening    30 秒电话开场白（口语、可照读）
  outline    上门拜访提纲（3-5 步）
  products   与该企业币种/规模匹配的产品建议
  objections 常见异议应对话术（2-3 条）
  key_facts  话术依赖的关键事实（每条带来源，供抽查）

硬约束：具体数字/事实必须来自检索证据，无证据内容不写或标「需核实」。

用法:
  python visit_pitch.py --company 东鹏饮料
  python visit_pitch.py --company 东鹏饮料 --json
  python visit_pitch.py --company 东鹏饮料 --dry-run
"""
import argparse
import datetime
import json
import os
import re
import sys

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from common import load_config
from retrieve import retrieve
import store

SYSTEM_PROMPT = (
    "你是工商银行深圳分行金融市场部资深客户经理，负责为外汇业务商机生成拜访话术。"
    "你只输出 JSON，不输出任何其他内容。"
    "硬性要求：1) 话术要像客户经理说出口的话，口语、可照读，不要泛泛而谈；"
    "2) 电话与上门拜访两种场景分开；3) 具体数字、币种、额度、日期必须来自证据，"
    "证据里没有的一律不写或标「需核实」；4) 内容与商机详情保持一致；"
    "5) 对行内产品政策的描述保持审慎，不承诺收益、不贬低同业。"
)

OUTPUT_SCHEMA = {
    "opening": "30秒电话开场白（约80-120字，口语，可照读）",
    "outline": ["上门拜访提纲，3-5步，每步一句话，含目标"],
    "products": ["产品建议，2-3条，注明适用场景，无依据写待评估"],
    "objections": ["常见异议应对话术，2-3条，每条含客户异议与回应"],
    "key_facts": [{"fact": "话术依赖的关键事实", "source": "来源", "date": "披露日期"}],
}


def build_prompt(company):
    evidence = retrieve("外汇需求 套期保值 境外收入 跨境结算 汇率风险", company=company, top_n=6)
    blocks = []
    for i, e in enumerate(evidence, start=1):
        blocks.append(
            f"[来源{i}] 公司：{e.get('company','')}\n标题：{e.get('title','')}\n"
            f"日期：{e.get('publish_date','')}\n链接：{e.get('url','')}\n内容：{e.get('text','')[:900]}"
        )
    opps = [o for o in store.list_opportunities() if (o.get("company_name") or "") == company]
    opp_line = ""
    if opps:
        top = opps[0]
        biz = top.get("biz") or {}
        opp_line = (
            f"商机线索：触发事件={top.get('trigger_event','')}；"
            f"潜在业务={biz.get('biz_type','待判断')}（{biz.get('biz_sub','')}）；"
            f"币种={biz.get('currency','待核实')}；国家/地区={biz.get('country','待核实')}；规则分={top.get('score')}"
        )
    ins = store.get_insight(company)
    ins_line = ""
    if ins:
        fields = []
        for k, label in (("revenue_scale", "营收规模"), ("fx_exposure_direction", "外汇敞口方向"),
                         ("hedge_history", "历史套保"), ("recommended_products", "建议产品")):
            try:
                v = json.loads(ins.get(k) or "{}")
                fields.append(f"{label}={v.get('value','未披露')}")
            except Exception:
                fields.append(f"{label}=未披露")
        ins_line = "企业画像：" + "；".join(fields)

    user = (
        "请为公司「" + company + "」生成拜访话术，输出严格符合以下 JSON 结构的对象：\n"
        + json.dumps(OUTPUT_SCHEMA, ensure_ascii=False, indent=2)
        + "\n\n检索证据：\n" + ("\n\n".join(blocks) if blocks else "（无检索证据，全部相关表述必须标「需核实」）")
        + ("\n\n" + opp_line if opp_line else "")
        + ("\n\n" + ins_line if ins_line else "")
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


def generate(company, dry_run=False):
    cfg = load_config()
    llm = cfg["rag"]["llm"]
    key = os.environ.get(llm["api_key_env"])
    if not key:
        return {"company": company, "skipped": True, "reason": "未设置 DEEPSEEK_API_KEY"}
    prompt = build_prompt(company)
    if dry_run:
        return {"company": company, "dry_run": True, "prompt": prompt}
    from openai import OpenAI
    client = OpenAI(base_url=llm["base_url"], api_key=key)
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": prompt},
    ]
    try:
        resp = client.chat.completions.create(
            model=llm["model"], messages=messages,
            response_format={"type": "json_object"}, temperature=0.4, timeout=120,
        )
        content = resp.choices[0].message.content
    except Exception as exc:
        return {"company": company, "skipped": True, "reason": f"调用失败: {exc}"}
    parsed = parse_json_text(content)
    if not parsed:
        return {"company": company, "skipped": True, "reason": "模型输出无法解析为 JSON"}
    parsed["company"] = company
    parsed["generated_at"] = datetime.datetime.now().isoformat(timespec="seconds")
    return {"company": company, "skipped": False, "pitch": parsed}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--company", required=True)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    res = generate(args.company, dry_run=args.dry_run)
    if args.dry_run:
        print(json.dumps(res, ensure_ascii=False, indent=2))
        return
    if res.get("skipped"):
        print(json.dumps(res, ensure_ascii=False, indent=2))
        sys.exit(1)
    if args.json:
        print(json.dumps(res["pitch"], ensure_ascii=False, indent=2))
        return
    p = res["pitch"]
    print(f"公司：{p['company']}")
    print("\n【30 秒电话开场白】\n" + p.get("opening", "（无）"))
    print("\n【上门拜访提纲】")
    for i, s in enumerate(p.get("outline", []), start=1):
        print(f"  {i}. {s}")
    print("\n【产品建议】")
    for s in p.get("products", []):
        print(f"  - {s}")
    print("\n【常见异议应对】")
    for s in p.get("objections", []):
        print(f"  - {s}")
    print("\n【关键事实】")
    for f in p.get("key_facts", []):
        print(f"  - {f.get('fact','')} | {f.get('source','')} {f.get('date','')}")


if __name__ == "__main__":
    main()
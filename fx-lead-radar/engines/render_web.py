"""Web 渲染引擎：由队列快照生成自包含的静态 HTML（零依赖，可直接双击打开）。

用法:
  python render_web.py                     # 用最新快照渲染 web/index.html
  python render_web.py --input <snapshot>  # 指定快照
  python render_web.py --out <path>        # 指定输出
"""
import argparse
import json
import os

from common import load_config, project_path

TEMPLATE = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>外汇与国际业务商机雷达</title>
<style>
  :root { --red:#C8102E; --dark:#1f2430; --bg:#f4f5f7; --card:#fff; --muted:#7a8194; --line:#e5e7eb; }
  * { box-sizing:border-box; margin:0; padding:0; }
  body { font-family:"Microsoft YaHei","PingFang SC",sans-serif; background:var(--bg); color:#222; }
  header { background:var(--dark); color:#fff; padding:12px 20px; display:flex; justify-content:space-between; align-items:center; }
  header h1 { font-size:18px; font-weight:600; }
  header h1 span { color:#ff5a6e; }
  header .meta { font-size:13px; color:#b8bfcc; display:flex; gap:16px; }
  main { display:flex; height:calc(100vh - 52px); }
  #queue { width:420px; min-width:320px; background:var(--card); border-right:1px solid var(--line); overflow-y:auto; }
  #queue .qhead { padding:14px 16px; border-bottom:1px solid var(--line); }
  #queue .qhead h2 { font-size:15px; }
  #queue .qhead p { font-size:12px; color:var(--muted); margin-top:4px; }
  .qitem { padding:12px 16px; border-bottom:1px solid var(--line); cursor:pointer; }
  .qitem:hover { background:#fafbfc; }
  .qitem.active { background:#fdeef0; border-left:3px solid var(--red); }
  .qitem .row1 { display:flex; align-items:baseline; gap:8px; }
  .qitem .rank { color:var(--muted); font-size:13px; min-width:18px; }
  .qitem .company { font-weight:600; font-size:14px; }
  .qitem .city { color:var(--muted); font-size:12px; }
  .qitem .title { font-size:12px; color:#444; margin:4px 0 6px; line-height:1.5; }
  .qitem .score { margin-left:auto; color:var(--red); font-weight:700; font-size:15px; }
  .tag { display:inline-block; background:#f1f2f5; color:#4a5060; border-radius:3px; padding:1px 6px; font-size:11px; margin-right:4px; }
  #detail { flex:1; overflow-y:auto; padding:20px 24px; }
  .card { background:var(--card); border:1px solid var(--line); border-radius:6px; padding:16px 18px; margin-bottom:14px; }
  .card h3 { font-size:13px; color:#333; margin-bottom:10px; display:flex; align-items:center; gap:6px; }
  .card h3 .badge { font-size:11px; color:var(--red); background:#fdeef0; border:1px solid #f5c6cc; padding:1px 6px; border-radius:3px; font-weight:400; }
  .dtop { display:flex; align-items:center; gap:12px; }
  .dtop .name { font-size:17px; font-weight:700; }
  .dtop .tag.on { background:#e4f7ec; color:#1a7f4b; border:1px solid #b8e6cd; }
  .scorebox { margin-left:auto; text-align:center; }
  .scorebox .num { font-size:34px; font-weight:800; color:#1a7f4b; line-height:1; }
  .scorebox .lab { font-size:11px; color:var(--muted); }
  .life { display:flex; gap:6px; font-size:12px; color:var(--muted); margin-top:8px; }
  .life .st { padding:2px 8px; border:1px solid var(--line); border-radius:10px; }
  .life .st.on { border-color:#1a7f4b; color:#1a7f4b; }
  .kv { display:flex; flex-wrap:wrap; gap:8px 24px; font-size:13px; }
  .kv b { color:#555; font-weight:600; }
  .bar-row { display:flex; align-items:center; gap:8px; margin-bottom:6px; font-size:12px; }
  .bar-row .bk { width:110px; color:#666; }
  .bar { flex:1; height:8px; background:#eef0f3; border-radius:4px; overflow:hidden; }
  .bar i { display:block; height:100%; background:var(--red); }
  .bar-row .bv { width:36px; text-align:right; font-weight:600; }
  ul.facts { padding-left:18px; font-size:13px; line-height:1.9; }
  ul.unknown { color:#8a5a00; }
  ul.questions { padding-left:18px; font-size:13px; line-height:1.9; }
  .btns { display:flex; gap:10px; margin-top:6px; }
  .btn { border:none; border-radius:4px; padding:8px 18px; font-size:14px; cursor:pointer; }
  .btn.claim { background:#1a7f4b; color:#fff; }
  .btn.invalid { background:#fff; border:1px solid #c9ccd4; color:#555; }
  .foot { font-size:12px; color:var(--muted); margin-top:12px; }
  .evlink { color:var(--red); text-decoration:none; border-bottom:1px dashed #f0a0ab; }
  .evlink:hover { text-decoration:underline; }
  .evbtn { display:inline-block; background:var(--red); color:#fff; font-size:12px; padding:5px 12px; border-radius:4px; text-decoration:none; }
  .evbtn:hover { opacity:.88; }
  .empty { padding:40px; text-align:center; color:var(--muted); }
  #toast { position:fixed; left:50%; bottom:24px; transform:translateX(-50%); background:#333; color:#fff; padding:8px 16px; border-radius:4px; font-size:13px; display:none; }
</style>
</head>
<body>
<header>
  <h1>外汇与国际业务商机雷达</h1>
  <div class="meta"><span>地区：广东</span><span id="hdrDate"></span><span>用户：张经理</span></div>
</header>
<main>
  <div id="queue">
    <div class="qhead">
      <h2>今日商机队列</h2>
      <p id="qsub"></p>
    </div>
    <div id="qlist"></div>
  </div>
  <div id="detail"><div class="empty">点击左侧商机查看详情</div></div>
</main>
<div id="toast"></div>
<script>
const SNAPSHOT = __SNAPSHOT_JSON__;
const items = SNAPSHOT.items || [];
document.getElementById("hdrDate").textContent = SNAPSHOT.date + " 生成于 " + (SNAPSHOT.generated_at || "").slice(0,16);
document.getElementById("qsub").textContent = "数据源：巨潮资讯 · 规则初筛 · " + (SNAPSHOT.generated_at || "").slice(11,16);

function tagHtml(tags){ return (tags||[]).map(t=>`<span class="tag">${t}</span>`).join(""); }
function esc(s){ return (s==null?"":String(s)).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;"); }

function renderList(activeId){
  const el = document.getElementById("qlist");
  if(!items.length){ el.innerHTML = '<div class="empty">暂无商机</div>'; return; }
  el.innerHTML = items.map(it=>`
    <div class="qitem ${it.opportunity_id===activeId?"active":""}" data-id="${it.opportunity_id}">
      <div class="row1"><span class="rank">${it.rank}</span><span class="company">${esc(it.company_name)}</span><span class="city">${esc(it.city)}</span><span class="score">${it.score}</span></div>
      <div class="title">${esc(it.title)}</div>
      ${tagHtml(it.tags)}
    </div>`).join("");
  el.querySelectorAll(".qitem").forEach(n=>n.addEventListener("click",()=>showDetail(n.dataset.id)));
}

function scoreBars(b){
  if(!b) return "";
  const names={event_credibility:"事件可信度",capital_scale:"资金体量",timeliness:"时效性",coverage:"我行覆盖度",info_completeness:"信息完整度"};
  return Object.keys(b).map(k=>`
    <div class="bar-row"><span class="bk">${names[k]||k}</span>
      <div class="bar"><i style="width:${b[k]}%"></i></div><span class="bv">${b[k]}</span></div>`).join("");
}

function evHref(it, evidence){
  if(it.evidence_url) return it.evidence_url;
  const q = encodeURIComponent((it.company_name||"")+" "+(evidence.doc_title||it.title||""));
  return "https://www.baidu.com/s?wd="+q;
}
function evDocLink(it, evidence){
  const title = evidence.doc_title || it.title || "（无标题）";
  return `<a class="evlink" href="${evHref(it,evidence)}" target="_blank" rel="noopener">${esc(title)}</a>`;
}
function evLabel(it){
  return it.evidence_url ? "查看原文 ↗" : "搜索相关报道 ↗";
}
function showDetail(id){
  const it = items.find(x=>x.opportunity_id===id); if(!it) return;
  renderList(id);
  const rev = it.review || {};
  const evidence = rev.evidence_summary || {};
  const lifeMap = {new:"新发现", verifying:"待核实", contacted:"已联系", invalid:"无效"};
  const lifeOrder = ["new","verifying","contacted"];
  document.getElementById("detail").innerHTML = `
    <div class="card">
      <div class="dtop">
        <div><div class="name">${esc(it.company_name)}<span style="font-size:13px;color:#777">（${esc(it.city)}）</span></div>
          <div style="margin-top:6px">${tagHtml(it.tags)}</div></div>
        <div class="scorebox"><div class="num">${it.score}</div><div class="lab">商机分</div></div>
      </div>
      <div class="life">${lifeOrder.map(s=>`<span class="st ${it.lifecycle===s?"on":""}">● ${lifeMap[s]}</span>`).join("")}
        ${it.lifecycle==="invalid"?`<span class="st on">● 无效</span>`:""}</div>
    </div>
    <div class="card"><h3>触发事件</h3><div style="font-size:13px">${esc(it.trigger_event)}</div>
      <div style="font-size:12px;color:#1a7f4b;margin-top:6px">规则命中：${(it.rule_hits||[]).join(" + ")}</div></div>
    <div class="card"><h3>证据摘要</h3>
      <div class="kv"><span><b>文档：</b>${evDocLink(it,evidence)}</span>
      <span><b>来源：</b>${esc(evidence.source||it.source||"")}</span>
      <span><b>时间：</b>${esc(evidence.publish_time||it.publish_date||"")}</span></div>
      <div style="margin-top:12px"><a class="evbtn" href="${evHref(it,evidence)}" target="_blank" rel="noopener">${evLabel(it,evidence)}</a>
      <span style="font-size:11px;color:var(--muted);margin-left:8px">${it.evidence_url?"点击打开公告/快讯原文":"未收录直接原文，点击搜索相关报道"}</span></div></div>
    <div class="card"><h3>已知事实 <span class="badge">AI提取</span></h3>
      <ul class="facts">${(rev.known_facts||[]).map(f=>`<li>${esc(f)}</li>`).join("")||"<li>（暂无）</li>"}</ul></div>
    <div class="card"><h3>未知 / 待核实</h3>
      <ul class="facts unknown">${(rev.unknown_facts||[]).map(f=>`<li>${esc(f)}</li>`).join("")||"<li>（暂无）</li>"}</ul></div>
    <div class="card"><h3>规则商机评分 ${rev.reviewed_score?`<span class="badge">大模型复核 ${rev.reviewed_score} 分</span>`:`<span class="badge">待大模型复核</span>`}</h3>
      ${scoreBars(it.score_breakdown)}
      <div style="font-size:12px;color:#777;margin-top:6px">${esc(rev.review_note||"评分由规则引擎按5维加权计算")}</div></div>
    <div class="card"><h3>建议客户沟通问题 <span class="badge">供参考</span></h3>
      <ul class="questions">${(rev.suggested_questions||[]).map(q=>`<li>${esc(q)}</li>`).join("")||"<li>（暂无）</li>"}</ul></div>
    <div class="card"><div class="btns">
        <button class="btn claim" onclick="action('${it.opportunity_id}','claim')">认领商机 ></button>
        <button class="btn invalid" onclick="action('${it.opportunity_id}','invalid')">标记无效</button></div>
      <div class="foot">认领后将进入线索管理，由您跟进${it.owner?`（当前负责人：${esc(it.owner)}）`:""}</div></div>`;
}

async function action(id, act){
  const it = items.find(x=>x.opportunity_id===id);
  try{
    const r = await fetch("/action",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({opportunity_id:id,action:act,owner:"张经理"})});
    if(!r.ok) throw new Error("http "+r.status);
    const j = await r.json();
    toast(j.message||"已更新");
    location.reload();
  }catch(e){
    // 静态模式兜底：仅本次会话生效
    it.lifecycle = act==="claim" ? "verifying" : "invalid";
    if(act==="claim") it.owner = "张经理";
    toast("静态模式：状态仅本次会话生效（启动 serve.py 可持久化）");
    showDetail(id);
  }
}
function toast(msg){ const t=document.getElementById("toast"); t.textContent=msg; t.style.display="block"; setTimeout(()=>t.style.display="none",2600); }

renderList(null);
if(items.length) showDetail(items[0].opportunity_id);
</script>
</body>
</html>
"""


def render(input_path=None, out=None):
    cfg = load_config()
    if input_path is None:
        snap_dir = project_path("data/queue_snapshots")
        files = sorted(f for f in os.listdir(snap_dir) if f.endswith(".json"))
        if not files:
            raise FileNotFoundError("没有队列快照，请先运行 build_queue.py")
        input_path = os.path.join(snap_dir, files[-1])
    with open(input_path, encoding="utf-8") as f:
        snapshot = json.load(f)
    html = TEMPLATE.replace("__SNAPSHOT_JSON__", json.dumps(snapshot, ensure_ascii=False))
    out = out or project_path(cfg["web"]["output"])
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        f.write(html)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", default=None)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    out = render(args.input, args.out)
    print(f"[result] 已渲染: {out}")


if __name__ == "__main__":
    main()
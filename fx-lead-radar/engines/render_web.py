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
<title>中国工商银行 · 外汇与国际业务商机雷达</title>
<style>
  :root {
    --red: #C8102E;
    --red-dark: #A60D26;
    --ink: #1F2733;
    --ink-2: #5A6472;
    --ink-3: #9AA3AF;
    --bg: #F4F5F7;
    --card: #FFFFFF;
    --line: #E3E6EA;
    --green: #1F9D63;
    --amber: #D98324;
  }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  html, body { height: 100%; }
  body {
    font-family: "Microsoft YaHei", "PingFang SC", "Segoe UI", sans-serif;
    background: var(--bg); color: var(--ink); font-size: 14px;
  }
  /* 顶栏：白底 + 工行红底线 */
  header {
    display: flex; align-items: center; gap: 16px;
    padding: 0 24px; height: 58px;
    background: var(--card); border-bottom: 2px solid var(--red);
  }
  .brand { display: flex; align-items: center; gap: 12px; }
  .icbc {
    background: var(--red); color: #fff; font-weight: 800;
    letter-spacing: 1px; padding: 6px 12px; font-size: 13px; white-space: nowrap;
  }
  .brand .name { font-size: 16px; font-weight: 700; }
  .vline { width: 1px; height: 24px; background: var(--line); }
  .page-title { font-size: 13px; color: var(--ink-3); letter-spacing: .5px; }
  header .meta { margin-left: auto; display: flex; gap: 22px; font-size: 13px; color: var(--ink-2); }
  header .meta b { color: var(--ink); font-weight: 600; }
  /* KPI 卡片 */
  .stats { display: grid; grid-template-columns: repeat(4, 1fr); gap: 14px; padding: 18px 24px 0; }
  .kpi {
    background: var(--card); border: 1px solid var(--line); border-top: 3px solid var(--red);
    padding: 14px 18px; display: flex; align-items: baseline; gap: 10px;
  }
  .kpi .num { font-size: 26px; font-weight: 800; color: var(--red); font-variant-numeric: tabular-nums; }
  .kpi .num.plain { color: var(--ink); }
  .kpi .lab { font-size: 13px; color: var(--ink-2); }
  /* 主区 */
  main { display: flex; height: calc(100vh - 216px); padding: 16px 24px 24px; gap: 16px; }
  #queue {
    width: 420px; min-width: 340px; display: flex; flex-direction: column;
    background: var(--card); border: 1px solid var(--line);
  }
  .qhead { padding: 13px 16px; border-bottom: 1px solid var(--line); display: flex; align-items: center; }
  .qhead h2 { font-size: 15px; font-weight: 700; }
  .qhead h2::before { content: ""; display: inline-block; width: 4px; height: 15px; background: var(--red); margin-right: 8px; vertical-align: -2px; }
  .qhead p { margin-left: auto; font-size: 12px; color: var(--ink-3); }
  #qlist { flex: 1; overflow-y: auto; padding: 8px 8px 18px; }
  .qitem {
    padding: 12px; border-bottom: 1px solid #EFF1F4; cursor: pointer;
    border-left: 3px solid transparent;
  }
  .qitem:hover { background: #FAFBFC; }
  .qitem.active { background: #FDF3F4; border-left-color: var(--red); }
  .row1 { display: flex; align-items: center; gap: 8px; }
  .rank { font-size: 12px; color: var(--ink-3); width: 22px; font-weight: 700; font-variant-numeric: tabular-nums; }
  .rank.top { color: var(--red); }
  .company { font-weight: 700; font-size: 15px; }
  .city { font-size: 12px; color: var(--ink-3); }
  .score { margin-left: auto; font-weight: 800; color: var(--red); font-size: 16px; }
  .score small { font-size: 11px; color: var(--ink-3); font-weight: 400; }
  .qtitle {
    font-size: 12.5px; color: var(--ink-2); margin: 6px 0; line-height: 1.5;
    display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden;
  }
  .tags { display: flex; gap: 6px; flex-wrap: wrap; }
  .tag { font-size: 11px; padding: 2px 8px; background: #F0F2F5; color: var(--ink-2); border-radius: 2px; }
  .tag.t1 { background: #FDEBED; color: var(--red); }
  .src { font-size: 11px; color: var(--ink-3); margin-left: auto; white-space: nowrap; }
  /* 详情 */
  #detail { flex: 1; overflow-y: auto; display: flex; flex-direction: column; gap: 14px; padding-bottom: 18px; }
  .card { background: var(--card); border: 1px solid var(--line); padding: 18px 20px; }
  .card h3 { font-size: 13px; color: var(--ink-2); font-weight: 700; margin-bottom: 10px; }
  .card h3::before { content: ""; display: inline-block; width: 3px; height: 13px; background: var(--red); margin-right: 8px; vertical-align: -1px; }
  .hero { display: flex; justify-content: space-between; align-items: flex-start; }
  .name { font-size: 22px; font-weight: 800; }
  .sub { margin-top: 8px; display: flex; gap: 6px; flex-wrap: wrap; }
  .gscore { text-align: right; }
  .gscore .big { font-size: 34px; font-weight: 800; color: var(--red); line-height: 1; }
  .gscore .lbl { font-size: 12px; color: var(--ink-3); margin-top: 4px; }
  .gbar { width: 150px; height: 4px; background: #EEF0F3; margin-top: 8px; margin-left: auto; }
  .gbar i { display: block; height: 100%; background: var(--red); }
  .life { display: flex; gap: 8px; margin-top: 14px; }
  .pill { font-size: 12px; padding: 3px 10px; color: var(--ink-3); background: #F0F2F5; border-radius: 2px; }
  .pill.on.new { color: var(--red); background: #FDEBED; }
  .pill.on.verifying { color: var(--amber); background: #FBF1E3; }
  .pill.on.contacted { color: var(--green); background: #E7F5EE; }
  .pill.on.invalid { color: var(--ink-3); background: #EEF0F3; }
  .trigger { font-size: 13.5px; line-height: 1.7; }
  .rule { display: inline-block; font-size: 11px; color: var(--red); background: #FDEBED; padding: 2px 8px; margin-top: 8px; border-radius: 2px; }
  .kv { display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; font-size: 13px; color: var(--ink-2); margin-bottom: 12px; }
  .kv span { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .kv b { color: var(--ink); font-weight: 600; }
  .evlink { color: var(--red); text-decoration: none; }
  .evlink:hover { text-decoration: underline; }
  .evrow { display: flex; align-items: center; gap: 12px; }
  .evbtn {
    display: inline-block; border: 1px solid var(--red); color: var(--red);
    padding: 7px 18px; font-size: 13px; font-weight: 700; text-decoration: none;
  }
  .evbtn:hover { background: #FDEBED; }
  .evbtn.alt { border-color: var(--ink-3); color: var(--ink-2); }
  .evnote { font-size: 12px; color: var(--ink-3); }
  .two { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; }
  .two .kv { grid-template-columns: 1fr; }
  .factlist { list-style: none; }
  .factlist li { font-size: 13px; line-height: 1.7; padding-left: 16px; position: relative; color: var(--ink-2); }
  .factlist.known li::before { content: "●"; position: absolute; left: 0; font-size: 8px; color: var(--green); top: 7px; }
  .factlist.unknown li::before { content: "○"; position: absolute; left: 0; font-size: 10px; color: var(--amber); top: 5px; }
  .bar-row { display: flex; align-items: center; gap: 10px; margin-bottom: 8px; }
  .bar-row .bk { width: 88px; font-size: 12.5px; color: var(--ink-2); }
  .bar { flex: 1; height: 6px; background: #EEF0F3; }
  .bar i { display: block; height: 100%; background: var(--red); }
  .bar-row .bv { width: 32px; text-align: right; font-size: 12.5px; font-weight: 700; color: var(--ink); }
  .qlist { padding-left: 18px; }
  .qlist li { font-size: 13px; line-height: 1.8; color: var(--ink-2); }
  .btns { display: flex; gap: 10px; }
  .btn {
    border: 1px solid var(--line); background: var(--card); color: var(--ink-2);
    padding: 9px 22px; font-size: 13px; font-weight: 700; cursor: pointer;
  }
  .btn.claim { background: var(--red); border-color: var(--red); color: #fff; }
  .btn.claim:hover { background: var(--red-dark); }
  .btn.invalid:hover { border-color: var(--red); color: var(--red); }
  .foot { font-size: 12px; color: var(--ink-3); margin-top: 12px; }
  footer {
    display: flex; gap: 22px; padding: 9px 24px; font-size: 12px; color: var(--ink-3);
    background: var(--card); border-top: 1px solid var(--line);
  }
  .empty { padding: 60px; text-align: center; color: var(--ink-3); }
  #toast {
    position: fixed; left: 50%; bottom: 34px; transform: translateX(-50%) translateY(16px); opacity: 0;
    background: #333A45; color: #fff; padding: 10px 20px; font-size: 13px; z-index: 99;
    transition: all .2s ease;
  }
  #toast.show { opacity: 1; transform: translateX(-50%) translateY(0); }
  @media (max-width: 1100px) {
    .stats { grid-template-columns: repeat(2, 1fr); }
    .two { grid-template-columns: 1fr; }
    .kv { grid-template-columns: 1fr; }
    #queue { width: 360px; }
  }
</style>
</head>
<body>
<header>
  <div class="brand">
    <span class="icbc">ICBC 中国工商银行</span>
    <div class="name">外汇与国际业务商机雷达</div>
    <span class="vline"></span>
    <span class="page-title">Foreign Exchange Lead Radar · 深圳分行</span>
  </div>
  <div class="meta">
    <span>地区 <b>广东</b></span>
    <span id="hdrDate"></span>
    <span>用户 <b>张经理</b></span>
  </div>
</header>

<div class="stats">
  <div class="kpi"><div class="num" id="kTotal">0</div><div class="lab">今日商机线索</div></div>
  <div class="kpi"><div class="num plain" id="kAvg">0</div><div class="lab">平均商机分</div></div>
  <div class="kpi"><div class="num plain" id="kVerifying">0</div><div class="lab">待核实</div></div>
  <div class="kpi"><div class="num plain" id="kClaimed">0</div><div class="lab">已认领</div></div>
</div>

<main>
  <div id="queue">
    <div class="qhead"><h2>今日商机队列</h2><p id="qsub"></p></div>
    <div id="qlist"></div>
  </div>
  <div id="detail"></div>
</main>

<footer>
  <span>AI 引擎：Pi Coding Agent + DeepSeek 复核</span>
  <span>证据可点击：公告原文 PDF / 相关报道搜索</span>
  <span id="genTime"></span>
</footer>

<div id="toast"></div>

<script>
const data = __SNAPSHOT_JSON__; const items = Array.isArray(data) ? data : (data.items || []);
function esc(s){ return String(s==null?"":s).replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c])); }
function tagHtml(tags){ return (tags||[]).map(t=>`<span class="tag ${t.includes("外汇")||t.includes("套保")?"t1":""}">${esc(t)}</span>`).join(""); }
function scoreBars(b){
  if(!b) return "";
  const names = {event_credibility:"事件可信度", capital_scale:"资金体量", timeliness:"时效性", coverage:"我行覆盖度", info_completeness:"信息完整度"};
  return Object.entries(b).map(([k,v])=>`<div class="bar-row"><span class="bk">${esc(names[k]||k)}</span><div class="bar"><i style="width:${v}%"></i></div><span class="bv">${v}</span></div>`).join("");
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
function evLabel(it){ return it.evidence_url ? "查看原文" : "搜索相关报道"; }
function renderList(activeId){
  document.getElementById("qlist").innerHTML = items.map(it=>`
    <div class="qitem ${it.opportunity_id===activeId?"active":""}" onclick="showDetail('${it.opportunity_id}')">
      <div class="row1">
        <span class="rank ${it.rank<=3?"top":""}">${String(it.rank==null?"":it.rank).padStart(2,"0")}</span>
        <span class="company">${esc(it.company_name)}</span>
        <span class="city">${esc(it.city)}</span>
        <span class="score">${it.score}<small> 分</small></span>
      </div>
      <div class="qtitle">${esc(it.title)}</div>
      <div style="display:flex;align-items:center;gap:6px">
        <span class="tags">${tagHtml(it.tags.slice(0,2))}</span>
        <span class="src">${esc(it.source||"")}</span>
      </div>
    </div>`).join("");
  const newCount = items.filter(i=>i.lifecycle==="new").length;
  document.getElementById("qsub").textContent = items.length ? `${items.length} 条 · 新发现 ${newCount}` : "";
}
function showDetail(id){
  const it = items.find(x=>x.opportunity_id===id); if(!it) return;
  renderList(id);
  const rev = it.review || {};
  const evidence = rev.evidence_summary || {};
  const lifeMap = {new:"新发现", verifying:"待核实", contacted:"已联系", invalid:"无效"};
  const lifeKey = {new:"new", verifying:"verifying", contacted:"contacted", invalid:"invalid"};
  const lifeOrder = ["new","verifying","contacted"];
  const scorePct = Math.max(0, Math.min(100, it.score||0));
  document.getElementById("detail").innerHTML = `
    <div class="card">
      <div class="hero">
        <div>
          <div class="name">${esc(it.company_name)} <span style="font-size:14px;color:var(--ink-3);font-weight:400">（${esc(it.city)}）</span></div>
          <div class="sub">${tagHtml(it.tags)}</div>
        </div>
        <div class="gscore">
          <div class="big">${it.score}</div>
          <div class="lbl">商机分 · 满分 100</div>
          <div class="gbar"><i style="width:${scorePct}%"></i></div>
        </div>
      </div>
      <div class="life">${lifeOrder.map(s=>`<span class="pill ${it.lifecycle===s?"on "+lifeKey[s]:""}">${lifeMap[s]}</span>`).join("")}
        ${it.lifecycle==="invalid"?`<span class="pill on invalid">无效</span>`:""}</div>
    </div>

    <div class="two">
    <div class="card"><h3>触发事件</h3>
      <div class="trigger">${esc(it.trigger_event)}</div>
      <div class="rule">规则命中：${(it.rule_hits||[]).join(" · ")}</div>
    </div>

    <div class="card"><h3>证据摘要</h3>
      <div class="kv">
        <span><b>文档：</b>${evDocLink(it,evidence)}</span>
        <span><b>来源：</b>${esc(evidence.source||it.source||"")}</span>
        <span><b>时间：</b>${esc(evidence.publish_time||it.publish_date||"")}</span>
      </div>
      <div class="evrow">
        <a class="evbtn ${it.evidence_url?"":"alt"}" href="${evHref(it,evidence)}" target="_blank" rel="noopener">${evLabel(it)} ↗</a>
        <span class="evnote">${it.evidence_url?"点击打开公告 / 快讯原文":"未收录直接原文，点击搜索相关报道"}</span>
      </div>
    </div>


    </div>

    <div class="two">
      <div class="card"><h3>已知事实 · AI 提取</h3>
        <ul class="factlist known">${(rev.known_facts||[]).map(f=>`<li>${esc(f)}</li>`).join("")||"<li>（暂无）</li>"}</ul></div>
      <div class="card"><h3>待核实</h3>
        <ul class="factlist unknown">${(rev.unknown_facts||[]).map(f=>`<li>${esc(f)}</li>`).join("")||"<li>（暂无）</li>"}</ul></div>
    </div>

    <div class="card"><h3>商机评分 ${rev.reviewed_score?`<span style="font-size:12px;color:var(--red)">· 大模型复核 ${rev.reviewed_score} 分</span>`:`<span style="font-size:12px;color:var(--ink-3)">· 待大模型复核</span>`}</h3>
      ${scoreBars(it.score_breakdown)}
      <div style="font-size:12px;color:var(--ink-3);margin-top:8px">${esc(rev.review_note||"评分由规则引擎按 5 维加权计算")}</div>
    </div>

    <div class="card"><h3>建议客户沟通问题</h3>
      <ol class="qlist">${(rev.suggested_questions||[]).map(q=>`<li>${esc(q)}</li>`).join("")||"<li>（暂无）</li>"}</ol>
    </div>

    <div class="card"><div class="btns">
        <button class="btn claim" onclick="action('${it.opportunity_id}','claim')">认领商机</button>
        <button class="btn invalid" onclick="action('${it.opportunity_id}','invalid')">标记无效</button></div>
      <div class="foot">认领后将进入线索管理，由您跟进${it.owner?`（当前负责人：${esc(it.owner)}）`:""}</div>
    </div>`;
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
    it.lifecycle = act==="claim" ? "verifying" : "invalid";
    if(act==="claim") it.owner = "张经理";
    toast("静态模式：状态仅本次会话生效（启动 serve.py 可持久化）");
    showDetail(id);
  }
}
function toast(msg){
  const t=document.getElementById("toast");
  t.textContent=msg; t.classList.add("show");
  setTimeout(()=>t.classList.remove("show"),2600);
}
function renderKPIs(){
  document.getElementById("kTotal").textContent = items.length;
  if(items.length){
    const avg = Math.round(items.reduce((s,i)=>s+i.score,0)/items.length);
    document.getElementById("kAvg").textContent = avg;
  }
  document.getElementById("kVerifying").textContent = items.filter(i=>i.lifecycle==="verifying").length;
  document.getElementById("kClaimed").textContent = items.filter(i=>i.owner).length;
}
document.getElementById("hdrDate").textContent = "日期 " + (items[0] && items[0].publish_date ? items[0].publish_date : "");
document.getElementById("genTime").textContent = "生成时间 " + new Date().toLocaleString("zh-CN");
renderKPIs();
renderList(null);
if(items.length) showDetail(items[0].opportunity_id);
</script>
</body>
</html>"""





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
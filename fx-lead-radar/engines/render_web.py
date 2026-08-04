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
<title>工商银行 · 外汇商机雷达</title>
<style>
  :root {
    --icbc:#C8102E; --icbc-2:#E8483A; --gold:#E8C15A; --gold-2:#F5DEA0;
    --bg0:#0A0F1E; --bg1:#0F1830; --card:rgba(255,255,255,.045);
    --line:rgba(255,255,255,.09); --line-2:rgba(255,255,255,.14);
    --text:#EEF2F9; --text2:#A9B3C7; --text3:#67718B;
    --blue:#5B8DEF; --green:#34D399; --amber:#F5B73F; --grey:#8A94AC;
  }
  * { box-sizing:border-box; margin:0; padding:0; }
  html,body { height:100%; }
  body {
    font-family:"Segoe UI","Microsoft YaHei","PingFang SC",sans-serif;
    color:var(--text); background:var(--bg0); overflow:hidden;
    background:
      radial-gradient(1100px 520px at 88% -12%, rgba(200,16,46,.20), transparent 62%),
      radial-gradient(900px 480px at -8% 112%, rgba(232,193,90,.10), transparent 60%),
      linear-gradient(158deg,#0A0F1E 0%,#101A32 52%,#0A0F1E 100%);
  }
  body::before {
    content:""; position:fixed; inset:0; pointer-events:none;
    background-image:
      linear-gradient(rgba(255,255,255,.028) 1px, transparent 1px),
      linear-gradient(90deg, rgba(255,255,255,.028) 1px, transparent 1px);
    background-size:44px 44px;
    mask-image:radial-gradient(1200px 700px at 50% 0%, #000 30%, transparent 80%);
  }
  /* ---------- 顶栏 ---------- */
  header {
    position:relative; z-index:5; display:flex; align-items:center; gap:16px;
    padding:14px 22px; border-bottom:1px solid var(--line);
    background:linear-gradient(180deg, rgba(16,24,48,.9), rgba(10,15,30,.55));
    backdrop-filter:blur(12px);
  }
  .brand { display:flex; align-items:center; gap:10px; }
  .brand .icbc {
    background:linear-gradient(135deg,#D81B32,#A80A24); color:#fff; font-weight:800;
    letter-spacing:1px; padding:5px 10px; border-radius:7px; font-size:13px;
    box-shadow:0 4px 18px rgba(200,16,46,.45), inset 0 1px 0 rgba(255,255,255,.25);
  }
  .brand .t1 { font-size:17px; font-weight:700; letter-spacing:.5px; }
  .brand .t2 { font-size:11px; color:var(--gold-2); letter-spacing:2px; margin-top:1px; }
  .brand .divider { width:1px; height:26px; background:var(--line-2); margin:0 6px; }
  header .meta { margin-left:auto; display:flex; gap:10px; }
  .chip {
    display:inline-flex; align-items:center; gap:6px; font-size:12px; color:var(--text2);
    border:1px solid var(--line); background:rgba(255,255,255,.04);
    padding:5px 12px; border-radius:20px;
  }
  .chip b { color:var(--text); font-weight:600; }
  .chip .dot { width:6px; height:6px; border-radius:50%; background:var(--green); box-shadow:0 0 8px var(--green); }

  /* ---------- KPI ---------- */
  .stats { position:relative; z-index:4; display:grid; grid-template-columns:repeat(4,1fr); gap:14px; padding:16px 22px 0; }
  .kpi {
    display:flex; align-items:center; gap:14px; padding:14px 18px; border-radius:14px;
    border:1px solid var(--line); background:linear-gradient(180deg,rgba(255,255,255,.055),rgba(255,255,255,.02));
    box-shadow:0 8px 24px rgba(0,0,0,.25);
  }
  .kpi .num { font-size:28px; font-weight:800; line-height:1; font-variant-numeric:tabular-nums; }
  .kpi .lab { font-size:12px; color:var(--text2); margin-top:6px; }
  .kpi .ico {
    width:44px; height:44px; border-radius:12px; display:flex; align-items:center; justify-content:center;
    font-size:20px; flex-shrink:0;
  }
  .kpi.r .num { color:var(--icbc-2); } .kpi.r .ico { background:rgba(200,16,46,.16); color:#FF7A6B; }
  .kpi.g .num { color:var(--gold); } .kpi.g .ico { background:rgba(232,193,90,.14); color:var(--gold); }
  .kpi.b .num { color:var(--blue); } .kpi.b .ico { background:rgba(91,141,239,.14); color:var(--blue); }
  .kpi.n .num { color:var(--green); } .kpi.n .ico { background:rgba(52,211,153,.13); color:var(--green); }

  main { position:relative; z-index:3; display:flex; height:calc(100vh - 158px); padding:16px 22px 22px; gap:16px; }

  /* ---------- 左：队列 ---------- */
  #queue {
    width:430px; min-width:360px; display:flex; flex-direction:column;
    border:1px solid var(--line); border-radius:16px; overflow:hidden;
    background:linear-gradient(180deg,rgba(255,255,255,.04),rgba(255,255,255,.015));
    backdrop-filter:blur(10px);
  }
  .qhead { padding:14px 18px; border-bottom:1px solid var(--line); display:flex; align-items:center; }
  .qhead h2 { font-size:15px; font-weight:700; display:flex; align-items:center; gap:8px; }
  .qhead h2::before { content:""; width:4px; height:16px; border-radius:2px; background:linear-gradient(180deg,var(--icbc-2),var(--icbc)); box-shadow:0 0 10px rgba(200,16,46,.6); }
  .qhead p { font-size:12px; color:var(--text3); margin-left:auto; }
  #qlist { flex:1; overflow-y:auto; padding:10px; }
  #qlist::-webkit-scrollbar, #detail::-webkit-scrollbar { width:8px; }
  #qlist::-webkit-scrollbar-thumb, #detail::-webkit-scrollbar-thumb { background:rgba(255,255,255,.12); border-radius:4px; }
  .qitem {
    position:relative; padding:12px 14px 12px 18px; margin-bottom:10px; border-radius:12px;
    border:1px solid transparent; cursor:pointer; transition:all .16s ease;
    background:rgba(255,255,255,.028);
  }
  .qitem:hover { background:rgba(255,255,255,.06); transform:translateY(-1px); }
  .qitem.active {
    background:linear-gradient(90deg, rgba(200,16,46,.16), rgba(255,255,255,.03) 70%);
    border-color:rgba(200,16,46,.45);
    box-shadow:0 6px 22px rgba(200,16,46,.12), inset 0 0 24px rgba(200,16,46,.05);
  }
  .qitem.active::before { content:""; position:absolute; left:0; top:10px; bottom:10px; width:3px; border-radius:3px; background:linear-gradient(180deg,var(--icbc-2),var(--icbc)); box-shadow:0 0 12px rgba(200,16,46,.8); }
  .row1 { display:flex; align-items:center; gap:10px; }
  .rank {
    width:26px; height:26px; border-radius:8px; display:flex; align-items:center; justify-content:center;
    font-size:13px; font-weight:800; color:var(--text2); background:rgba(255,255,255,.06); flex-shrink:0;
    font-variant-numeric:tabular-nums;
  }
  .qitem:nth-of-type(1) .rank, .qitem:nth-of-type(2) .rank, .qitem:nth-of-type(3) .rank { color:#12131A; }
  .qitem:nth-of-type(1) .rank { background:linear-gradient(135deg,#FFE9A8,#E8C15A); }
  .qitem:nth-of-type(2) .rank { background:linear-gradient(135deg,#E6EDF7,#B9C6DA); }
  .qitem:nth-of-type(3) .rank { background:linear-gradient(135deg,#F0C9A8,#D99B6C); }
  .company { font-weight:700; font-size:14.5px; }
  .city { font-size:11px; color:var(--text3); border:1px solid var(--line); padding:1px 7px; border-radius:10px; }
  .score { margin-left:auto; font-weight:800; font-size:17px; color:var(--icbc-2); font-variant-numeric:tabular-nums; }
  .score small { font-size:10px; color:var(--text3); font-weight:600; }
  .qtitle { font-size:12px; color:var(--text2); margin:7px 0 8px; line-height:1.5; display:-webkit-box; -webkit-line-clamp:2; -webkit-box-orient:vertical; overflow:hidden; }
  .tags { display:flex; flex-wrap:wrap; gap:5px; }
  .tag { font-size:10.5px; color:var(--text2); border:1px solid var(--line); background:rgba(255,255,255,.04); padding:2px 8px; border-radius:12px; }
  .tag.t1 { color:#FFB4A8; border-color:rgba(200,16,46,.4); background:rgba(200,16,46,.12); }
  .src { font-size:10.5px; color:var(--text3); margin-left:auto; }

  /* ---------- 右：详情 ---------- */
  #detail { flex:1; overflow-y:auto; padding-right:2px; }
  .card {
    border:1px solid var(--line); border-radius:16px; padding:18px 20px; margin-bottom:14px;
    background:linear-gradient(180deg,rgba(255,255,255,.05),rgba(255,255,255,.02));
    backdrop-filter:blur(10px);
    animation:fadeUp .28s ease both;
  }
  @keyframes fadeUp { from { opacity:0; transform:translateY(8px);} to { opacity:1; transform:none;} }
  .card h3 { font-size:13px; color:var(--text2); margin-bottom:12px; display:flex; align-items:center; gap:8px; letter-spacing:.5px; }
  .card h3::before { content:""; width:14px; height:2px; border-radius:2px; background:linear-gradient(90deg,var(--icbc-2),transparent); }

  .hero { display:flex; align-items:center; gap:20px; }
  .hero .name { font-size:22px; font-weight:800; letter-spacing:.3px; }
  .hero .sub { display:flex; align-items:center; gap:8px; margin-top:8px; flex-wrap:wrap; }
  .gauge { position:relative; width:104px; height:104px; flex-shrink:0; margin-left:auto; }
  .gauge svg { transform:rotate(-90deg); }
  .gauge .gv { position:absolute; inset:0; display:flex; flex-direction:column; align-items:center; justify-content:center; }
  .gauge .gv b { font-size:26px; font-weight:800; color:var(--gold); line-height:1; font-variant-numeric:tabular-nums; }
  .gauge .gv span { font-size:10px; color:var(--text3); margin-top:3px; }
  .life { display:flex; gap:8px; margin-top:14px; flex-wrap:wrap; }
  .pill {
    display:inline-flex; align-items:center; gap:6px; font-size:12px; padding:5px 13px; border-radius:20px;
    border:1px solid var(--line); color:var(--text3); background:rgba(255,255,255,.03);
  }
  .pill .pdot { width:7px; height:7px; border-radius:50%; background:var(--grey); }
  .pill.on { color:var(--text); border-color:var(--line-2); background:rgba(255,255,255,.06); }
  .pill.on.new .pdot { background:var(--blue); box-shadow:0 0 8px var(--blue); }
  .pill.on.verifying .pdot { background:var(--amber); box-shadow:0 0 8px var(--amber); }
  .pill.on.contacted .pdot { background:var(--green); box-shadow:0 0 8px var(--green); }
  .pill.on.invalid .pdot { background:var(--grey); }

  .trigger { font-size:13.5px; line-height:1.7; color:var(--text); }
  .trigger .rule { display:inline-flex; align-items:center; gap:6px; margin-top:10px; font-size:12px; color:#8FD9B8; background:rgba(52,211,153,.10); border:1px solid rgba(52,211,153,.3); padding:4px 12px; border-radius:12px; }

  .kv { display:flex; flex-wrap:wrap; gap:10px 26px; font-size:13px; color:var(--text2); }
  .kv b { color:var(--text); font-weight:600; }
  .evrow { margin-top:14px; display:flex; align-items:center; gap:12px; flex-wrap:wrap; }
  .evlink { color:#FFB4A8; text-decoration:none; border-bottom:1px dashed rgba(255,180,168,.5); font-size:13px; }
  .evlink:hover { color:#FFD9D2; }
  .evbtn {
    display:inline-flex; align-items:center; gap:6px; font-size:12.5px; font-weight:600; color:#1A1208;
    background:linear-gradient(135deg,#F5DEA0,#E8C15A); padding:8px 18px; border-radius:10px; text-decoration:none;
    box-shadow:0 6px 18px rgba(232,193,90,.25); transition:all .15s ease;
  }
  .evbtn:hover { transform:translateY(-1px); box-shadow:0 10px 26px rgba(232,193,90,.35); }
  .evbtn.alt { background:linear-gradient(135deg,var(--icbc-2),var(--icbc)); color:#fff; box-shadow:0 6px 18px rgba(200,16,46,.3); }
  .evnote { font-size:11px; color:var(--text3); }

  .two { display:grid; grid-template-columns:1fr 1fr; gap:14px; }
  .factlist { list-style:none; }
  .factlist li { position:relative; padding-left:24px; font-size:13px; line-height:1.9; color:var(--text2); }
  .factlist li::before { content:""; position:absolute; left:2px; top:9px; width:8px; height:8px; border-radius:50%; }
  .factlist.known li::before { background:var(--green); box-shadow:0 0 8px rgba(52,211,153,.6); }
  .factlist.unknown li::before { background:var(--amber); box-shadow:0 0 8px rgba(245,183,63,.55); }
  .factlist.unknown li { color:#CBB488; }

  .qlist { list-style:none; counter-reset:q; }
  .qlist li { counter-increment:q; display:flex; gap:12px; font-size:13px; line-height:1.8; color:var(--text2); padding:8px 0; border-bottom:1px dashed rgba(255,255,255,.07); }
  .qlist li:last-child { border-bottom:none; }
  .qlist li::before { content:counter(q); width:22px; height:22px; flex-shrink:0; border-radius:7px; background:rgba(200,16,46,.16); color:#FF8A7C; font-size:12px; font-weight:700; display:flex; align-items:center; justify-content:center; margin-top:3px; }

  .bar-row { display:flex; align-items:center; gap:10px; margin-bottom:11px; font-size:12px; }
  .bar-row .bk { width:96px; color:var(--text2); flex-shrink:0; }
  .bar { flex:1; height:8px; background:rgba(255,255,255,.07); border-radius:5px; overflow:hidden; }
  .bar i { display:block; height:100%; border-radius:5px; background:linear-gradient(90deg,var(--icbc),var(--icbc-2)); box-shadow:0 0 10px rgba(200,16,46,.4); transition:width .6s ease; }
  .bar-row .bv { width:40px; text-align:right; font-weight:700; color:var(--text); font-variant-numeric:tabular-nums; }

  .btns { display:flex; gap:12px; margin-top:4px; }
  .btn { border:none; border-radius:12px; padding:11px 24px; font-size:14px; font-weight:700; cursor:pointer; transition:all .15s ease; }
  .btn.claim { background:linear-gradient(135deg,var(--icbc-2),var(--icbc)); color:#fff; box-shadow:0 8px 24px rgba(200,16,46,.35); }
  .btn.claim:hover { transform:translateY(-2px); box-shadow:0 12px 30px rgba(200,16,46,.45); }
  .btn.invalid { background:transparent; border:1px solid var(--line-2); color:var(--text2); }
  .btn.invalid:hover { border-color:var(--grey); color:var(--text); }
  .foot { font-size:12px; color:var(--text3); margin-top:14px; }

  .empty { padding:60px; text-align:center; color:var(--text3); }
  #toast {
    position:fixed; left:50%; bottom:30px; transform:translateX(-50%) translateY(20px); opacity:0;
    background:linear-gradient(135deg,#1B2340,#131A30); border:1px solid var(--line-2); color:#fff;
    padding:11px 22px; border-radius:12px; font-size:13px; z-index:99; transition:all .25s ease;
    box-shadow:0 12px 40px rgba(0,0,0,.5);
  }
  #toast.show { opacity:1; transform:translateX(-50%) translateY(0); }
  footer { position:fixed; bottom:0; left:0; right:0; z-index:2; padding:8px 22px; font-size:11px; color:var(--text3); border-top:1px solid var(--line); background:rgba(10,15,30,.7); backdrop-filter:blur(8px); display:flex; gap:20px; }
  @media (max-width:1100px){ .stats{grid-template-columns:repeat(2,1fr);} .two{grid-template-columns:1fr;} #queue{width:360px;} }
</style>
</head>
<body>
<header>
  <div class="brand">
    <span class="icbc">ICBC</span>
    <div>
      <div class="t1">外汇与国际业务商机雷达</div>
      <div class="t2">FOREIGN EXCHANGE LEAD RADAR · 工行深圳分行</div>
    </div>
    <span class="divider"></span>
    <span class="chip"><span class="dot"></span>数据源：巨潮 · 新浪 · 东财</span>
  </div>
  <div class="meta">
    <span class="chip">地区 <b>广东</b></span>
    <span class="chip" id="hdrDate"></span>
    <span class="chip">用户 <b>张经理</b></span>
  </div>
</header>

<div class="stats">
  <div class="kpi r"><div class="ico">🧭</div><div><div class="num" id="kTotal">0</div><div class="lab">今日商机线索</div></div></div>
  <div class="kpi g"><div class="ico">🎯</div><div><div class="num" id="kAvg">0</div><div class="lab">平均商机分</div></div></div>
  <div class="kpi b"><div class="ico">⏳</div><div><div class="num" id="kVerifying">0</div><div class="lab">待核实</div></div></div>
  <div class="kpi n"><div class="ico">✅</div><div><div class="num" id="kClaimed">0</div><div class="lab">已认领</div></div></div>
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
function evLabel(it){
  return it.evidence_url ? "查看原文 ↗" : "搜索相关报道 ↗";
}
function renderList(activeId){
  const life = {new:"新发现", verifying:"待核实", contacted:"已联系", invalid:"无效"};
  document.getElementById("qlist").innerHTML = items.map(it=>`
    <div class="qitem ${it.opportunity_id===activeId?"active":""}" onclick="showDetail('${it.opportunity_id}')">
      <div class="row1">
        <span class="rank">${it.rank}</span>
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
  const C = 2*Math.PI*42;
  document.getElementById("detail").innerHTML = `
    <div class="card">
      <div class="hero">
        <div>
          <div class="name">${esc(it.company_name)} <span style="font-size:13px;color:var(--text3)">（${esc(it.city)}）</span></div>
          <div class="sub">${tagHtml(it.tags)}</div>
        </div>
        <div class="gauge">
          <svg width="104" height="104" viewBox="0 0 104 104">
            <circle cx="52" cy="52" r="42" fill="none" stroke="rgba(255,255,255,.08)" stroke-width="9"/>
            <circle cx="52" cy="52" r="42" fill="none" stroke="url(#gg)" stroke-width="9" stroke-linecap="round"
              stroke-dasharray="${C}" stroke-dashoffset="${C*(1-scorePct/100)}"/>
            <defs><linearGradient id="gg" x1="0" y1="0" x2="1" y2="1">
              <stop offset="0%" stop-color="#E8483A"/><stop offset="100%" stop-color="#E8C15A"/></linearGradient></defs>
          </svg>
          <div class="gv"><b>${it.score}</b><span>商机分</span></div>
        </div>
      </div>
      <div class="life">${lifeOrder.map(s=>`<span class="pill ${it.lifecycle===s?"on "+lifeKey[s]:""}"><span class="pdot"></span>${lifeMap[s]}</span>`).join("")}
        ${it.lifecycle==="invalid"?`<span class="pill on invalid"><span class="pdot"></span>无效</span>`:""}</div>
    </div>

    <div class="card"><h3>触发事件</h3>
      <div class="trigger">${esc(it.trigger_event)}
        <span class="rule">⚡ ${(it.rule_hits||[]).join(" + ")}</span></div>
    </div>

    <div class="card"><h3>证据摘要</h3>
      <div class="kv">
        <span><b>文档：</b>${evDocLink(it,evidence)}</span>
        <span><b>来源：</b>${esc(evidence.source||it.source||"")}</span>
        <span><b>时间：</b>${esc(evidence.publish_time||it.publish_date||"")}</span>
      </div>
      <div class="evrow">
        <a class="evbtn ${it.evidence_url?"":"alt"}" href="${evHref(it,evidence)}" target="_blank" rel="noopener">${evLabel(it)}</a>
        <span class="evnote">${it.evidence_url?"点击打开公告/快讯原文":"未收录直接原文，点击搜索相关报道"}</span>
      </div>
    </div>

    <div class="two">
      <div class="card"><h3>已知事实 <span style="color:var(--green);font-size:11px">AI 提取</span></h3>
        <ul class="factlist known">${(rev.known_facts||[]).map(f=>`<li>${esc(f)}</li>`).join("")||"<li>（暂无）</li>"}</ul></div>
      <div class="card"><h3>待核实</h3>
        <ul class="factlist unknown">${(rev.unknown_facts||[]).map(f=>`<li>${esc(f)}</li>`).join("")||"<li>（暂无）</li>"}</ul></div>
    </div>

    <div class="card"><h3>规则商机评分 ${rev.reviewed_score?`<span style="color:var(--gold);font-size:11px">大模型复核 ${rev.reviewed_score} 分</span>`:`<span style="color:var(--text3);font-size:11px">待大模型复核</span>`}</h3>
      ${scoreBars(it.score_breakdown)}
      <div style="font-size:12px;color:var(--text3);margin-top:8px">${esc(rev.review_note||"评分由规则引擎按 5 维加权计算")}</div>
    </div>

    <div class="card"><h3>建议客户沟通问题</h3>
      <ol class="qlist">${(rev.suggested_questions||[]).map(q=>`<li>${esc(q)}</li>`).join("")||"<li>（暂无）</li>"}</ol>
    </div>

    <div class="card"><div class="btns">
        <button class="btn claim" onclick="action('${it.opportunity_id}','claim')">认领商机 →</button>
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
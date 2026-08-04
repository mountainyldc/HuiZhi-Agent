# fx-lead-radar — 企业外汇需求商机雷达（Pi Agent 编排）

基于 Pi Coding Agent 的商机雷达：自动抓取巨潮公告 → 规则初筛（广东企业+外汇套保+45天）
→ 5 维评分 → DeepSeek 大模型复核 → 生成每日商机队列 → 渲染页面 → 认领/标记无效。

## 快速开始

```bash
# 1. 依赖（Python 3 + requests/openai/PyYAML）
pip install requests openai pyyaml

# 2. 配置环境变量（复核用，缺省自动跳过）
set DEEPSEEK_API_KEY=sk-xxx

# 3. 跑全流程（等价于让 Pi 依次调用 8 个工具）
python engines/crawl_cninfo.py          # ① 巨潮公告（失败回退样例）
python engines/sina_news.py --pages 10  # ② 新浪财经 7x24 快讯（舆情软信号）
python engines/eastmoney_news.py        # ③ 东方财富 7x24 快讯（舆情软信号）
python engines/rule_screen.py --reset   # ④ 规则初筛+5维评分（--reset 清空重建）
python engines/llm_review.py --all      # ⑤ DeepSeek 复核
python engines/build_queue.py           # ⑥ 生成今日队列（含 evidence_url 证据链接）
python engines/render_web.py            # ⑦ 渲染 web/index.html（证据摘要可点击）

# 4. 查看
# 方式A（推荐演示）：启动服务，认领/标记无效可持久化
python engines/serve.py                # 打开 http://127.0.0.1:8000
# 方式B：直接双击 web/index.html（静态模式，状态仅本次会话生效）
```

## Pi Agent 集成

```bash
# 加载扩展（注册 7 个工具 + /radar 命令）
pi -e ./extensions/fx-lead-radar.ts

# 在 Pi 中说一句话跑全流程：
#   "跑一遍企业外汇需求商机雷达"
# 或手动调用工具：
#   crawl_cninfo → rule_screen → review_opportunity(all=true)
#   → build_daily_queue → render_web
#   → claim_opportunity / mark_invalid
```

扩展安装到全局：复制 `extensions/fx-lead-radar.ts` 到 `~/.pi/agent/extensions/`。

## 目录结构

```
extensions/fx-lead-radar.ts   # Pi 扩展：7 个工具
skills/fx-lead-radar/SKILL.md # 业务知识 + 工具用法
skills/workflow/SKILL.md      # 全流程编排指令
engines/
  crawl_cninfo.py     # ① 巨潮公告抓取（关键词+45天，失败回退样例）
  sina_news.py        # ② 新浪财经 7x24 快讯 -> 舆情软信号（含 docurl 原文）
  eastmoney_news.py   # ③ 东方财富 7x24 快讯 -> 舆情软信号（含原文链接）
  rule_screen.py      # ④ 规则初筛 + 5维评分（多源：公告硬规则/舆情软规则）
  llm_review.py       # ⑤ DeepSeek 复核（证据摘要/已知未知/沟通问题/复核分）
  build_queue.py      # ⑥ 今日商机队列快照（含 evidence_url）
  render_web.py       # ⑦ 静态页面渲染（证据摘要可点击，无原文时搜索兜底）
  serve.py            # ⑧ 轻量演示服务（认领/标记无效持久化）
  actions.py          # 认领/推进/标记无效 CLI
  store.py            # SQLite 存储层（生命周期状态机）
  common.py           # 配置与路径
data/               # 抓取结果/快照/样例（db 不入库）
config.yaml         # 地区/关键词/窗口/评分权重/LLM 配置
```

## 边界说明（已知不稳，已降级处理）

- 巨潮接口偶发 504 → 自动重试 + 失败回退样例数据（source=sample）
- "我行覆盖度"无行内数据 → config 占位值 55，页面已标注
- DeepSeek key 缺失 → 复核自动跳过，评分用规则分
- Pi 为交互式 CLI，定时自动运行本期不做；演示以现场一句话跑通为主
- 广东企业识别依赖 `engines/region_allowlist.csv` 名单，需持续维护
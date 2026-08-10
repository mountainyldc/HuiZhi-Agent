# 企业外汇智能体（HuiZhi Agent）

> 基于 Pi Coding Agent 的企业外汇需求商机雷达 Agent
>
> [![CI](https://github.com/mountainyldc/HuiZhi-Agent/actions/workflows/ci.yml/badge.svg)](https://github.com/mountainyldc/HuiZhi-Agent/actions/workflows/ci.yml) · [MIT License](LICENSE)

面向商业银行金融市场部客户经理的外汇获客智能体：自动抓取公开数据 → 规则初筛 + 大模型复核 → 每日输出潜在外汇业务客户清单（判定依据 + 潜在业务 + 最新年报数据 + 建议沟通重点）。

## 功能

- **商机雷达全流程**：一句话（/radar）触发「抓取 → 规则初筛 → LLM 复核 → 队列 → 渲染」，接入 9 类数据源（巨潮资讯、新浪财经、东方财富 7x24、同花顺直播、港交所披露易、商务部机电产品国际招标、广东省投资项目在线审批监管平台等）
- **RAG 可溯源问答**：FTS5 BM25 + Embedding + FAISS + RRF 混合检索，回答带 [来源N] 可点击溯源，支持单公司深度分析
- **企业画像**：法人 / 注册地 / 年报外汇指标；营收 / 出口占比 / 外汇敞口方向等 6 字段画像
- **营销辅助**：拜访话术生成器、跨轮次会话记忆、按需实时 Web 搜索、意图路由
- **Web 看板**：商机队列、资讯中心、企业档案、规则过滤词设置，支持认领 / 标记无效

## 仓库结构

```
HuiZhi-Agent/   # 智能体本体：Pi 扩展 + skills + Python 引擎 + Web 看板
pi-web/              # Pi Web 桌面端（已定制品牌标识）
```

## 快速开始

```bash
git clone https://github.com/mountainyldc/HuiZhi-Agent.git
cd HuiZhi-Agent

# 商机雷达 Web（Python 3.10+，启动时自动播种数据）
pip install -r HuiZhi-Agent/requirements.txt
cd HuiZhi-Agent && python engines/serve.py   # 打开 http://127.0.0.1:8000

# Pi Web 桌面端（Node.js >= 22.19，配置 DeepSeek 后可直接对话 / 跑雷达）
cd ../pi-web && npm install && npm run build && npm start  # 打开 http://127.0.0.1:30141
```

详细使用说明见 [HuiZhi-Agent/README.md](HuiZhi-Agent/README.md)。

## 开发

- 测试：`cd HuiZhi-Agent && python -X utf8 -m pytest tests/ -q`（26 个用例）
- 变更记录：[CHANGELOG.md](CHANGELOG.md) · 贡献指南：[CONTRIBUTING.md](CONTRIBUTING.md)

## 免责声明

本项目为实习期技术原型，仅用于学习交流；数据抓取自公开渠道，输出不构成投资建议。

# Changelog

按日期倒序记录功能与修复，遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)。

## [Unreleased]
- 工程化：pytest 单元测试（26 个用例）+ GitHub Actions CI（py_compile + pytest）+ CHANGELOG / CONTRIBUTING / LICENSE + issue/PR 模板

## 2026-08-06
### 新增
- P0-1 跨轮次会话记忆：`memory.py` + memory_status / clear_memory 工具，追问可指代上一家公司
- P0-2 企业画像增强：`build_insights.py` 生成营收/出口占比/境外子公司/敞口方向/历史套保/建议产品 6 字段画像，字段带来源与披露日期，未披露标「未披露」
- P0-3 按需实时 Web 搜索：`web_search` 工具（Exa → so.com → 手工搜索降级链），结果带来源链接并标注「网络信息，需人工核验」
- P0-4 拜访话术生成器：`visit_pitch.py` 输出开场白/拜访提纲/产品建议/异议应对，事实可追溯
- P1-2 意图路由 · 动态规划：`dispatch.py` 规则路由，把问法分发到对应工具链
- 看板「设置 · 规则过滤词」：生效关键词/排除词/时间窗口持久化到 `data/settings.json`，一键恢复默认
- Claude Code Agent 底层循环原理图（面试/PPT 素材）

### 修复
- session 提示工具数 18 -> 17
- RAG 回答无 [来源N] 标记时兜底追加可点击来源列表

## 2026-08-05
### 新增
- 品牌更名：fx-lead-radar → HuiZhi-Agent（工银汇智 · 企业外汇智能体）
- 看板与 pi-web 浅色主题（Claude 米白暖色系）、主界面版本号 HUIZHI 1.0
- RAG 全链路：FTS5 BM25 + 百炼 text-embedding-v4 + FAISS + RRF 混合检索
- 公告正文摄入 `ingest_docs.py` 与企业档案 `build_profiles.py`（19 家公司，法人/注册地/年报指标）
- 证据级问答：回答带 [来源N] 角标，可点击打开巨潮原文 PDF
- 资讯中心多数据源：东财 7x24 / 同花顺直播 / 新浪财经 / 港交所披露易 / 商务部机电产品国际招标 / 广东省投资项目在线审批监管平台等
- 最新年报数据：`fetch_financials.py` 提取汇兑损益等外汇指标
- pi-web 桌面端整合进仓库（clone 即用，含品牌标识定制）
- 文档：实习汇报报告（09）、功能详细解释（10）、会议纪要（11）、RAG 技术选型（08）

### 修复
- serve.py 编码乱码
- pi-web 服务端静态扫描与 Windows junction 导致的 next build 失败

## 2026-08-04
### 新增
- 脚手架：目录结构、config.yaml、SQLite 存储层、样例数据、广东企业名单（950 家）
- 抓取引擎：巨潮公告（关键词 + 日期窗口，失败回退样例）
- 规则初筛 + 5 维评分引擎（广东企业/套保/时间窗口）
- DeepSeek 大模型复核引擎（证据摘要 / 已知未知事实 / 复核分）
- 队列 + Web 渲染 + 演示服务（静态页面，认领/标记无效持久化）
- Pi 扩展 + skills：7 个工具 + 全流程编排 skill
- 多源数据 + 证据可点击：新浪 / 东方财富舆情源、队列 evidence_url
- 商机加量：白名单 950 家、时间窗口 45→180 天、关键词 12 个、队列 115 条
- start_server 工具：渲染后自动启动服务并返回可点击网址
- 页面简洁商务风（白底 + 工行红 + 品牌标识）、苹果风配色

### 修复
- Pi v0.83 崩溃：工具返回值改为 {content:[{type:text}]} 结构
- /radar 在 pi-web 空白：命令 handler 注入真实用户消息驱动全流程

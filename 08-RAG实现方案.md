# 08-RAG 实现方案（方案 1：证据级问答）

> 架构师视角的实现方案。目标：把「工银汇智 · 企业外汇智能体」从"标题级线索"升级为"证据级分析"，
> 在 pi-web 里实现对任意公司的深度问答（带引用来源）。按 P0→P1→P2 分期交付，先稳后炫。

## 1. 现状缺口（为什么要做 RAG）
- 商机只有「标题 + 链接 + 摘要」，判断依据点进原文才能看
- DeepSeek 复核是单轮打分：没有检索、没有引用原文，无法回答"为什么东鹏排第一"
- 导师提的"年报外汇收入可作业务规模依据"已有数据，但没有被检索利用

## 2. 目标能力（做什么）
- 用户在 pi-web 问：`帮我分析比亚迪的外汇需求`
- 系统：识别主体 → 从公告 / 新闻 / 年报中混合检索证据 → DeepSeek 生成带引用的深度分析
- 输出：结论 + 证据列表（每条可追溯到原文链接），并在看板商机详情里附证据片段

## 3. 总体架构（六层）

```
应用层   pi-web 对话（ask_insights / analyze_company 工具）
生成层   DeepSeek：证据拼接 -> 带引用回答
检索层   BM25 关键词 + 向量语义 混合检索 -> RRF 融合 -> 重排序
索引层   FAISS 向量库 + SQLite 元数据（公司/日期/来源/标题/链接）
解析层   PDF/正文抓取 + 分块（按公告/章节切，保留结构元数据）
数据层   data/crawled（公告/舆情）+ data/financials（年报）+ 新增 data/rag
```

## 4. 模块与改动点

| 模块 | 文件 | 职责 | 改动方式 |
| --- | --- | --- | --- |
| 正文抓取 | 新增 `engines/ingest_docs.py` | 巨潮公告 PDF→文本；新闻/年报正文入库 | 新增，复用 crawl_cninfo 的公告清单 |
| 分块 | 同上 | 按"公告/章节"切块，保留 公司+日期+来源+标题 元数据；表格跨页先合并再切 | 新增 |
| 索引 | 新增 `engines/index_docs.py` | Embedding 生成向量，写入 FAISS + SQLite | 新增 |
| 检索 | 新增 `engines/retrieve.py` | BM25（SQLite FTS5）+ 向量 Top-K，RRF 融合 | 新增，复用 store.py 的 SQLite |
| 生成 | 新增 `engines/rag_answer.py` | 证据拼 Prompt → DeepSeek → 带 [来源] 角标的回答 | 新增，复用 llm_review 的客户端 |
| 工具接入 | 改 `extensions/ICBC-HuiZhi-Agent.ts` | 注册 `analyze_company` / `ask_insights` | 扩展 |
| 看板 | 改 `web_template.html` | 商机详情展示预取证据片段 | 扩展 |

## 5. 技术选型（定稿，2026-08-05 实测验证）

| 层 | 选型 | 关键参数 | 验证状态 |
| --- | --- | --- | --- |
| Embedding | 阿里云百炼 `text-embedding-v4`（兼容模式 `/v1/embeddings`） | 1024 维 | ✅ 已用现有 DASHSCOPE_API_KEY 实测通过 |
| 向量库 | `faiss-cpu`，IndexFlatIP（归一化内积） | 千级块规模足够，无需 Milvus | ⏳ 待安装（唯一新增重量依赖） |
| 关键词 BM25 | SQLite FTS5（Python 内置，零依赖） | `CREATE VIRTUAL TABLE ... USING fts5` | ✅ 已实测通过 |
| 混合融合 | RRF 融合，k=60：BM25 Top10 ∪ 向量 Top10 → Top5 | 兼顾精确关键词与语义泛化 | 实现阶段验证 |
| 分块 | 按公告/新闻/年报自然段落切块 | 每块 ≤800 token（约 1200 汉字），保留 company/date/source/title/url/type 元数据 | 实现阶段验证 |
| 生成 | DeepSeek `deepseek-chat` | 证据拼接 + [来源] 角标 | ✅ DEEPSEEK_API_KEY 已在环境变量 |
| 重排序（P2） | DeepSeek 对 Top10 相关性打分取 Top5 | 不引第三方重排模型 | 预留 |

**Key 读取优先级**：`EMBEDDING_API_KEY` → `DASHSCOPE_API_KEY`（vision skill `.env` 已有）→ 无 key 自动降级为仅 BM25 关键词检索，流程不中断。

**成本**：embedding 调用量 ≈ 文档块数（几百~几千块）；text-embedding-v4 单价约 0.5 元/百万 token，整轮索引 < 0.1 元，可忽略。

**新增依赖**：仅 `faiss-cpu`（pip 安装，约 70MB）。其余复用现有环境（openai / pypdf / numpy / SQLite FTS5）。

**备选（不选的原因）**：
- ChromaDB / Milvus：千级块规模用不上，服务与依赖更重
- 智谱 embedding-2：需额外申请 key；百炼 key 已有且已实测
- sentence-transformers / bge-m3 本地模型：需下载模型 + torch，体积大，离线收益不明显
## 6. 主链路时序

```
用户提问 -> 意图识别(公司名/时间/主题) -> 查 SQLite 商机库/财务缓存
  -> retrieve.py: 混合检索 Top10 证据块
  -> rag_answer.py: 证据块 + 指令 拼 Prompt -> DeepSeek 生成
  -> 回答含 [来源N] 角标，下方列出证据卡(原文标题+链接+日期)
  -> pi-web 渲染；同时写入看板商机详情的"证据片段"
```

## 7. 分期交付（里程碑）

| 阶段 | 内容 | 产出 / 验收 |
| --- | --- | --- |
| P0 | 公告正文抓取落库（巨潮 PDF→文本，覆盖队列 Top20 公司） | 队列 Top20 公司正文可检索率 ≥80% |
| P1 | FAISS 索引 + BM25 混合检索 + CLI 查询 | `python engines/retrieve.py --company 比亚迪` 返回 Top5 证据 |
| P2 | rag_answer 带引用回答 + pi-web 工具接入 | pi-web 中问"分析比亚迪外汇需求"得到带引用回答 |
| P3（可选） | 看板商机详情预置证据片段；队列证据增强 | 每条商机详情页直接显示证据片段 |

## 8. 可量化指标（汇报用，报实测不报虚数）
- 证据覆盖率：队列 Top20 公司中正文已入库可检索的比例
- 引用可溯源率：回答中带 [来源] 的条目都能点回原文链接
- 检索命中率：人工抽检 Top-5 相关度（每家公司抽 10 问）

## 9. 风险与对策
- 巨潮 PDF 为扫描件 → 解析不到文本：只对可解析文本建索引，扫描件在页面标注"建议人工查看原文"
- 需要额外 Embedding Key → 配置化 + 缺省降级为关键词检索，不影响现有流程
- 检索质量不稳定 → 混合检索 + 元数据过滤兜底；P2 增加重排序
- 边界：只检索公开数据，不碰行内系统/台账，汇报口径与背景文档一致
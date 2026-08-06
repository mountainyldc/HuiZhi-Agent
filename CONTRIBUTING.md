# Contributing

感谢你关注「工银汇智 · 企业外汇智能体」。本仓库由实习项目演化而来，欢迎提 issue / PR。

## 环境搭建

```bash
# Python 3.10+
pip install -r HuiZhi-Agent/requirements.txt

# 可选环境变量（缺失时自动降级，不影响核心流程）
set DEEPSEEK_API_KEY=sk-xxx     # LLM 复核 / RAG 问答
set DASHSCOPE_API_KEY=sk-xxx    # 百炼 Embedding，缺失仅走 BM25

# pi-web 桌面端（可选）
cd pi-web && npm install
```

## 跑测试

```bash
cd HuiZhi-Agent
python -X utf8 -m pytest tests/ -q
```

- 26 个用例覆盖：`settings`（关键词/排除词/时间窗口读写与回退）、`rule_screen`（硬规则/排除词/days_window）、`dispatch`（意图路由）、`retrieve`（FTS5 + RRF 融合）、`store`（画像/记忆 upsert/get）
- 测试使用临时目录隔离数据，不触碰真实 `data/`；CI 每次 push / PR 自动运行

## 代码规范

- 业务逻辑放 `HuiZhi-Agent/engines/` 的 Python 引擎，Pi 扩展只做桥接（安全边界）
- 配置走 `config.yaml`，运行期可调参数走 `settings.py`（持久化 `data/settings.json`）
- 新增引擎或工具时同步更新 README、CHANGELOG 与对应文档

## 提交规范

- 提交信息格式：`type(scope): 中文说明（写"为什么"而非"改了什么"）`
- type：feat / fix / docs / style / refactor / test / chore
- 例：`feat(rag): 回答追加可点击来源列表，方便客户经理一键溯源核验`

## 提 PR

- 模板见 `.github/PULL_REQUEST_TEMPLATE.md`：说明背景 / 改动 / 测试结果
- CI 必须通过（py_compile + pytest）

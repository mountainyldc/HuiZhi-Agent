---
name: fx-radar-workflow
description: 商机雷达全流程编排 - 用户说"跑一遍商机雷达"时，按此步骤依次调用工具
---

# 商机雷达全流程（一句话触发）

当用户要求"跑一遍企业外汇需求商机雷达 / 生成今日商机队列 / 看看今天有什么商机"时，
严格按以下顺序执行：

## 步骤

1. `crawl_cninfo` — 抓取巨潮公告（近45天，外汇/套保关键词）
   - 若返回 source=sample，向用户说明：当前为样例数据兜底（离线/接口异常）
2. `rule_screen` — 规则初筛（广东企业+外汇与套保+近45天）+ 5 维评分
   - 若命中 0 条，向用户说明原因并停止
3. `review_opportunity` with `all=true` — 大模型复核全部未复核商机
   - 若输出跳过（无 Key/失败），说明评分仍为规则分
4. `build_daily_queue` — 生成今日商机队列
5. `render_web` — 渲染页面

## 汇报格式

向用户汇报：
- 今日商机 N 条（附公司/城市/分数/标签列表）
- 数据来源：真实抓取 or 样例
- 复核状态：已完成 N 条 / 跳过（规则分）
- 查看方式：`python engines/serve.py` 后打开 http://127.0.0.1:8000，或直接打开 web/index.html

## 后续操作（用户要求时）

- "认领 X 商机" → `claim_opportunity`（状态→待核实）→ 重新 `build_daily_queue` + `render_web`
- "标记 X 无效" → `mark_invalid` → 重新 `build_daily_queue` + `render_web`
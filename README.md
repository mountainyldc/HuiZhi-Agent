# 企业外汇需求商机雷达 Agent（基于 Pi Coding Agent）

> 项目统一目录：`E:\2026工行实习\基于picoding-agent的企业外汇需求商机雷达agent实现`
> GitHub：https://github.com/mountainyldc/fx-lead-radar （clone 即用）
> 更新日期：2026-08-05

## 项目定位
帮金融市场部客户经理自动发现"潜在有结售汇需求的公司"：自动抓取公开数据 → 关键字 + 大模型语义过滤
→ 每日输出潜在客户清单（判定依据 + 潜在业务 + 最新年报数据 + 建议沟通重点）。**不是量化交易**（见 00-背景.md）。

## 核心文档（后续只维护这两份）
```
00-背景.md        # 唯一背景文档：定位/为什么不是量化/交易员现状/痛点/名词
01-数据源清单.md  # 唯一数据源文档：识别逻辑/四类数据源/MVP/待确认问题
```

## 规划文档
```
02-问题定义.md    # 交付物/硬约束/隐含要求/完成标准/风险点（✅）
03-可行方案.md    # 方案A/B/C 对比，选定方案B（Pi Agent 编排）（✅）
04-系统骨架.md    # 模块/目录/接口/数据结构/时序/边界（✅）
05-演示视频录制流程.md  # 录屏完整流程（✅）
06-自由提问与分析拓展计划.md  # 形态A + 4 个新工具设计（计划未实施）
```

## 代码（✅ 已实现，单仓库 clone 即用）
```
fx-lead-radar/    # 商机雷达本体：Pi 扩展 + skills + 9 个引擎 + 苹果风 Web 页面
  README.md       # 使用说明（快速开始 / 接口一览 / 边界）
pi-web/           # Pi Web 桌面端（已定制 ICBC 标识），clone 后 npm install 即可用
```

## 一条命令体验（clone 即用）

```bash
git clone https://github.com/mountainyldc/fx-lead-radar.git
cd fx-lead-radar

# 商机雷达 Web（Python 3.10+，自动播种数据）
pip install -r fx-lead-radar/requirements.txt
cd fx-lead-radar && python engines/serve.py     # 打开 http://127.0.0.1:8000

# Pi Web 桌面端（Node.js >= 22.19，配置 DeepSeek 后可直接对话/跑雷达）
cd ../pi-web
npm install && npm run build && npm start       # 打开 http://127.0.0.1:30141
```

## 2026-08-05 更新
- 页面改为苹果风配色（浅灰 `#F5F5F7` + 白色圆角卡片 + 蓝/绿/紫/橙点缀，红色仅 ICBC 徽标）
- 新增**资讯中心**：公告+舆情聚合检索（搜索/来源筛选/时间窗口/分页/一键更新）
- 新增**03 最新年报数据**：从巨潮年报 PDF 提取汇兑损益等外汇指标（`fetch_financials.py`）
- 新增**潜在业务判断**卡片：汇率避险 / 对外付款 / 对外收款 / 跨境结算（`infer_biz`）
- serve.py 启动时自动播种数据（clone 即用），新增 `/news`、`/financials` 接口
- pi-web 桌面端已定制 ICBC 标识并推送：https://github.com/agegr/pi-web

## 参考素材（docs/，行内内部资料不入库）
- `金融市场部AI赋能需求分析.md`、`交易员访谈_痛点与场景.md`、`7-29金融市场部谈话.docx`

## 待办
- [ ] 与导师确认 7 个问题（见 01-数据源清单.md）
- [ ] 巨潮接口稳定性观察（已加重试+样例兜底）
- [ ] 广东企业名单持续维护（engines/region_allowlist.csv）
- [ ] 资讯中心数据源扩展到 14 个（当前 3 类：巨潮/新浪/东财）

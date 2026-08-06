/**
 * 工银汇智 · 企业外汇智能体 - Pi Coding Agent 扩展
 *
 * 为"工银汇智 · 企业外汇智能体"注册工具，覆盖完整链路:
 *   多源抓取(公告+舆情) -> 规则初筛评分 -> 大模型复核 -> 生成队列 -> 渲染页面 -> 认领/标记无效
 *
 * 安装方式:
 *   1. 复制到 ~/.pi/agent/extensions/ICBC-HuiZhi-Agent.ts
 *   2. 或: pi -e ./extensions/ICBC-HuiZhi-Agent.ts
 *
 * 依赖: Python 3 (需 requests / openai / PyYAML)
 */

import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { Type } from "typebox";
import { execFileSync, spawn } from "child_process";
import { get as httpGet } from "http";
import { existsSync } from "fs";
import { homedir } from "os";
import { join } from "path";

function resolveEnginesDir(): string {
  const candidates = [
    join(__dirname, "..", "engines"),
    join(homedir(), ".pi", "agent", "engines"),
    process.env.FX_RADAR_HOME ? join(process.env.FX_RADAR_HOME, "engines") : "",
  ].filter(Boolean);
  for (const c of candidates) {
    if (existsSync(c)) return c;
  }
  return candidates[0];
}

const ENGINES_DIR = resolveEnginesDir();

// 优先使用会话项目目录下的引擎，保证数据落在项目里（与 CLI 一致）；否则回退全局引擎目录
function resolveEnginesForCwd(cwd: string | undefined): string {
  if (cwd) {
    const candidates = [
      join(cwd, "ICBC-HuiZhi-Agent", "engines"),
      join(cwd, "engines"),
    ];
    for (const c of candidates) {
      if (existsSync(c)) return c;
    }
  }
  return ENGINES_DIR;
}

function runPython(script: string, args: string[], enginesDir: string = ENGINES_DIR): { content: { type: "text"; text: string }[]; isError: boolean } {
  try {
    const out = execFileSync(
      "python",
      [join(enginesDir, script), ...args],
      { encoding: "utf-8", timeout: 180000 }
    );
    return { content: [{ type: "text", text: out.trim() }], isError: false };
  } catch (e: any) {
    const stderr = e.stderr ? `\n${e.stderr.toString()}` : "";
    const stdout = e.stdout ? `\n${e.stdout.toString()}` : "";
    return { content: [{ type: "text", text: `执行失败: ${e.message}${stdout}${stderr}` }], isError: true };
  }
}

const crawlTool = {
  name: "crawl_cninfo",
  label: "抓取巨潮公告",
  description:
    "从巨潮资讯抓取外汇相关公告（按关键词+日期窗口），写入 data/crawled/。" +
    "抓取失败或为空时自动回退样例数据。返回公告数量与数据来源。",
  promptSnippet: "抓取巨潮资讯外汇/套保相关公告",
  promptGuidelines: [
    "商机雷达流程第一步调用本工具",
    "默认抓取近45天、config 中配置的关键词",
    "返回结果中 source=cninfo 表示真实数据，source=sample 表示样例兜底",
  ],
  parameters: Type.Object({
    days: Type.Optional(Type.Integer({ description: "日期窗口天数，默认45" })),
    force_sample: Type.Optional(Type.Boolean({ description: "强制使用样例数据" })),
  }),
  async execute(_toolCallId: string, params: any, _signal?: any, _onUpdate?: any, ctx?: any) {
    const args: string[] = [];
    if (params.days) args.push("--days", String(params.days));
    if (params.force_sample) args.push("--force-sample");
    return runPython("crawl_cninfo.py", args, resolveEnginesForCwd(ctx?.cwd));
  },
};

const crawlNewsTool = {
  name: "crawl_news",
  label: "抓取财经快讯舆情",
  description:
    "抓取财经媒体 7x24 快讯（新浪财经 / 东方财富）生成舆情软信号，写入 data/crawled/。" +
    "实时命中「广东企业 + 外汇/汇率/出口/海外」关键词即产出；无命中时回退样例（source 标注样例）。",
  promptSnippet: "抓取财经快讯生成舆情软信号",
  promptGuidelines: [
    "在 crawl_cninfo 之后调用，为商机增加舆情软信号（可提升队列数量）",
    "source=sina 为新浪财经，source=eastmoney 为东方财富，默认全部",
  ],
  parameters: Type.Object({
    source: Type.Optional(Type.String({ description: "sina / eastmoney / all（默认 all）" })),
    pages: Type.Optional(Type.Integer({ description: "抓取页数，默认新浪10页/东财5页" })),
  }),
  async execute(_toolCallId: string, params: any, _signal?: any, _onUpdate?: any, ctx?: any) {
    const source = params.source || "all";
    const pagesArgs = params.pages ? ["--pages", String(params.pages)] : [];
    const ed = resolveEnginesForCwd(ctx?.cwd);
    const results: { content: { type: "text"; text: string }[]; isError: boolean }[] = [];
    if (source === "sina" || source === "all") results.push(runPython("sina_news.py", pagesArgs, ed));
    if (source === "eastmoney" || source === "all") results.push(runPython("eastmoney_news.py", pagesArgs, ed));
    return {
      content: results.flatMap((r) => r.content),
      isError: results.some((r) => r.isError),
    };
  },
};

const ruleScreenTool = {
  name: "rule_screen",
  label: "规则初筛与评分",
  description:
    "对已抓取公告执行规则初筛（广东企业+外汇与套保+近45天）并计算5维商机分，写入 SQLite。" +
    "返回命中商机列表（公司/城市/分数/标签）。",
  promptSnippet: "规则初筛并生成商机评分",
  promptGuidelines: [
    "在 crawl_cninfo 之后调用",
    "评分5维：事件可信度/资金体量/时效性/我行覆盖度/信息完整度",
    "非广东企业或非套保相关公告会被过滤掉",
  ],
  parameters: Type.Object({
    region: Type.Optional(Type.String({ description: "地区，默认广东" })),
  }),
  async execute(_toolCallId: string, params: any, _signal?: any, _onUpdate?: any, ctx?: any) {
    const args: string[] = [];
    if (params.region) args.push("--region", params.region);
    return runPython("rule_screen.py", args, resolveEnginesForCwd(ctx?.cwd));
  },
};

const reviewTool = {
  name: "review_opportunity",
  label: "大模型复核商机",
  description:
    "调用大模型（DeepSeek）对商机进行复核：生成证据摘要、已知/未知事实、建议沟通问题、复核分。" +
    "无 API Key 或调用失败时自动跳过，不影响主流程。",
  promptSnippet: "大模型复核商机线索",
  promptGuidelines: [
    "在 rule_screen 之后调用",
    "指定商机用 --id；复核全部未复核商机用 --all",
    "输出会保存到复核记录中",
  ],
  parameters: Type.Object({
    opportunity_id: Type.Optional(Type.String({ description: "商机ID" })),
    all: Type.Optional(Type.Boolean({ description: "复核全部未复核商机" })),
  }),
  async execute(_toolCallId: string, params: any, _signal?: any, _onUpdate?: any, ctx?: any) {
    const ed = resolveEnginesForCwd(ctx?.cwd);
    if (params.all) return runPython("llm_review.py", ["--all"], ed);
    if (params.opportunity_id) return runPython("llm_review.py", ["--id", params.opportunity_id], ed);
    return "请提供 opportunity_id 或 all=true";
  },
};

const buildQueueTool = {
  name: "build_daily_queue",
  label: "生成今日商机队列",
  description:
    "从 SQLite 生成今日商机队列快照（按分数排序，含详情与复核），写入 data/queue_snapshots/。",
  promptSnippet: "生成今日商机队列",
  promptGuidelines: ["在复核之后调用，生成最终队列快照"],
  parameters: Type.Object({}),
  async execute(_toolCallId?: string, _params?: any, _signal?: any, _onUpdate?: any, ctx?: any) {
    return runPython("build_queue.py", [], resolveEnginesForCwd(ctx?.cwd));
  },
};

const renderTool = {
  name: "render_web",
  label: "渲染商机雷达页面",
  description:
    "由最新队列快照渲染自包含的静态 HTML 页面 web/index.html，可直接双击打开或通过 serve.py 访问。",
  promptSnippet: "渲染商机雷达网页",
  promptGuidelines: ["在 build_daily_queue 之后调用"],
  parameters: Type.Object({}),
  async execute(_toolCallId?: string, _params?: any, _signal?: any, _onUpdate?: any, ctx?: any) {
    return runPython("render_web.py", [], resolveEnginesForCwd(ctx?.cwd));
  },
};

const startServerTool = {
  name: "start_server",
  label: "启动本地预览服务",
  description:
    "启动商机雷达本地 HTTP 预览服务（serve.py），返回可直接点击的访问地址。" +
    "自动跳过被占用端口；若已有新版页面服务在运行则直接返回现有地址。",
  promptSnippet: "启动本地预览服务",
  promptGuidelines: ["在 render_web 之后调用，把可点击的网址交给用户"],
  parameters: Type.Object({}),
  async execute(_toolCallId?: string, _params?: any, _signal?: any, _onUpdate?: any, ctx?: any) {
    const ed = resolveEnginesForCwd(ctx?.cwd);
    const probe = (port: number, timeoutMs: number): Promise<{ alive: boolean; text: string }> =>
      new Promise((resolve) => {
        const req = httpGet({ host: "127.0.0.1", port, path: "/", timeout: timeoutMs }, (res) => {
          let body = "";
          res.setEncoding("utf8");
          res.on("data", (c) => { body += c; });
          res.on("end", () => resolve({ alive: res.statusCode === 200, text: body }));
        });
        req.on("timeout", () => { req.destroy(); resolve({ alive: false, text: "" }); });
        req.on("error", () => resolve({ alive: false, text: "" }));
      });
    const isCurrentPage = async (base: string) => {
      const port = Number(new URL(base).port) || 80;
      const r = await probe(port, 1500);
      return r.alive && (r.text.includes("ICBC") || r.text.includes("中国工商银行"));
    };
    const isFree = async (port: number) => !(await probe(port, 800)).alive;
    // 1) 已有新版页面服务在跑，直接复用
    for (let off = 0; off <= 9; off++) {
      const base = `http://127.0.0.1:${8000 + off}`;
      if (await isCurrentPage(base)) {
        return { content: [{ type: "text", text: `预览服务已在运行：${base}\n浏览器打开即可查看并保存商机雷达页面。` }], isError: false };
      }
    }
    // 2) 依次找空闲端口并后台启动
    for (let off = 0; off <= 9; off++) {
      const port = 8000 + off;
      if (!(await isFree(port))) continue;
      const child = spawn("python", [join(ed, "serve.py"), "--port", String(port)], {
        cwd: ed,
        detached: true,
        stdio: "ignore",
        windowsHide: true,
      });
      child.unref();
      const base = `http://127.0.0.1:${port}`;
      for (let i = 0; i < 25; i++) {
        await new Promise((r) => setTimeout(r, 400));
        if (await isCurrentPage(base)) {
          return { content: [{ type: "text", text: `预览服务已启动：${base}\n浏览器打开即可查看并保存商机雷达页面。` }], isError: false };
        }
      }
      return { content: [{ type: "text", text: `服务启动中，请稍后访问 ${base}（若仍打不开：cd ICBC-HuiZhi-Agent && python engines/serve.py）` }], isError: true };
    }
    return { content: [{ type: "text", text: "8000-8009 端口均不可用，请手动运行 python engines/serve.py 后访问" }], isError: true };
  },
};


function runRagAnswer(args: string[], ed: string) {
  const out = runPython("rag_answer.py", args, ed);
  if (out.isError) return out;
  try {
    const parsed = JSON.parse(out.content[0].text);
    const evLines = (parsed.evidence || [])
      .map((e: any, i: number) => `[来源${i + 1}](${e.url}) ${e.company} | ${e.publish_date} | ${e.title}`)
      .join("\n");
    const head = parsed.company ? `公司：${parsed.company}\n\n` : "";
    const hasSources = (parsed.answer || "").includes("数据来源（点击打开原文）");
    const tail = hasSources ? "" : `\n\n参考证据：\n${evLines}`;
    return { content: [{ type: "text", text: `${head}${parsed.answer}${tail}` }], isError: false };
  } catch {
    return { content: [{ type: "text", text: out.content[0].text }], isError: false };
  }
}

const analyzeCompanyTool = {
  name: "analyze_company",
  label: "单公司深度分析",
  description:
    "对指定上市公司做外汇需求深度分析：从公告/年报语料中混合检索证据（FTS5 BM25 + 向量），" +
    "再交给 DeepSeek 生成带 [来源N] 引用角标的分析报告（外汇风险敞口、套保现状、合作机会、拜访建议）。" +
    "适用问题：'帮我分析东鹏饮料的外汇需求' '比亚迪的外汇风险敞口如何'。",
  promptSnippet: "分析某家公司的外汇需求与业务机会",
  promptGuidelines: [
    "参数 company 必填（公司全名或简称）",
    "question 可选，默认'分析该公司外汇需求与潜在业务机会'",
    "回答自带 [来源N] 引用，可追溯原文链接",
  ],
  parameters: Type.Object({
    company: Type.String({ description: "公司名称，如：东鹏饮料、比亚迪" }),
    question: Type.Optional(Type.String({ description: "具体问题，默认分析外汇需求与业务机会" })),
    top: Type.Optional(Type.Integer({ description: "检索证据条数，默认5" })),
  }),
  async execute(_toolCallId: string, params: any, _signal?: any, _onUpdate?: any, ctx?: any) {
    const ed = resolveEnginesForCwd(ctx?.cwd);
    const q = params.question || `分析${params.company}的外汇需求与潜在业务机会`;
    const args = ["--company", params.company, "--query", q, "--json", "--remember", "--with-memory"];
    if (params.top) args.push("--top", String(params.top));
    return runRagAnswer(args, ed);
  },
};

const askInsightsTool = {
  name: "ask_insights",
  label: "证据级智能问答",
  description:
    "对商机语料（公告/年报）做自由提问：自动识别公司、混合检索证据、DeepSeek 生成带引用的回答。" +
    "适用问题：'为什么东鹏饮料排在商机第一' '这批企业集中反映了什么趋势' '哪些公司近期公告了套期保值业务'。",
  promptSnippet: "基于公告/年报语料自由提问分析",
  promptGuidelines: [
    "问题中带公司名时自动限定该公司",
    "回答带 [来源N] 引用与原文链接",
    "适合'为什么/趋势/有哪些'类分析问题",
  ],
  parameters: Type.Object({
    question: Type.String({ description: "要分析的问题" }),
    top: Type.Optional(Type.Integer({ description: "检索证据条数，默认5" })),
  }),
  async execute(_toolCallId: string, params: any, _signal?: any, _onUpdate?: any, ctx?: any) {
    const ed = resolveEnginesForCwd(ctx?.cwd);
    const args = ["--query", params.question, "--json", "--remember", "--with-memory"];
    if (params.top) args.push("--top", String(params.top));
    return runRagAnswer(args, ed);
  },
};

const companyInsightTool = {
  name: "company_insight",
  label: "查询企业画像卡",
  description:
    "查询某上市公司的「拜访前必看画像卡」：营收规模、出口占比、境外子公司、外汇敞口方向、历史套保记录、建议切入产品、置信度。" +
    "画像由 build_insights.py 基于公告+年报+舆情生成，字段均带来源与披露日期，未披露标「未披露」。",
  promptSnippet: "查询某公司的企业画像卡",
  promptGuidelines: [
    "company 必填（公司全名，如 东鹏饮料）",
    "若返回 exists=false，说明画像尚未生成，提示用户可运行 build_insights.py 生成",
  ],
  parameters: Type.Object({
    company: Type.String({ description: "公司名称，如：东鹏饮料" }),
  }),
  async execute(_toolCallId: string, params: any, _signal?: any, _onUpdate?: any, ctx?: any) {
    return runPython("build_insights.py", ["--company", params.company, "--show"], resolveEnginesForCwd(ctx?.cwd));
  },
};

const memoryStatusTool = {
  name: "memory_status",
  label: "查看会话记忆",
  description: "查看当前跨轮次会话记忆：最近分析过的公司、关注区域。记忆仅存公司/区域名，不含个人信息。",
  promptSnippet: "查看跨轮次会话记忆",
  promptGuidelines: ["记忆用于连续追问时理解指代（如「那它的子公司呢」）"],
  parameters: Type.Object({}),
  async execute(_toolCallId?: string, _params?: any, _signal?: any, _onUpdate?: any, ctx?: any) {
    return runPython("memory.py", [], resolveEnginesForCwd(ctx?.cwd));
  },
};

const clearMemoryTool = {
  name: "clear_memory",
  label: "清除会话记忆",
  description: "清除跨轮次会话记忆（最近分析的公司、关注区域），用户要求重置上下文时使用。",
  promptSnippet: "清除会话记忆",
  promptGuidelines: ["清除后追问指代将不再回退到旧公司"],
  parameters: Type.Object({}),
  async execute(_toolCallId?: string, _params?: any, _signal?: any, _onUpdate?: any, ctx?: any) {
    return runPython("memory.py", ["--clear"], resolveEnginesForCwd(ctx?.cwd));
  },
};

const claimTool = {
  name: "claim_opportunity",
  label: "认领商机",
  description: "认领指定商机：生命周期 新发现 -> 待核实，并记录负责人。",
  promptSnippet: "认领商机线索",
  promptGuidelines: ["认领后商机进入待核实阶段"],
  parameters: Type.Object({
    opportunity_id: Type.String({ description: "商机ID" }),
    owner: Type.Optional(Type.String({ description: "负责人，默认叶霖德" })),
  }),
  async execute(_toolCallId: string, params: any, _signal?: any, _onUpdate?: any, ctx?: any) {
    const owner = params.owner || "叶霖德";
    return runPython("actions.py", ["--id", params.opportunity_id, "--claim", "--owner", owner], resolveEnginesForCwd(ctx?.cwd));
  },
};

const invalidTool = {
  name: "mark_invalid",
  label: "标记商机无效",
  description: "标记指定商机为无效（生命周期 -> invalid），不再进入队列。",
  promptSnippet: "标记商机无效",
  promptGuidelines: ["标记无效后商机会从队列中移除"],
  parameters: Type.Object({
    opportunity_id: Type.String({ description: "商机ID" }),
    owner: Type.Optional(Type.String({ description: "操作人" })),
  }),
  async execute(_toolCallId: string, params: any, _signal?: any, _onUpdate?: any, ctx?: any) {
    const args = ["--id", params.opportunity_id, "--invalid"];
    if (params.owner) args.push("--owner", params.owner);
    return runPython("actions.py", args, resolveEnginesForCwd(ctx?.cwd));
  },
};

export default function fxLeadRadar(pi: ExtensionAPI) {
  pi.registerTool(crawlTool);
  pi.registerTool(crawlNewsTool);
  pi.registerTool(ruleScreenTool);
  pi.registerTool(reviewTool);
  pi.registerTool(buildQueueTool);
  pi.registerTool(renderTool);
  pi.registerTool(claimTool);
  pi.registerTool(invalidTool);
  pi.registerTool(startServerTool);
  pi.registerTool(analyzeCompanyTool);
  pi.registerTool(askInsightsTool);
  pi.registerTool(companyInsightTool);
  pi.registerTool(memoryStatusTool);
  pi.registerTool(clearMemoryTool);

  pi.registerCommand("radar", {
    description: "跑一遍企业外汇需求商机雷达全流程",
    handler: async (_args, ctx) => {
      try {
        ctx.ui.notify("🛰️ 商机雷达流程启动：抓取→初筛→复核→队列→渲染…", "info");
      } catch { /* RPC 模式可能无 UI，忽略 */ }
      // 注入一条用户消息，让 Agent 真正执行工具并在聊天里展示全过程
      pi.sendUserMessage(
        "请跑一遍企业外汇需求商机雷达全流程：依次调用 crawl_cninfo、crawl_news、" +
        "rule_screen、review_opportunity(all=true)、build_daily_queue、render_web、start_server，" +
        "最后按 fx-radar-workflow 技能的汇报格式总结今日商机队列（附可点击的预览地址）。"
      );
    },
  });

  pi.on("session_start", async (_event, ctx) => {
    ctx.ui.notify(
      "🛰️ 企业外汇智能体已就绪 | 15 tools\n" +
      "  流程: crawl_cninfo / crawl_news / rule_screen / review_opportunity / build_daily_queue / render_web / start_server\n" +
      "  动作: claim_opportunity / mark_invalid\n" +
      "  RAG: analyze_company / ask_insights（证据级智能问答）\n" +
      "  画像: company_insight（拜访前必看画像卡）\n" +
      "  记忆: memory_status / clear_memory（跨轮次，追问可指代）\n" +
      "  命令: /radar",
      "info"
    );
  });
}
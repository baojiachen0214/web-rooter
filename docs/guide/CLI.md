# CLI Guide

## Philosophy

- `do` 是一号入口：先编译 IR，再 lint，再执行
- `quick` 是兼容入口：内部仍走编排层
- CLI 是一等接口：MCP 只是 CLI 能力的适配层
- URL 访问优先 `visit`，跨站信息检索优先 `web/deep`
- 深度搜索与深度爬取分离，避免默认过重

## Core Commands

```bash
python main.py help
python main.py --version
python main.py doctor
python main.py do <goal> [--skill=name] [--dry-run] [--strict] [--js] [--top=N] [--crawl-assist] [--crawl-pages=N] [--html-first|--no-html-first]
python main.py do-plan <goal> [--skill=name] [--strict] [--js] [--top=N] [--crawl-assist] [--crawl-pages=N] [--html-first|--no-html-first]
python main.py do-submit <goal> [--skill=name] [--strict] [--js] [--top=N] [--crawl-assist] [--crawl-pages=N] [--timeout-sec=N] [--html-first|--no-html-first]
python main.py jobs [--limit=N] [--status=queued|running|completed|failed]
python main.py job-status <job_id> [--with-result]
python main.py job-result <job_id>
python main.py safe-mode [status|on|off] [--policy=strict]
python main.py skills [--resolve "<goal>"] [--compact|--full]
python main.py ir-lint <ir-file|json|workflow-file|workflow-json>
python main.py quick <url|query> [--js] [--crawl-pages=N]
python main.py visit <url> [--js]
python main.py web <query> [--no-crawl] [--crawl-pages=N] [--num-results=N] [--engine=name|a,b]
python main.py deep <query> [--en] [--crawl=N] [--num-results=N] [--variants=N] [--engine=name|a,b] [--news] [--platforms] [--commerce] [--channel=x,y]
python main.py mindsearch <query> [--turns=N] [--branches=N] [--num-results=N] [--crawl=N] [--planner=name] [--strict-expand] [--channel=x,y]
python main.py social <query> [--platform=xiaohongshu|zhihu|tieba|douyin|bilibili|weibo]
python main.py shopping <query> [--platform=taobao|jd|pinduoduo|meituan]
python main.py crawl <url> [pages] [depth] [--pattern=REGEX] [--allow-external] [--no-subdomains]
python main.py academic <query> [--papers-only|--with-code] [--no-abstracts] [--num-results=N] [--source=xxx]
python main.py processors [--load=module:object] [--force]
python main.py planners [--load=module:object] [--force]
python main.py challenge-profiles
python main.py auth-profiles
python main.py auth-hint <url>
python main.py auth-template [path] [--force]
python main.py workflow-schema
python main.py workflow-template [path] [--scenario=social_comments|academic_relations] [--force]
python main.py workflow <spec-file|json> [--var key=value] [--set key=value] [--strict] [--dry-run]
python main.py context [--limit=N] [--event=type]
python main.py telemetry [--no-refresh]
```

## Typical Workflows

### 1) 单入口执行（推荐）

```bash
python main.py do "抓取知乎和小红书评论区观点并给出处" --dry-run
python main.py do "分析 RAG benchmark 论文关系并给引用" --skill=academic_relation_mining --strict
python main.py do-plan "抓取知乎评论区观点并给出处" --skill=social_comment_mining
python main.py do-submit "分析 RAG benchmark 论文关系并给引用" --skill=academic_relation_mining --strict --timeout-sec=1200
python main.py skills --resolve "抓取知乎评论区观点并给出处" --compact
python main.py skills --resolve "抓取知乎评论区观点并给出处" --full
python main.py jobs --status=running
python main.py safe-mode on --policy=strict
```

### 2) 快速查资料

```bash
python main.py quick "OpenAI Agents SDK"
```

### 3) 多引擎搜索 + 页面摘要

```bash
python main.py web "RAG benchmark 2026" --crawl-pages=5
python main.py web "RAG benchmark" --engine=quark --num-results=6 --no-crawl
```

### 4) 深度搜索（多查询变体）

```bash
python main.py deep "量化交易 因子" --variants=4 --crawl=5
python main.py deep "RAG benchmark" --engine=quark --num-results=8 --crawl=0
```

### 4.1) 渠道扩展（媒体/平台站点）

```bash
python main.py deep "OpenAI 最新动态" --news
python main.py deep "AI Agent 工程实践" --platforms
python main.py deep "羽绒服选购" --commerce
python main.py deep "AI 芯片供应链" --channel=news,platforms,commerce
```

### 5) 站点定向爬取

```bash
python main.py crawl "https://docs.python.org/3/" 20 2 --pattern="/3/library/" --no-subdomains
```

### 6) MindSearch 图研究

```bash
python main.py mindsearch "多模态大模型 工程化落地" --turns=3 --branches=4 --planner=heuristic --strict-expand --channel=news,platforms
```

### 7) 学术模式（带出处）

```bash
python main.py academic "RAG benchmark" --papers-only --source=arxiv --source=semantic_scholar
python main.py academic "Agent eval framework" --with-code --num-results=15 --source=github
```

### 8) 需登录站点（本地登录态模板）

```bash
python main.py auth-template
python main.py auth-profiles
python main.py auth-hint https://www.zhihu.com
```

填写本地 `login_profiles.json` 后，Claude Code 可以继续调用 `social/site/deep/mindsearch`，避免反复询问登录细节。

### 9) AI 可编排 Workflow（不写死爬虫流程）

```bash
python main.py workflow-schema
python main.py workflow-template .web-rooter/workflow.social.json --scenario=social_comments --force
python main.py workflow .web-rooter/workflow.social.json --var topic="手机 评测" --var top_hits=8 --dry-run

python main.py workflow-template .web-rooter/workflow.academic.json --scenario=academic_relations --force
python main.py workflow .web-rooter/workflow.academic.json --var topic="RAG benchmark" --strict
```

Workflow 机制的意义：
- 外层 AI 按目标动态决定“搜什么、爬什么、怎么爬”
- 每一步可组合（search/visit/crawl/extract/academic/mindsearch）
- 用 `${vars...}` / `${steps...}` 在步骤间传递上下文，减少硬编码站点脚本

## Notes

- `deep --variants` 用于子查询分解，默认值为 `1`
- `deep` 默认通用引擎已包含 `quark`（与 `google/bing/baidu/duckduckgo` 并行）
- `deep --news/--platforms/--commerce` 会自动扩展为 `site:domain` 查询，覆盖媒体、社交与电商站点
- `mindsearch` 输出 `mindsearch_compat`，包含 `node` / `adjacency_list` / `ref2url`，便于外层 AI 直接消费
- `do` / `workflow` 在执行前都可 `--dry-run`，并输出 IR + lint 结果
- `do-plan` 会返回阶段化 skills 剧本（phases + recommended_cli_sequence），给外层 AI 作短上下文执行清单
- `do-plan` 还会返回 `phase_wakeup` 与 `ai_contract`，用于阶段唤醒与执行校验
- `do-submit` 将长任务放到后台执行，避免 CLI 阻塞超时；用 `jobs/job-status/job-result` 轮询
- `do-submit --timeout-sec=N` 可显式设置后台任务超时时间（默认 `900` 秒）
- `safe-mode strict` 会拦截低层命令，强制外层 AI 优先走 `do-plan`/`do`
- 未知命令若疑似拼写错误，会附带自动 skill 路由修复建议（`do-plan`/`do --dry-run`）
- `telemetry`（别名：`budget`/`budget-telemetry`）可查看统一预算健康快照（pressure/utilization/alerts）
- `skills --resolve "<goal>"` 默认返回紧凑 probe（低上下文），加 `--full` 返回完整技能目录
- `WEB_ROOTER_SKILL_MIN_MARGIN` 可调技能判定的最小分差（默认 `0.35`）
- `WEB_ROOTER_SCHEDULER_MAX_QUEUE_SIZE` / `WEB_ROOTER_SCHEDULER_DUPEFILTER_MAX_ENTRIES` 可调调度器硬预算
- Spider 默认开启自适应预算控制：会按内存与错误率压力自动收缩/恢复队列与去重容量
- `ir-lint` 可独立校验 AI 生成的 IR/workflow，防止错误命令直达执行
- `python scripts/regression/run_skill_ab.py --arm-a=auto --arm-b=social_comment_mining` 可做 skills A/B 回归（默认 compile-only）
- `python scripts/regression/run_skill_ab.py --execute --max-cases=2 --case-timeout-sec=180` 可跑真实执行回归并避免长时间卡住
- `crawl` 默认不跨站，`--allow-external` 才会跨域
- 无法稳定用 HTTP 抓取时，优先 `visit --js` 或 `quick --js`
- `web/deep/academic/research` 输出包含 `citations` 字段；`deep/research` 还包含 `comparison` 交叉来源统计
- `challenge-profiles` 会显示 profile 来源（`builtin` 或 JSON 路径），便于排查平台级挑战策略是否生效
- `profiles/challenge_profiles/china_platforms.json` 已提供社交/电商/GitHub 的平台级 challenge 模板，可按站点继续细化

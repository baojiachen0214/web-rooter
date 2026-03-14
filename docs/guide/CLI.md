# CLI Guide

## Default Entry

安装后默认入口是 `wr`。  
源码调试时可把 `wr` 替换为 `python main.py`。

示例：

```bash
wr help
wr --version
wr doctor
```

## Philosophy

- `do` 是一号入口：Intent -> Skill -> IR -> Lint -> Execute
- `quick` 是兼容入口：内部仍走编排层
- CLI 是一等接口：MCP 只是适配层
- URL 访问优先 `visit`，跨站研究优先 `web/deep/do`

## Core Commands

```bash
wr help
wr --version
wr doctor

wr do <goal> [--skill=name] [--dry-run] [--strict] [--js] [--top=N] [--crawl-assist] [--crawl-pages=N] [--command-timeout-sec=N] [--html-first|--no-html-first]
wr do-plan <goal> [--skill=name] [--strict] [--js] [--top=N] [--crawl-assist] [--crawl-pages=N] [--html-first|--no-html-first]
wr do-submit <goal> [--skill=name] [--strict] [--js] [--top=N] [--crawl-assist] [--crawl-pages=N] [--timeout-sec=N] [--html-first|--no-html-first]

wr jobs [--limit=N] [--status=queued|running|completed|failed]
wr jobs-clean [--keep=N] [--days=N] [--all]
wr job-status <job_id> [--with-result]
wr job-result <job_id>

wr safe-mode [status|on|off] [--policy=strict]
wr skills [--resolve "<goal>"] [--compact|--full]
wr ir-lint <ir-file|json|workflow-file|workflow-json>

wr quick <url|query> [--js] [--top=N] [--crawl-pages=N] [--strict] [--command-timeout-sec=N]
wr visit <url> [--js]
wr html <url> [--js] [--max-chars=N] [--no-fallback]
wr web <query> [--no-crawl] [--crawl-pages=N] [--num-results=N] [--engine=name|a,b]
wr deep <query> [--en] [--crawl=N] [--num-results=N] [--variants=N] [--engine=name|a,b] [--news] [--platforms] [--commerce] [--channel=x,y]
wr mindsearch <query> [--turns=N] [--branches=N] [--num-results=N] [--crawl=N] [--planner=name] [--strict-expand] [--channel=x,y]
wr social <query> [--platform=xiaohongshu|zhihu|tieba|douyin|bilibili|weibo|reddit|twitter]
wr shopping <query> [--platform=taobao|jd|pinduoduo|meituan]
wr academic <query> [--papers-only|--with-code] [--no-abstracts] [--num-results=N] [--source=xxx]
wr crawl <url> [pages] [depth] [--pattern=REGEX] [--allow-external] [--no-subdomains]

wr workflow-schema
wr workflow-template [path] [--scenario=social_comments|academic_relations] [--force]
wr workflow <spec-file|json> [--var key=value] [--set key=value] [--strict] [--dry-run]

wr processors [--load=module:object] [--force]
wr planners [--load=module:object] [--force]
wr challenge-profiles
wr auth-profiles
wr auth-hint <url>
wr auth-template [path] [--force]
wr context [--limit=N] [--event=type]
wr telemetry [--no-refresh]
wr pressure [--no-refresh]
wr events [--limit=N] [--event=type] [--source=name] [--since=seq]
wr artifact [--nodes=N] [--edges=N] [--kind=page|url|domain|request|session]
```

## Typical Workflows

### 1) AI-first single entry

```bash
wr skills --resolve "抓取知乎评论区观点并给出处" --compact
wr do-plan "抓取知乎评论区观点并给出处" --skill=social_comment_mining
wr do "抓取知乎评论区观点并给出处" --dry-run
wr do "抓取知乎评论区观点并给出处" --strict
```

### 2) Async long task

```bash
wr do-submit "分析 RAG benchmark 论文关系并给引用" --skill=academic_relation_mining --strict --timeout-sec=1200
wr jobs --status=running
wr job-status <job_id>
wr job-result <job_id>
wr jobs-clean --keep=80 --days=7
```

### 3) Quick lookup and deep research

```bash
wr quick "OpenAI Agents SDK"
wr web "RAG benchmark 2026" --crawl-pages=5
wr deep "AI Agent 工程实践" --variants=4 --crawl=3 --platforms --channel=news
```

### 4) Workflow template

```bash
wr workflow-schema
wr workflow-template .web-rooter/workflow.social.json --scenario=social_comments --force
wr workflow .web-rooter/workflow.social.json --var topic="手机 评测" --var top_hits=8 --dry-run
```

## Notes

- `wr doctor` 通过前，建议先用 `skills/do-plan/do --dry-run` 做规划与校验
- `--command-timeout-sec` 可为单条命令设置保护超时，避免 CLI 长时间挂住
- `do-submit --timeout-sec=N` 控制后台作业 worker 超时（默认 `900` 秒）
- `jobs-clean` 用于回收历史作业目录，避免长期磁盘堆积
- `safe-mode strict` 会限制低层命令，强制 AI 走高层入口
- `telemetry` 可查看预算健康度（pressure/utilization/alerts）

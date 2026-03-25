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

- `do` 是一号入口：Intent -> Skill -> IR -> Lint -> Execute -> Completion Post-check
- `quick` 是兼容入口：内部仍走编排层
- CLI 是一等接口：agent / MCP 复用 CLI 同源的 do runtime
- URL 访问优先 `visit`，跨站研究优先 `web/deep/do`
- 社交详情页优先走平台专用 reader，而不是先假设通用 HTML 可读

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
wr skills-install [--no-home]
wr add-skills-dir <path> [--tool=claude|codex|cursor|generic] [--register-only]
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

对于小红书 / Bilibili 这类详情页任务，建议仍优先走 `do-plan -> do`，因为：

- planner 会把详情 URL 识别成 `social_detail`
- 小红书详情页会落到 `xiaohongshu_detail` strategy
- Bilibili 视频详情页会落到 `bilibili_detail` strategy
- workflow 结束后会给 completion 百分比、缺失项和 fallback 建议

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


## Completion Post-check

当 workflow spec 内含 `completion_contract` 时，`wr do` / `wr workflow` 在执行后会自动做一次 post-check。

当前主要检查：

- `body`
- `author`
- `engagement`
- `comments`
- `search_hits_required`
- `browser_required`
- `auth_hint_checked`
- `comment_capture_preferred`

典型结果：

- `complete`：需要的输出都拿到了
- `partial`：步骤大体成功，但正文/评论等仍有缺失
- `incomplete`：关键输出基本没拿到

这一步的目标是避免把“页面打开成功”误判成“任务已经完成”。


## AI skills discovery

Web-Rooter 现在把 AI skills 发现问题显式化了：

- `wr skills-install`：把 skills 写到常见 AI 工具约定位置
- `wr add-skills-dir <path> --tool=...`：显式登记并写入额外 skills 目录
- `wr doctor`：检查 skills 是否真的可被工具发现

默认覆盖的常见位置包括：

- `.claude/skills/web-rooter/SKILL.md`
- `AGENTS.md`
- `.agents/skills/web-rooter/SKILL.md`
- `.cursor/rules/web-rooter-cli.mdc`

## Micro skills

`wr skills --resolve`、`wr do-plan`、`wr do` 等高层命令会在结构化输出中附带 `micro_skills`。

用途：

- 给 AI 一个短而硬的执行提示
- 约束“当前任务优先哪些命令、避免哪些命令”
- 降低把 `crawl` / `site` / `extract` 误用于社交详情页或复杂任务的概率


## Xiaohongshu (小红书) Usage Guide

Web-Rooter provides **two ways** to access Xiaohongshu, choose based on your scenario:

### Method 1: `wr social` (Recommended, Safe & Compliant)

**For**: Searching notes, browsing public content

**Features**:
- ✅ No login required, works out of the box
- ✅ Browser-based access, safe and compliant
- ✅ Only accesses publicly visible search results

**Examples**:
```bash
# Search XHS notes
wr social "travel tips" --platform=xiaohongshu

# Get specific note content
wr html "https://xiaohongshu.com/explore/xxx" --js
```

### Method 2: `wr xhs` (Advanced, With Risks)

⚠️ **Risk Warning**: `wr xhs` directly calls XHS internal APIs, requires login, and carries **risk of account suspension**. Based on open-source project [jackwener/xiaohongshu-cli](https://github.com/jackwener/xiaohongshu-cli).

**For**: Deep operations (full comments, likes, posting, etc.)

**Before using**:
1. Must explicitly inform user of the risks
2. Recommend using a test account only
3. Control operation frequency

**Examples**:
```bash
# Login
wr xhs login

# Get comments
wr xhs comments <note_id> --all

# Like (high risk)
wr xhs like <note_id>
```

### Decision Table

| Need | Recommended | Reason |
|------|-------------|--------|
| Search/Browse | `wr social` | No login needed, safe |
| Get note content | `wr html` / `wr do` | Browser-based, no login |
| Full comments | `wr xhs` | Requires API access, inform risk |
| Like/Comment/Post | `wr xhs` | High risk operations, use with caution |

### Risk Disclaimer

- **Account Ban Risk**: Frequent API calls, likes, comments, posts may trigger XHS anti-spam
- **Test Account Only**: Never use your main account for `wr xhs`
- **Rate Limiting**: Control frequency, avoid batch operations
- **Compliance**: Respect platform Terms of Service

# Configuration Guide

## Configuration Sources

1. `config.py` (current source of truth)
2. CLI flags (`main.py` commands)
3. Environment variables for runtime behavior (optional)

## Core Runtime Config (`config.py`)

Key objects:

- `crawler_config`: timeout/retry/delay/concurrency
- `browser_config`: headless, timeout, real Chrome/CDP options
- `stealth_config`: anti-bot options and fingerprint behavior
- `server_config`: HTTP server host/port

Edit `config.py` directly when you need persistent defaults.

## CLI Overrides

Examples:

```bash
python main.py deep "OpenAI updates" --crawl=5 --num-results=20 --variants=3
python main.py academic "RAG benchmark" --num-results=15 --source=arxiv --source=semantic_scholar
python main.py web "agent framework" --crawl-pages=5
```

## Output Size Control

For very large JSON responses in CLI output:

```bash
# Linux/macOS
export WEB_ROOTER_MAX_OUTPUT_CHARS=50000

# Windows PowerShell
$env:WEB_ROOTER_MAX_OUTPUT_CHARS="50000"
```

## Advanced Runtime Extensions

### Challenge Workflow (Cloudflare/JS Challenge)

```bash
# 指定单个 challenge profile 配置文件
export WEB_ROOTER_CHALLENGE_PROFILE_FILE=/abs/path/challenge_profiles.json

# 指定 challenge profile 目录（自动加载 *.json）
export WEB_ROOTER_CHALLENGE_PROFILE_DIR=/abs/path/challenge_profiles

# 默认会自动加载：
#   ./profiles/challenge_profiles/*.json
#   ~/.web-rooter/challenge-profiles/*.json

# 强制使用某个 profile（调试用）
export WEB_ROOTER_CHALLENGE_PROFILE=cloudflare_turnstile

# 每轮最多尝试多少 profile
export WEB_ROOTER_CHALLENGE_MAX_PROFILES=3
```

### Login/Auth Profiles（需登录站点）

```bash
# 指定单个登录态 profile 文件
export WEB_ROOTER_AUTH_PROFILE_FILE=/abs/path/login_profiles.json

# 指定登录态 profile 目录（自动加载 *.json）
export WEB_ROOTER_AUTH_PROFILE_DIR=/abs/path/auth_profiles
```

默认会尝试读取：

- `./.web-rooter/login_profiles.json`
- `~/.web-rooter/login_profiles.json`

推荐流程：

1. 先执行 `python main.py auth-template` 生成模板
2. 在本地填充 cookies / storage_state（不要提交到仓库）
3. 使用 `python main.py auth-hint https://target.site` 验证命中情况

### Platform Search Templates + Recovery Mode

```bash
# 自定义平台搜索入口/域名优先级模板（默认读取仓库内模板）
export WEB_ROOTER_PLATFORM_PROFILE_FILE=/abs/path/platform_profiles.json

# 每个引擎最多尝试多少入口 URL（含主模板+备用模板）
export WEB_ROOTER_ENGINE_URL_CANDIDATES=3

# 浏览器兜底最多尝试多少入口 URL
export WEB_ROOTER_BROWSER_URL_CANDIDATES=2

# 平台级 backup 站点数量与单站点超时
export WEB_ROOTER_PLATFORM_BACKUP_DOMAINS=6
export WEB_ROOTER_PLATFORM_BACKUP_TIMEOUT_SEC=80

# 结果为 0 时是否启用 recovery（低置信结果兜底）
export WEB_ROOTER_ENABLE_RECOVERY_MODE=1
export WEB_ROOTER_RECOVERY_MAX_RESULTS=3
```

默认平台模板路径：

- `./profiles/search_templates/platform_profiles.json`

### MindSearch Planner

```bash
# 选择已注册 planner 名称
export WEB_ROOTER_MINDSEARCH_PLANNER_NAME=heuristic

# 直接加载 planner（module:object 或 file.py:object）
export WEB_ROOTER_MINDSEARCH_PLANNER=plugins/planners/example_planner.py:create_planner

# 批量加载 planner
export WEB_ROOTER_MINDSEARCH_PLANNERS=plugins/planners/example_planner.py:create_planner

# 强制每个完成节点继续扩展 follow-up
export WEB_ROOTER_MINDSEARCH_STRICT=1
```

### Postprocess + Context

```bash
# 加载抓取后处理扩展
export WEB_ROOTER_POSTPROCESSORS=plugins/post_processors/example_processor.py:create_processor

# 全局上下文持久化位置
export WEB_ROOTER_CONTEXT_PATH=.web-rooter/global-context.jsonl
export WEB_ROOTER_CONTEXT_MAX_EVENTS=500

# 记录 MindSearch 节点级事件
export WEB_ROOTER_CONTEXT_CAPTURE_MINDSEARCH_NODES=1

# (Windows 可选) 显式切换 SelectorEventLoop，默认关闭
export WEB_ROOTER_WINDOWS_SELECTOR_LOOP=0
```

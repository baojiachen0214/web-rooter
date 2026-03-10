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

# 强制使用某个 profile（调试用）
export WEB_ROOTER_CHALLENGE_PROFILE=cloudflare_turnstile

# 每轮最多尝试多少 profile
export WEB_ROOTER_CHALLENGE_MAX_PROFILES=3
```

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

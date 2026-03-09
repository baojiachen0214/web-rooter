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


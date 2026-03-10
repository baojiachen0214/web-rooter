# Web-Rooter Release Notes (2026-03-10)

## Scope

- AI orchestration-first execution path is now default for CLI/MCP.
- HTML-first analysis is now first-class, crawl becomes auxiliary.
- Browser shutdown/timeout stability improved for long-running tasks.

## Key Changes

- New high-level orchestration entry in agent layer:
  - `orchestrate_task(...)`
  - route auto-classification: `url / academic / social / commerce / general`
  - file: `agents/web_agent.py`

- New raw HTML retrieval primitive:
  - `fetch_html(...)`
  - used by workflow and default orchestration
  - file: `agents/web_agent.py`

- Workflow engine extended:
  - new tool alias: `fetch_html` / `web_fetch_html` / `html`
  - social/academic templates switched to HTML-first reading
  - file: `core/workflow.py`

- CLI changes:
  - new command: `html <url> [--js] [--max-chars=N] [--no-fallback]`
  - new command: `task <goal> ...` (recommended default)
  - `quick` now defaults to orchestration mode
  - compatibility flag: `--legacy` (restores old URL/query shortcut behavior)
  - file: `main.py`

- MCP tools changes:
  - new recommended tool: `web_orchestrate`
  - new helper: `web_fetch_html`
  - file: `tools/mcp_tools.py`

- Browser stability hardening:
  - active operation tracking and close-time cleanup
  - graceful cancellation handling in `fetch(...)`
  - loop-level filtering for known Playwright close/timeout future-noise
  - file: `core/browser.py`

## Behavior Changes

- `quick` command now prioritizes workflow orchestration instead of direct hardcoded path.
- Default analysis reads HTML first and lets upper-layer AI decide extraction path.
- Crawl is optional and controlled via `--crawl-assist`.

## Compatibility

- Existing direct commands (`visit`, `web`, `deep`, `social`, `academic`, etc.) remain available.
- For older automation depending on pre-change `quick` behavior, use:
  - `quick ... --legacy`

## Validation

- Full real regression run: `pass`
  - report: `docs/reports/REAL_REGRESSION_latest2.md`
  - json: `temp/real_regression_latest2.json`
- Regression comparison:
  - `docs/reports/REAL_REGRESSION_COMPARISON_20260310.md`


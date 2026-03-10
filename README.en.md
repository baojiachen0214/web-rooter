<div align="center">
  <img src="./LOGO.png" alt="Web-Rooter Logo" width="240" />
  <h1>Web-Rooter</h1>
  <p><strong>AI-Native Web Search & Deep Crawling Infrastructure</strong></p>
  <p>Providing verifiable internet information retrieval for Claude Code, Cursor, and AI coding assistants</p>

  <p>
    <a href="./LICENSE"><img src="https://img.shields.io/badge/license-MIT-green.svg" alt="License MIT"></a>
    <img src="https://img.shields.io/badge/python-3.10%2B-blue.svg" alt="Python 3.10+">
    <img src="https://img.shields.io/badge/platform-Windows%20%7C%20macOS%20%7C%20Linux-black.svg" alt="Platforms">
    <img src="https://img.shields.io/badge/interface-CLI%20%7C%20MCP%20%7C%20HTTP-orange.svg" alt="Interfaces">
    <img src="https://img.shields.io/badge/playwright-✓-brightgreen.svg" alt="Playwright">
  </p>

  <p>
    <a href="./README.md">Landing</a> |
    <a href="./README.zh-CN.md">简体中文</a>
  </p>
</div>

---

## Why Web-Rooter?

AI coding assistants often face these challenges when solving real-world problems:

| Pain Point | Web-Rooter Solution |
|------------|---------------------|
| Unverifiable search results | Auto-fetch original pages with `citations` trail |
| Anti-bot page failures | HTTP + Browser dual-channel, auto-fallback to Playwright |
| Single source of information | Multi-engine parallel + channel expansion (news/social/commerce/academic) |
| Chaotic output formats | Unified structured output with `references_text` ready to cite |
| Disconnected from AI toolchain | Native MCP protocol support, works out-of-box with Claude Code |

---

## Core Capabilities

### Tech Stack

- **Python 3.10+** + **AsyncIO** - High-performance async crawling engine
- **Playwright** - Browser automation & anti-detection
- **MCP Protocol** - Native AI toolchain integration
- **Multi-Engine Search** - Google/Bing/Baidu/DuckDuckGo parallel

### Highlights

1. **Unified Search & Crawl** - One-stop from retrieval to content extraction, no tool switching needed
2. **Smart Anti-Bot** - HTTP first, auto-fallback to Playwright on challenge pages, 80%+ success rate
3. **Citation-Ready Output** - Auto-generated reference format, AI-ready
4. **Multi-Source Validation** - `comparison.corroborated_results` shows corroborated results count
5. **Channel Expansion** - `--news/--platforms/--commerce` one-click channel expansion
6. **Academic Mode** - 10+ academic databases, paper+code joint search
7. **Native MCP Integration** - Claude Code ready out-of-box, 15+ tools exposed to AI
8. **Challenge Workflow Routing** - Built-in Cloudflare/general challenge profiles with JSON-based custom routing
9. **MindSearch Compatibility Output** - Includes `mindsearch_compat` (`node` / `adjacency_list` / `ref2url`) for external AI orchestration
10. **Platform Challenge Template Library** - Auto-loads `profiles/challenge_profiles/*.json` (Xiaohongshu/Zhihu/Weibo/Douyin/E-commerce templates included)
11. **Pluggable Extensions** - Hot-loadable `postprocessors` and `planners`
12. **Local Auth Template Flow** - `auth-template` / `auth-profiles` / `auth-hint` for login-required sites
13. **AI-Orchestrated Workflow** - Declarative JSON flow lets AI decide each crawl/search step dynamically

### Known Limitations

- **Network Timeouts**: `deep` / `social` commands may experience timeouts in certain network environments (caused by anti-bot/challenge pages). Suggested workarounds:
  - Use `--crawl=0` to skip page crawling and retrieve search results only
  - Prefer the `web` command as an alternative
  - Check network connection or try switching network environments

---

## Quick Start

### Installation

```bash
pip install -r requirements.txt
python -m playwright install chromium
python main.py --doctor
```

### 5-Minute Walkthrough

```bash
# 1. Quick lookup (use this when you forget commands)
python main.py quick "OpenAI Agents SDK best practices"

# 2. Multi-engine search + auto crawling
python main.py web "RAG evaluation benchmark 2025" --crawl-pages=5

# 3. Deep research (multi-query variants + channel expansion)
python main.py deep "AI agent engineering" --variants=4 --crawl=5 --platforms --channel=news

# 4. Social media search
python main.py social "iPhone 17 review" --platform=reddit --platform=twitter

# 5. E-commerce search
python main.py shopping "light down jacket" --platform=taobao --platform=jd

# 6. Academic search (with citation format)
python main.py academic "RAG evaluation" --papers-only --source=arxiv --source=semantic_scholar

# 7. MindSearch graph research (planner-aware)
python main.py mindsearch "multimodal LLM production engineering" --turns=3 --branches=4 --planner=heuristic --strict-expand --channel=news,platforms

# 8. Inspect extension and challenge routing state
python main.py planners
python main.py challenge-profiles
python main.py auth-template
python main.py auth-hint https://www.zhihu.com
python main.py workflow-schema
python main.py workflow-template .web-rooter/workflow.social.json --scenario=social_comments --force
python main.py workflow .web-rooter/workflow.social.json --var topic="phone review" --var top_hits=8
python main.py context --limit=20
```

---

## MCP Integration (Claude Code Ready)

### Automatic Setup

```bash
# Windows
scripts\windows\setup-claude-mcp.bat

# macOS / Linux
chmod +x scripts/unix/setup-claude-mcp.sh
./scripts/unix/setup-claude-mcp.sh
```

### Manual Configuration

Add to your Claude config file (`~/Library/Application Support/Claude/config.json` on macOS, `%APPDATA%\Claude\config.json` on Windows):

```json
{
  "mcpServers": {
    "web-rooter": {
      "command": "python",
      "args": ["main.py", "--mcp"],
      "cwd": "/path/to/web-rooter",
      "env": {
        "PYTHONUNBUFFERED": "1",
        "PYTHONIOENCODING": "utf-8"
      }
    }
  }
}
```

### MCP Tools Reference

| Tool | Purpose |
|------|---------|
| `web_search_internet` | Multi-engine web search |
| `web_research` | Deep topic research |
| `web_search_academic` | Academic paper search |
| `web_mindsearch` | MindSearch graph research |
| `web_search_social` | Social media search |
| `web_search_commerce` | E-commerce/local service search |
| `web_fetch` / `web_fetch_js` | HTTP / Browser page fetching |
| `web_crawl` | Deep site crawling |
| `web_extract` | Targeted information extraction |
| `web_context_snapshot` | Global deep-crawl context snapshot |
| `web_postprocessors` / `web_planners` | Post-process / planner extension management |
| `web_challenge_profiles` | Challenge workflow profile listing |
| `web_auth_profiles` / `web_auth_hint` / `web_auth_template` | Local auth profile management for login-required sites |

---

## Installation by OS

### Windows

- Basic install: `install.bat`
- Install global `wr` command: `scripts\windows\install-system-cli.bat`
- Claude MCP setup: `scripts\windows\setup-claude-mcp.bat`

### macOS / Linux

```bash
chmod +x scripts/unix/*.sh
./scripts/unix/install-system-cli.sh
./scripts/unix/setup-claude-mcp.sh
```

---

## Repository Layout

```
web-rooter/
├── main.py                 # CLI/MCP/HTTP unified entry
├── agents/                 # Orchestration layer (visit/search/research/crawl)
│   └── web_agent.py
├── core/                   # Search, crawler, browser, parser core
│   ├── crawler.py          # HTTP crawling
│   ├── browser.py          # Playwright browser management
│   ├── challenge_workflow.py # Challenge workflow routing/orchestration
│   ├── global_context.py   # Global deep-crawl event store
│   ├── postprocess.py      # Post-process extension registry
│   ├── search/             # Search engines
│   │   ├── engine_base.py
│   │   ├── advanced.py
│   │   ├── mindsearch_pipeline.py
│   │   ├── research_planner.py
│   │   └── universal_parser.py
│   ├── academic_search.py  # Academic search
│   └── citation.py         # Citation generation
├── plugins/                # User extensions (examples)
│   ├── post_processors/
│   └── planners/
├── profiles/               # Built-in configurable templates
│   ├── challenge_profiles/ # Platform challenge profile JSONs
│   └── auth/               # Local auth profile template JSON
├── tools/                  # MCP adapter
│   └── mcp_tools.py
├── scripts/                # Cross-platform install scripts
│   ├── windows/
│   └── unix/
├── docs/                   # Documentation
│   ├── guide/              # User guides
│   ├── reference/          # API reference
│   └── architecture/       # Architecture docs
├── tests/                  # Automated tests
└── temp/                   # Reference snapshots (not runtime deps)
```

---

## Documentation

| Document | Content |
|----------|---------|
| [docs/README.md](./docs/README.md) | Documentation index |
| [docs/guide/INSTALLATION.md](./docs/guide/INSTALLATION.md) | Detailed installation guide |
| [docs/guide/CONFIGURATION.md](./docs/guide/CONFIGURATION.md) | Configuration guide |
| [docs/guide/CLI.md](./docs/guide/CLI.md) | Complete CLI reference |
| [docs/guide/MCP.md](./docs/guide/MCP.md) | MCP integration guide |
| [docs/reference/MCP_TOOLS.md](./docs/reference/MCP_TOOLS.md) | MCP tools detailed reference |
| [docs/architecture/PROJECT_STRUCTURE.md](./docs/architecture/PROJECT_STRUCTURE.md) | Project architecture design |

---

## Open-Source Credits

This project draws inspiration from multiple excellent open-source projects in the search/crawling space. See [ACKNOWLEDGMENTS.md](./ACKNOWLEDGMENTS.md) for details.

---

## Usage Statement

**This project is specifically designed to assist Vibe Coding tools (such as Claude Code, Cursor, etc.) with information retrieval and literature search.**

⚠️ **Strictly prohibited from being repurposed into network-harmful attack tools, including but not limited to:**
- Large-scale malicious crawlers for DDoS attacks
- Automated registration/brushing/scalping tools
- Unauthorized data scraping by bypassing security mechanisms
- Any abusive behavior violating target website terms of service

Users should comply with relevant laws, regulations, and target website robots.txt and terms of service.

---

## License

MIT License - See [LICENSE](./LICENSE)

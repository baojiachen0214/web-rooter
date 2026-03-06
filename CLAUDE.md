# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Build & Run Commands

```bash
# Install dependencies
pip install -r requirements.txt
playwright install chromium

# Run demo
python demo.py

# Search demo (test internet search features)
python search_demo.py

# Interactive CLI mode
python main.py

# MCP Server (for AI integration)
python main.py --mcp

# HTTP API Server
python main.py --server
# Or directly: python server.py

# Run single command
python main.py visit https://example.com
python main.py search "query"
python main.py extract https://example.com "target info"
python main.py crawl https://example.com 5 2
python main.py web "AI 大模型 2025 最新进展"    # Internet search
python main.py research "机器学习入门"        # Deep research
python main.py academic "Transformer"         # Academic search
python main.py site https://github.com "AI"   # Site search
```

## Architecture Overview

**Three-layer architecture:**

1. **Core Layer (`core/`)**: Low-level web fetching and parsing
   - `crawler.py`: Async HTTP client with rate limiting, retries, concurrent fetching
   - `browser.py`: Playwright-based browser automation for JavaScript-rendered pages
   - `parser.py`: BeautifulSoup-based HTML parser extracting structured data
   - `search_engine.py`: Multi-search engine support (Bing, Google, Baidu, DuckDuckGo, Sogou)
   - `academic_search.py`: Academic search (arXiv, Google Scholar, PubMed, IEEE, GitHub, Gitee)
   - `form_search.py`: Auto form filling and site search

2. **Agent Layer (`agents/`)**: Natural language interface
   - `web_agent.py`: `WebAgent` class with methods for visit, search, extract, crawl, academic search, form search

3. **Tools/Server Layer (`tools/`, `server.py`)**: External interfaces
   - `mcp_tools.py`: MCP protocol tools (12 tools including academic and site search)
   - `server.py`: FastAPI HTTP server with REST endpoints

**Configuration**: Single `config.py` with dataclass-based config

## Key Patterns

- All components use async/await with `asyncio`
- Components implement `__aenter__`/`__aexit__` for context manager support
- Browser is lazy-initialized (only when `use_browser=True`)
- Knowledge base caches visited pages with titles, content, and links
- Search results are deduplicated and merged across multiple engines

## Internet Search Features

**Supported Search Engines:**
- Bing (default, most stable)
- Google
- Baidu (for Chinese queries)
- DuckDuckGo
- Sogou
- Google Scholar (for academic queries)

**Academic Sources:**
- arXiv (preprint papers)
- Google Scholar
- Semantic Scholar
- PubMed (biomedical papers)
- IEEE Xplore
- CNKI (Chinese papers)
- GitHub (code projects)
- Gitee (Chinese code projects)
- Papers With Code

**Search Modes:**
1. Single engine search: `web_search(query, engine, num_results)`
2. Multi-engine parallel search: `multi.search(query, engines=[...])`
3. Combined search with deduplication: `multi.search_combined(query)`
4. Smart search (search + crawl): `multi.smart_search(query)`
5. Agent internet search: `agent.search_internet(query, auto_crawl=True)`
6. Deep research: `agent.research_topic(topic, max_pages=10)`
7. **Academic search: `agent.search_academic(query, include_code=True)`**
8. **Site search: `agent.search_with_form(url, query)`**

## MCP Integration

Copy `claude-code-mcp.json` content to Claude Code config directory, or configure:
```json
{
  "mcpServers": {
    "web-rooter": {
      "command": "python",
      "args": ["main.py", "--mcp"],
      "cwd": "C:\\Users\\rukel\\Desktop\\Web-Rooter"
    }
  }
}
```

**Available MCP Tools:**
- `web_fetch` - Fetch webpage content
- `web_fetch_js` - Fetch with browser (JavaScript support)
- `web_search` - Search in already-visited pages
- `web_search_internet` - Internet search across multiple engines
- `web_search_combined` - Internet search + crawl top results
- `web_research` - Deep research on a topic (multi-step search + crawl)
- `web_search_academic` - Academic search (papers + code projects)
- `web_search_site` - Search within a website using its internal search form
- `web_extract` - Extract specific information
- `web_crawl` - Crawl a website
- `parse_html` - Parse HTML content
- `get_links` - Get page links

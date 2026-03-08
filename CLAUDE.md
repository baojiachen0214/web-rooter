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

# Advanced search commands (new!)
python main.py deep "苹果发布会" --en --crawl=5    # Deep search (multi-engine + multi-language)
python main.py social "iPhone 17" --platform=zhihu  # Social media search
python main.py tech "machine learning" --source=github  # Tech community search
python main.py export "AI 新闻" ai_news.json      # Export search results

# Run tests
python test_all.py
python test_advanced_search.py  # Test advanced search features
```

## Architecture Overview

**Three-layer architecture:**

1. **Core Layer (`core/`)**: Low-level web fetching and parsing
   - `crawler.py`: Async HTTP client with rate limiting, retries, concurrent fetching
   - `parser.py`: BeautifulSoup-based HTML parser extracting structured data
   - `browser.py`: Playwright-based browser automation for JavaScript-rendered pages
   - `search_engine.py`: Multi-search engine support (Bing, Google, Baidu, DuckDuckGo, Sogou)
   - `advanced_search.py`: **Advanced search with 21+ engines** (Google, Bing, Yandex, GitHub, Reddit, Twitter, etc.)
   - `academic_search.py`: Academic search (arXiv, Google Scholar, PubMed, IEEE, GitHub, Gitee)
   - `form_search.py`: Auto form filling and site search

2. **Agent Layer (`agents/`)**: Natural language interface
   - `web_agent.py`: `WebAgent` class with methods for visit, search, extract, crawl, academic search, form search

3. **Tools/Server Layer (`tools/`, `server.py`)**: External interfaces
   - `mcp_tools.py`: MCP protocol tools (12 tools including academic and site search)
   - `server.py`: FastAPI HTTP server with REST endpoints

**Configuration**: Single `config.py` with dataclass-based config. Environment variables via `.env` file.

## Key Patterns

- All components use async/await with `asyncio`
- Components implement `__aenter__`/`__aexit__` for context manager support
- Browser is lazy-initialized (only when `use_browser=True`)
- Knowledge base caches visited pages with titles, content, and links
- Search results are deduplicated and merged across multiple engines

## Data Classes

- `CrawlResult`: Web fetching result (html, status_code, error)
- `ExtractedData`: Parsed page data (title, text, links, metadata)
- `BrowserResult`: Browser fetch result with network idle wait
- `SearchResult`/`SearchResponse`: Search engine results
- `PaperResult`/`CodeProjectResult`: Academic search results
- `AgentResponse`: WebAgent response wrapper
- `PageKnowledge`: Cached page knowledge

## Internet Search Features

**Supported Search Engines (21+ engines):**

**General Search:**
- Bing (default, most stable)
- Google
- Baidu (for Chinese queries)
- DuckDuckGo
- Sogou
- **Yandex** (Russian engine, good for English)
- **Google US** (English)
- **Bing US** (English)

**Social Media:**
- **Bilibili** (B 站)
- **Zhihu** (知乎)
- **Weibo** (微博)
- **Reddit**
- **Twitter/X**
- **Hacker News**

**Tech Communities:**
- **GitHub** (code projects)
- **Stack Overflow** (Q&A)
- **Medium** (tech articles)

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
9. **Deep search: `deep_search.deep_search(query, use_english=True, crawl_top=5)`** - All engines in parallel
10. **Social media search: `search_social_media(query, platforms=[...])`**
11. **Tech community search: `search_tech(query, sources=[...])`**

## MCP Integration

Copy `claude-code-mcp.json` content to Claude Code config directory, or configure:
```json
{
  "mcpServers": {
    "web-rooter": {
      "command": "python",
      "args": ["main.py", "--mcp"],
      "cwd": "/path/to/web-rooter"
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
- `web_deep_search` - **Deep search across 4+ engines with multi-language support**
- `web_search_social` - **Search social media** (Bilibili, Zhihu, Weibo, Reddit, Twitter)
- `web_search_tech` - **Search tech communities** (GitHub, Stack Overflow, Medium, Hacker News)

## Testing

Run the comprehensive test suite:
```bash
python test_all.py
python test_advanced_search.py  # Test advanced search features
python tests/test_all_search_functions.py  # Comprehensive search function tests
```

Tests cover:
- Module imports
- WebAgent methods
- MCP tools
- HTTP API endpoints
- Academic search features
- Form search features
- CLI commands
- Async initialization

## Tool Usage Strategy

**Key Principle**: Choose the right tool for each task to avoid local optima.

### Quick Selection Guide

| Task Type | Best Tool | Why |
|-----------|-----------|-----|
| General info search | `web` or `deep` | Fast overview |
| Comprehensive research | `deep --en` | Multi-engine + bilingual |
| User reviews/feedback | `social` | Real user discussions |
| Tech/code projects | `tech` | GitHub, Stack Overflow |
| Academic papers | `academic` | arXiv, Google Scholar |
| Deep research topic | `research` | Multi-step analysis |
| Specific URL content | `visit` / `fetch` | Direct access |
| JavaScript pages | `fetch_js` | Full rendering |
| Multi-page crawling | `crawl` | Auto link following |
| Extract structured data | `extract` | AI-powered extraction |

### Common Workflows

**1. Information Discovery**
```
web_search(query) → fetch(top URLs) → extract(key info)
```

**2. Comprehensive Research**
```
deep_search(query, use_english=True, crawl_top=5) → analyze results
```

**3. Product/User Analysis**
```
web_search(product) + social_search(product) → compare findings
```

**4. Technical Investigation**
```
tech_search(topic, sources=["github", "stackoverflow"]) → fetch(project URLs)
```

### Avoiding Local Optima

❌ **Bad**: Always using `web_search` for everything
✅ **Good**: Choose based on task type

❌ **Bad**: Search without crawling content
✅ **Good**: Use `web_search_combined` or `deep --crawl=N`

❌ **Bad**: Using `fetch` for JavaScript pages
✅ **Good**: Use `fetch_js` for dynamic content

❌ **Bad**: Single search iteration
✅ **Good**: Use `research` for multi-step analysis

For detailed guidance, see `docs/TOOL_USAGE_STRATEGY.md`

## Information Source Policy ⭐ Important

**First-party data priority**: Always prefer content directly fetched by web-rooter over AI knowledge.

### Source Attribution

| Source | Attribution |
|--------|-------------|
| web-rooter search | `[web-rooter]` or `[搜索]` |
| Specific webpage | `[来源：URL]` |
| AI training data | `[AI 知识库]` |
| Not found | `[未找到]` |

### Response Template

```markdown
## Search Results

According to web-rooter search:

### [Topic]
[Content] [来源：URL or tool name]

---

## Additional Notes (Optional)

The following is from my training data for reference only:
[Content] [标注：AI 知识库]

---

## Source Summary
- Main content: web-rooter search (X sources)
- Supplementary: AI training data
- Not found: [list]
```

### Prohibited

❌ Do NOT present AI knowledge as search results
❌ Do NOT mix sources without attribution
❌ Do NOT fabricate URLs or citations

## Memory Optimization

Web-rooter automatically cleans up intermediate cache after search:
- Default: `auto_cleanup=True`
- Only final results are kept
- Manual cleanup: `cleanup_search_session()`

For more details, see `docs/MEMORY_OPTIMIZATION.md`

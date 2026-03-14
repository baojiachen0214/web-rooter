"""
MCP 工具定义 - 让 AI 可以调用网页爬取功能
"""
import asyncio
import json
from typing import Optional, Dict, Any, List
import logging

from agents.web_agent import WebAgent, AgentResponse
from core.search.engine import SearchEngine
from core.academic_search import AcademicSource, is_academic_query
from core.search.advanced import DeepSearchEngine, search_social_media, search_tech, search_commerce

try:
    from core.crawler import Crawler
except ModuleNotFoundError as exc:  # pragma: no cover - optional runtime dependency
    Crawler = None  # type: ignore[assignment]
    _CRAWLER_IMPORT_ERROR: Optional[Exception] = exc
else:
    _CRAWLER_IMPORT_ERROR = None

try:
    from core.parser import Parser
except ModuleNotFoundError as exc:  # pragma: no cover - optional runtime dependency
    Parser = None  # type: ignore[assignment]
    _PARSER_IMPORT_ERROR: Optional[Exception] = exc
else:
    _PARSER_IMPORT_ERROR = None

try:
    from core.browser import BrowserManager
except ModuleNotFoundError as exc:  # pragma: no cover - optional runtime dependency
    BrowserManager = None  # type: ignore[assignment]
    _BROWSER_IMPORT_ERROR: Optional[Exception] = exc
else:
    _BROWSER_IMPORT_ERROR = None

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class WebTools:
    """
    Web 工具集 - 可被 AI 调用的工具

    这些工具设计为可以被 AI agent 直接调用
    """

    def __init__(self):
        self._agent: Optional[WebAgent] = None
        self._initialized = False

    async def initialize(self):
        """初始化工具"""
        if not self._initialized:
            self._agent = WebAgent()
            await self._agent._init()
            self._initialized = True
            logger.info("WebTools initialized")

    async def close(self):
        """关闭工具"""
        if self._agent:
            await self._agent.close()
            self._initialized = False

    # ==================== 工具方法 ====================

    async def fetch(self, url: str) -> Dict[str, Any]:
        """
        获取网页内容

        Args:
            url: 要访问的 URL

        Returns:
            包含页面标题、内容和链接的字典
        """
        await self._ensure_initialized()
        result = await self._agent.visit(url)
        return result.to_dict()

    async def fetch_html(
        self,
        url: str,
        use_browser: bool = False,
        auto_fallback: bool = True,
        max_chars: int = 80000,
    ) -> Dict[str, Any]:
        """
        获取原始 HTML（推荐 AI 进行结构分析时使用）。
        """
        await self._ensure_initialized()
        result = await self._agent.fetch_html(
            url=url,
            use_browser=use_browser,
            auto_fallback=auto_fallback,
            max_chars=max_chars,
        )
        return result.to_dict()

    async def fetch_js(self, url: str, wait_for: Optional[str] = None) -> Dict[str, Any]:
        """
        使用浏览器获取网页（支持 JavaScript）

        Args:
            url: 要访问的 URL
            wait_for: 可选的 CSS 选择器，等待该元素出现

        Returns:
            包含渲染后内容的字典
        """
        await self._ensure_initialized()
        await self._agent._ensure_browser()
        result = await self._agent._browser.fetch(url, wait_for=wait_for)
        return {
            "success": result.error is None,
            "url": result.url,
            "title": result.title,
            "html": result.html[:50000],  # 限制大小
            "error": result.error,
        }

    async def search(self, query: str, url: Optional[str] = None) -> Dict[str, Any]:
        """
        在网页中搜索信息

        Args:
            query: 搜索关键词
            url: 可选的目标 URL

        Returns:
            搜索结果
        """
        await self._ensure_initialized()
        result = await self._agent.search(query, url)
        return result.to_dict()

    async def extract(self, url: str, target: str) -> Dict[str, Any]:
        """
        从网页提取特定信息

        Args:
            url: 目标 URL
            target: 要提取的信息描述

        Returns:
            提取的信息
        """
        await self._ensure_initialized()
        result = await self._agent.extract(url, target)
        return result.to_dict()

    async def crawl(
        self,
        start_url: str,
        max_pages: int = 10,
        max_depth: int = 3,
    ) -> Dict[str, Any]:
        """
        爬取网站

        Args:
            start_url: 起始 URL
            max_pages: 最大页面数
            max_depth: 最大深度

        Returns:
            爬取结果
        """
        await self._ensure_initialized()
        result = await self._agent.crawl(start_url, max_pages, max_depth)
        return result.to_dict()

    async def parse_html(self, html: str, url: str = "") -> Dict[str, Any]:
        """
        解析 HTML 内容

        Args:
            html: HTML 字符串
            url: 源 URL（用于解析相对链接）

        Returns:
            解析后的结构化数据
        """
        if Parser is None:
            raise RuntimeError(
                "HTML parser runtime is unavailable. Install optional dependencies from requirements.txt."
            ) from _PARSER_IMPORT_ERROR
        parser = Parser().parse(html, url)
        extracted = parser.extract()
        return extracted.to_dict()

    async def get_links(self, url: str, internal_only: bool = True) -> Dict[str, Any]:
        """
        获取页面所有链接

        Args:
            url: 目标 URL
            internal_only: 是否仅返回内部链接

        Returns:
            链接列表
        """
        await self._ensure_initialized()
        result = await self._agent.visit(url)
        if result.success and result.data:
            links = result.data.get("links", [])
            if internal_only:
                from urllib.parse import urlparse
                base_domain = urlparse(url).netloc
                links = [l for l in links if base_domain in urlparse(l["href"]).netloc]
            return {"success": True, "links": links, "count": len(links)}
        return {"success": False, "error": result.error}

    async def get_knowledge_base(self) -> Dict[str, Any]:
        """获取已访问页面的知识库"""
        await self._ensure_initialized()
        return {
            "success": True,
            "knowledge": self._agent.get_knowledge_base(),
            "visited_urls": self._agent.get_visited_urls(),
            "runtime_state": self._agent.get_runtime_state_stats(),
            "runtime_events": self._agent.get_runtime_events_stats(),
            "runtime_pressure": self._agent.get_runtime_pressure_stats(),
            "artifact_graph": self._agent.get_artifact_graph_stats(),
            "budget_telemetry": self._agent.get_budget_telemetry_snapshot(refresh=False),
        }

    async def web_search(self, query: str, num_results: int = 10) -> Dict[str, Any]:
        """
        互联网搜索（多引擎）

        Args:
            query: 搜索关键词
            num_results: 结果数量

        Returns:
            搜索结果
        """
        await self._ensure_initialized()
        result = await self._agent.search_internet(query, num_results=num_results)
        return result.to_dict()

    async def web_orchestrate(
        self,
        task: str,
        html_first: bool = True,
        top_results: int = 5,
        use_browser: bool = False,
        crawl_assist: bool = False,
        crawl_pages: int = 2,
        strict: bool = False,
    ) -> Dict[str, Any]:
        """
        AI 默认入口（推荐）：
        workflow 编排优先 + HTML-first 分析优先，爬取作为辅助。
        """
        await self._ensure_initialized()
        result = await self._agent.orchestrate_task(
            task=task,
            html_first=html_first,
            top_results=top_results,
            use_browser=use_browser,
            crawl_assist=crawl_assist,
            crawl_pages=crawl_pages,
            strict=strict,
        )
        return result.to_dict()

    async def web_search_combined(
        self,
        query: str,
        num_results: int = 20,
        crawl_top: int = 3,
    ) -> Dict[str, Any]:
        """
        互联网搜索并爬取内容

        Args:
            query: 搜索关键词
            num_results: 搜索结果数量
            crawl_top: 爬取前 N 个结果

        Returns:
            搜索结果和爬取内容
        """
        await self._ensure_initialized()
        result = await self._agent.search_internet(
            query,
            num_results=num_results,
            auto_crawl=True,
            crawl_pages=crawl_top,
        )
        return result.to_dict()

    async def web_research(self, topic: str, max_pages: int = 10) -> Dict[str, Any]:
        """
        深度研究主题

        Args:
            topic: 研究主题
            max_pages: 最大爬取页面数

        Returns:
            研究结果
        """
        await self._ensure_initialized()
        result = await self._agent.research_topic(topic, max_pages=max_pages)
        return result.to_dict()

    async def web_search_academic(
        self,
        query: str,
        num_results: int = 10,
        include_code: bool = True,
        fetch_abstracts: bool = True,
        sources: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        学术搜索 - 论文和代码项目

        Args:
            query: 搜索关键词
            num_results: 结果数量
            include_code: 是否包含代码项目
            fetch_abstracts: 是否获取论文摘要
            sources: 指定来源（arxiv/google_scholar/semantic_scholar/pubmed/ieee/cnki/wanfang/paper_with_code/github/gitee）

        Returns:
            学术搜索结果
        """
        await self._ensure_initialized()
        normalized_sources = None
        if sources:
            source_map = {
                "arxiv": AcademicSource.ARXIV,
                "google_scholar": AcademicSource.GOOGLE_SCHOLAR,
                "scholar": AcademicSource.GOOGLE_SCHOLAR,
                "semantic_scholar": AcademicSource.SEMANTIC_SCHOLAR,
                "semantic": AcademicSource.SEMANTIC_SCHOLAR,
                "pubmed": AcademicSource.PUBMED,
                "ieee": AcademicSource.IEEE,
                "cnki": AcademicSource.CNKI,
                "wanfang": AcademicSource.WANFANG,
                "paper_with_code": AcademicSource.PAPER_WITH_CODE,
                "pwc": AcademicSource.PAPER_WITH_CODE,
                "github": AcademicSource.GITHUB,
                "gitee": AcademicSource.GITEE,
            }
            normalized_sources = []
            for source in sources:
                enum_value = source_map.get(str(source or "").strip().lower())
                if enum_value and enum_value not in normalized_sources:
                    normalized_sources.append(enum_value)

        result = await self._agent.search_academic(
            query,
            num_results=num_results,
            include_code=include_code,
            fetch_abstracts=fetch_abstracts,
            sources=normalized_sources,
        )
        return result.to_dict()

    async def web_search_site(
        self,
        url: str,
        query: str,
        use_browser: bool = True,
    ) -> Dict[str, Any]:
        """
        站内搜索 - 在网站内部搜索框提交查询

        Args:
            url: 网站 URL
            query: 搜索关键词
            use_browser: 是否使用浏览器

        Returns:
            搜索结果
        """
        await self._ensure_initialized()
        result = await self._agent.search_with_form(
            url, query, use_browser=use_browser
        )
        return result.to_dict()

    async def web_deep_search(
        self,
        query: str,
        num_results: int = 20,
        use_english: bool = True,
        crawl_top: int = 5,
        channel_profiles: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        深度搜索 - 多引擎并行，支持中英文

        Args:
            query: 搜索关键词
            num_results: 每个引擎的结果数量
            use_english: 是否同时使用英文搜索
            crawl_top: 爬取前 N 个结果
            channel_profiles: 渠道档案（news/platforms/commerce）

        Returns:
            深度搜索结果
        """
        deep_search = DeepSearchEngine()
        try:
            return await deep_search.deep_search(
                query,
                num_results=num_results,
                use_english=use_english,
                crawl_top=crawl_top,
                channel_profiles=channel_profiles,
            )
        finally:
            await deep_search.close()

    async def web_mindsearch(
        self,
        query: str,
        max_turns: int = 3,
        max_branches: int = 4,
        num_results: int = 8,
        crawl_top: int = 1,
        use_english: bool = False,
        channel_profiles: Optional[List[str]] = None,
        planner_name: Optional[str] = None,
        strict_expand: Optional[bool] = None,
    ) -> Dict[str, Any]:
        """
        MindSearch 风格研究（图搜索 + 深度抓取 + 引用）。
        """
        await self._ensure_initialized()
        result = await self._agent.mindsearch_research(
            query=query,
            max_turns=max_turns,
            max_branches=max_branches,
            num_results=num_results,
            crawl_top=crawl_top,
            use_english=use_english,
            channel_profiles=channel_profiles,
            planner_name=planner_name,
            strict_expand=strict_expand,
        )
        return result.to_dict()

    async def web_context_snapshot(
        self,
        limit: int = 20,
        event_type: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        获取全局深度抓取上下文快照。
        """
        await self._ensure_initialized()
        snapshot = self._agent.get_global_context_snapshot(limit=limit, event_type=event_type)
        return {
            "success": True,
            "context": snapshot,
        }

    async def web_artifact_snapshot(
        self,
        node_limit: int = 80,
        edge_limit: int = 200,
        node_kind: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        获取 runtime artifact graph 快照。
        """
        await self._ensure_initialized()
        snapshot = self._agent.get_artifact_graph_snapshot(
            node_limit=node_limit,
            edge_limit=edge_limit,
            node_kind=node_kind,
        )
        return {
            "success": True,
            "artifact_graph": snapshot,
        }

    async def web_runtime_events(
        self,
        limit: int = 50,
        event_type: Optional[str] = None,
        source: Optional[str] = None,
        since_seq: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        获取 bounded runtime event stream 快照。
        """
        await self._ensure_initialized()
        snapshot = self._agent.get_runtime_events_snapshot(
            limit=limit,
            event_type=event_type,
            source=source,
            since_seq=since_seq,
        )
        return {
            "success": True,
            "runtime_events": snapshot,
        }

    async def web_runtime_pressure(
        self,
        refresh: bool = True,
    ) -> Dict[str, Any]:
        """
        获取运行时压力快照与自适应限制。
        """
        await self._ensure_initialized()
        snapshot = self._agent.get_runtime_pressure_snapshot(refresh=refresh)
        return {
            "success": True,
            "runtime_pressure": snapshot,
        }

    async def web_budget_telemetry(
        self,
        refresh: bool = True,
    ) -> Dict[str, Any]:
        """
        获取统一预算健康度快照（state/events/artifact/pressure）。
        """
        await self._ensure_initialized()
        snapshot = self._agent.get_budget_telemetry_snapshot(refresh=refresh)
        return {
            "success": True,
            "budget_telemetry": snapshot,
        }

    async def web_postprocessors(
        self,
        specs: Optional[List[str]] = None,
        force: bool = False,
    ) -> Dict[str, Any]:
        """
        加载/查看后处理扩展。
        """
        await self._ensure_initialized()
        data = self._agent.register_post_processors(specs=specs, force=force)
        return {
            "success": True,
            **data,
        }

    async def web_planners(
        self,
        specs: Optional[List[str]] = None,
        force: bool = False,
    ) -> Dict[str, Any]:
        """
        加载/查看 MindSearch planner 扩展。
        """
        await self._ensure_initialized()
        data = self._agent.register_research_planners(specs=specs, force=force)
        return {
            "success": True,
            **data,
        }

    async def web_challenge_profiles(self) -> Dict[str, Any]:
        """
        查看 challenge workflow profiles。
        """
        await self._ensure_initialized()
        data = self._agent.get_challenge_profiles()
        return {
            "success": True,
            **data,
        }

    async def web_auth_profiles(self) -> Dict[str, Any]:
        """
        查看本地登录态 profile 列表。
        """
        await self._ensure_initialized()
        data = self._agent.get_auth_profiles()
        return {
            "success": True,
            **data,
        }

    async def web_auth_hint(self, url: str) -> Dict[str, Any]:
        """
        根据 URL 返回登录态配置提示。
        """
        await self._ensure_initialized()
        data = self._agent.get_auth_hint(url)
        return {
            "success": True,
            **data,
        }

    async def web_auth_template(
        self,
        output_path: Optional[str] = None,
        force: bool = False,
    ) -> Dict[str, Any]:
        """
        导出本地登录态模板 JSON。
        """
        await self._ensure_initialized()
        return self._agent.export_auth_template(output_path=output_path, force=force)

    async def web_workflow_schema(self) -> Dict[str, Any]:
        """Return workflow schema so AI can decide crawl steps dynamically."""
        await self._ensure_initialized()
        data = self._agent.get_workflow_schema()
        return {
            "success": True,
            **data,
        }

    async def web_workflow_template(
        self,
        output_path: Optional[str] = None,
        scenario: str = "social_comments",
        force: bool = False,
    ) -> Dict[str, Any]:
        """Export workflow template JSON for local customization."""
        await self._ensure_initialized()
        return self._agent.export_workflow_template(
            output_path=output_path,
            scenario=scenario,
            force=force,
        )

    async def web_workflow_run(
        self,
        spec: Dict[str, Any],
        variables: Optional[Dict[str, Any]] = None,
        strict: bool = False,
    ) -> Dict[str, Any]:
        """Run declarative workflow spec."""
        await self._ensure_initialized()
        response = await self._agent.run_workflow_spec(
            spec=spec,
            variable_overrides=variables,
            strict=strict,
        )
        return response.to_dict()

    async def web_search_social(
        self,
        query: str,
        platforms: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        社交媒体搜索

        Args:
            query: 搜索关键词
            platforms: 指定平台（默认全部）
                     支持：xiaohongshu, zhihu, tieba, douyin, bilibili, weibo, reddit, twitter

        Returns:
            社交媒体搜索结果
        """
        return await search_social_media(query, platforms)

    async def web_search_tech(
        self,
        query: str,
        sources: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        技术社区搜索

        Args:
            query: 搜索关键词
            sources: 指定来源（默认全部）
                    支持：github, stackoverflow, medium, hackernews

        Returns:
            技术社区搜索结果
        """
        return await search_tech(query, sources)

    async def web_search_commerce(
        self,
        query: str,
        platforms: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        电商和本地生活平台搜索

        Args:
            query: 搜索关键词
            platforms: 指定平台（默认全部）
                     支持：taobao, jd, pinduoduo, meituan

        Returns:
            电商平台搜索结果
        """
        return await search_commerce(query, platforms)

    async def _ensure_initialized(self):
        """确保已初始化"""
        if not self._initialized:
            await self.initialize()


# ==================== MCP 服务器设置 ====================

async def setup_mcp_server():
    """
    设置 MCP 服务器

    这将注册所有可用的工具
    """
    from mcp.server import Server
    from mcp.server.stdio import stdio_server
    from mcp.types import Tool, TextContent

    web_tools = WebTools()
    await web_tools.initialize()

    server = Server("web-rooter")

    @server.list_tools()
    async def list_tools() -> list[Tool]:
        return [
            Tool(
                name="web_orchestrate",
                description="RECOMMENDED default for AI: workflow-first orchestration with HTML-first analysis; low-level tools are auxiliary",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "task": {"type": "string", "description": "Natural-language task/goal"},
                        "html_first": {"type": "boolean", "description": "Read raw HTML first before deeper crawl", "default": True},
                        "top_results": {"type": "integer", "description": "Top pages to inspect", "default": 5},
                        "use_browser": {"type": "boolean", "description": "Prefer browser rendering for dynamic pages", "default": False},
                        "crawl_assist": {"type": "boolean", "description": "Enable crawl as auxiliary step", "default": False},
                        "crawl_pages": {"type": "integer", "description": "Auxiliary crawl page budget", "default": 2},
                        "strict": {"type": "boolean", "description": "Fail fast on step errors", "default": False}
                    },
                    "required": ["task"],
                },
            ),
            Tool(
                name="web_fetch_html",
                description="Low-level helper: fetch raw HTML for AI DOM/structure analysis",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "url": {"type": "string", "description": "Target URL"},
                        "use_browser": {"type": "boolean", "description": "Use browser rendering", "default": False},
                        "auto_fallback": {"type": "boolean", "description": "Fallback to browser if HTTP fails", "default": True},
                        "max_chars": {"type": "integer", "description": "Max HTML chars returned", "default": 80000}
                    },
                    "required": ["url"],
                },
            ),
            Tool(
                name="web_fetch",
                description="Low-level helper: fetch parsed page summary from a URL",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "url": {"type": "string", "description": "The URL to fetch"}
                    },
                    "required": ["url"],
                },
            ),
            Tool(
                name="web_fetch_js",
                description="Low-level helper: fetch page via browser for JavaScript-rendered pages",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "url": {"type": "string", "description": "The URL to fetch"},
                        "wait_for": {"type": "string", "description": "CSS selector to wait for"}
                    },
                    "required": ["url"],
                },
            ),
            Tool(
                name="web_search",
                description="Search for information in fetched content (already visited pages)",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Search query"},
                        "url": {"type": "string", "description": "Optional URL to search in"}
                    },
                    "required": ["query"],
                },
            ),
            Tool(
                name="web_search_internet",
                description="Search the internet across multiple search engines (Bing, Baidu, Google, etc.)",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Search query"},
                        "num_results": {"type": "integer", "description": "Number of results", "default": 10}
                    },
                    "required": ["query"],
                },
            ),
            Tool(
                name="web_search_combined",
                description="Search internet and crawl top results for detailed content",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Search query"},
                        "num_results": {"type": "integer", "description": "Number of search results", "default": 20},
                        "crawl_top": {"type": "integer", "description": "Number of top results to crawl", "default": 3}
                    },
                    "required": ["query"],
                },
            ),
            Tool(
                name="web_research",
                description="Deep research on a topic - multiple searches + crawling",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "topic": {"type": "string", "description": "Research topic"},
                        "max_pages": {"type": "integer", "description": "Maximum pages to crawl", "default": 10}
                    },
                    "required": ["topic"],
                },
            ),
            Tool(
                name="web_search_academic",
                description="Search academic papers and code projects with citation-ready metadata (arXiv, Semantic Scholar, PubMed, GitHub, etc.)",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Academic search query"},
                        "num_results": {"type": "integer", "description": "Number of results", "default": 10},
                        "include_code": {"type": "boolean", "description": "Include code projects from GitHub/Gitee", "default": True},
                        "fetch_abstracts": {"type": "boolean", "description": "Fetch paper abstracts", "default": True},
                        "sources": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Specific academic sources (arxiv, google_scholar, semantic_scholar, pubmed, ieee, cnki, wanfang, paper_with_code, github, gitee)"
                        },
                    },
                    "required": ["query"],
                },
            ),
            Tool(
                name="web_search_site",
                description="Search within a specific website using its internal search form",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "url": {"type": "string", "description": "Website URL to search in"},
                        "query": {"type": "string", "description": "Search query"},
                        "use_browser": {"type": "boolean", "description": "Use browser for JavaScript forms", "default": True}
                    },
                    "required": ["url", "query"],
                },
            ),
            Tool(
                name="web_deep_search",
                description="Deep search across multiple engines (Google, Bing, Baidu, DuckDuckGo) with parallel execution and multi-language support",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Search query"},
                        "num_results": {"type": "integer", "description": "Results per engine", "default": 20},
                        "use_english": {"type": "boolean", "description": "Also search with English query", "default": True},
                        "crawl_top": {"type": "integer", "description": "Crawl top N results", "default": 5},
                        "channel_profiles": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Channel profiles to expand query via site:domain (supported: news, platforms, commerce)"
                        },
                    },
                    "required": ["query"],
                },
            ),
            Tool(
                name="web_mindsearch",
                description="MindSearch-style graph research with planning, multi-node deep search, and citation graph output",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Research query"},
                        "max_turns": {"type": "integer", "description": "Max graph depth/turns", "default": 3},
                        "max_branches": {"type": "integer", "description": "Max branches per expansion", "default": 4},
                        "num_results": {"type": "integer", "description": "Results per node", "default": 8},
                        "crawl_top": {"type": "integer", "description": "Crawl top N per node", "default": 1},
                        "use_english": {"type": "boolean", "description": "Enable English query variants", "default": False},
                        "channel_profiles": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Optional channel profiles (news/platforms/commerce)"
                        },
                        "planner_name": {"type": "string", "description": "Optional planner name to use"},
                        "strict_expand": {"type": "boolean", "description": "Force follow-up expansion for completed nodes"},
                    },
                    "required": ["query"],
                },
            ),
            Tool(
                name="web_context_snapshot",
                description="Get global deep-crawl context snapshot across commands/sessions in current process",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "limit": {"type": "integer", "description": "Max events to return", "default": 20},
                        "event_type": {"type": "string", "description": "Optional event type filter"},
                    },
                },
            ),
            Tool(
                name="web_artifact_snapshot",
                description="Get bounded runtime artifact graph snapshot (pages, links, fetch relations)",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "node_limit": {"type": "integer", "description": "Max nodes to return", "default": 80},
                        "edge_limit": {"type": "integer", "description": "Max edges to return", "default": 200},
                        "node_kind": {"type": "string", "description": "Optional node kind filter (page/url/domain/request/session)"},
                    },
                },
            ),
            Tool(
                name="web_runtime_events",
                description="Get bounded runtime event stream snapshot (visit/fallback/fetch lifecycle)",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "limit": {"type": "integer", "description": "Max events to return", "default": 50},
                        "event_type": {"type": "string", "description": "Optional event type filter"},
                        "source": {"type": "string", "description": "Optional source filter"},
                        "since_seq": {"type": "integer", "description": "Return events with seq greater than this cursor"},
                    },
                },
            ),
            Tool(
                name="web_runtime_pressure",
                description="Get adaptive runtime pressure snapshot and current degrade limits",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "refresh": {"type": "boolean", "description": "Re-evaluate memory/error pressure before returning", "default": True},
                    },
                },
            ),
            Tool(
                name="web_budget_telemetry",
                description="Get unified runtime budget telemetry (state/events/artifact/pressure) with health score",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "refresh": {"type": "boolean", "description": "Re-evaluate runtime pressure before collecting telemetry", "default": True},
                    },
                },
            ),
            Tool(
                name="web_postprocessors",
                description="List/load post-processors for custom data handling after crawl/search",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "specs": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Processor specs: module:object or /path/file.py:object"
                        },
                        "force": {"type": "boolean", "description": "Force reload specs", "default": False},
                    },
                },
            ),
            Tool(
                name="web_planners",
                description="List/load MindSearch planners (module:path loaders) for custom planning strategy",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "specs": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Planner specs: module:object or /path/file.py:object"
                        },
                        "force": {"type": "boolean", "description": "Force reload specs", "default": False},
                    },
                },
            ),
            Tool(
                name="web_challenge_profiles",
                description="List challenge workflow profiles used for anti-bot pages",
                inputSchema={
                    "type": "object",
                    "properties": {},
                },
            ),
            Tool(
                name="web_auth_profiles",
                description="List local auth/login profiles used for login-required websites",
                inputSchema={
                    "type": "object",
                    "properties": {},
                },
            ),
            Tool(
                name="web_auth_hint",
                description="Show auth profile match/hint for a target URL",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "url": {"type": "string", "description": "Target URL"}
                    },
                    "required": ["url"],
                },
            ),
            Tool(
                name="web_auth_template",
                description="Export local auth profile JSON template for user-filled credentials",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "output_path": {"type": "string", "description": "Optional output path"},
                        "force": {"type": "boolean", "description": "Overwrite if exists", "default": False}
                    },
                },
            ),
            Tool(
                name="web_workflow_schema",
                description="Get declarative workflow schema so AI can compose crawl/search steps dynamically",
                inputSchema={
                    "type": "object",
                    "properties": {},
                },
            ),
            Tool(
                name="web_workflow_template",
                description="Export workflow template JSON for local customization (social_comments / academic_relations)",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "output_path": {"type": "string", "description": "Optional output path"},
                        "scenario": {"type": "string", "description": "Template scenario", "default": "social_comments"},
                        "force": {"type": "boolean", "description": "Overwrite if exists", "default": False}
                    },
                },
            ),
            Tool(
                name="web_workflow_run",
                description="Run a declarative workflow spec (JSON object) with optional variable overrides",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "spec": {"type": "object", "description": "Workflow JSON spec"},
                        "variables": {"type": "object", "description": "Optional variable overrides"},
                        "strict": {"type": "boolean", "description": "Fail fast on any step failure", "default": False}
                    },
                    "required": ["spec"],
                },
            ),
            Tool(
                name="web_search_social",
                description="Search social media platforms (Xiaohongshu, Zhihu, Tieba, Douyin, Bilibili, Weibo, Reddit, Twitter)",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Search query"},
                        "platforms": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Platforms to search (xiaohongshu, zhihu, tieba, douyin, bilibili, weibo, reddit, twitter)"
                        }
                    },
                    "required": ["query"],
                },
            ),
            Tool(
                name="web_search_tech",
                description="Search tech communities (GitHub, Stack Overflow, Medium, Hacker News)",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Search query"},
                        "sources": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Sources to search (github, stackoverflow, medium, hackernews)"
                        }
                    },
                    "required": ["query"],
                },
            ),
            Tool(
                name="web_search_commerce",
                description="Search shopping/life-service platforms (Taobao, JD, Pinduoduo, Meituan)",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Search query"},
                        "platforms": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Platforms to search (taobao, jd, pinduoduo, meituan)"
                        }
                    },
                    "required": ["query"],
                },
            ),
            Tool(
                name="web_extract",
                description="Extract specific information from a webpage",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "url": {"type": "string", "description": "The URL to extract from"},
                        "target": {"type": "string", "description": "Description of information to extract"}
                    },
                    "required": ["url", "target"],
                },
            ),
            Tool(
                name="web_crawl",
                description="Crawl a website starting from a URL",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "start_url": {"type": "string", "description": "Starting URL"},
                        "max_pages": {"type": "integer", "description": "Maximum pages to crawl", "default": 10},
                        "max_depth": {"type": "integer", "description": "Maximum depth to crawl", "default": 3}
                    },
                    "required": ["start_url"],
                },
            ),
            Tool(
                name="parse_html",
                description="Parse HTML content and extract structured data",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "html": {"type": "string", "description": "HTML content to parse"},
                        "url": {"type": "string", "description": "Source URL for resolving relative links"}
                    },
                    "required": ["html"],
                },
            ),
            Tool(
                name="get_links",
                description="Get all links from a webpage",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "url": {"type": "string", "description": "The URL to get links from"},
                        "internal_only": {"type": "boolean", "description": "Only return internal links", "default": True}
                    },
                    "required": ["url"],
                },
            ),
        ]

    @server.call_tool()
    async def call_tool(name: str, arguments: dict) -> list[TextContent]:
        try:
            result = None

            if name == "web_orchestrate":
                result = await web_tools.web_orchestrate(
                    arguments["task"],
                    html_first=arguments.get("html_first", True),
                    top_results=arguments.get("top_results", 5),
                    use_browser=arguments.get("use_browser", False),
                    crawl_assist=arguments.get("crawl_assist", False),
                    crawl_pages=arguments.get("crawl_pages", 2),
                    strict=arguments.get("strict", False),
                )
            elif name == "web_fetch_html":
                result = await web_tools.fetch_html(
                    arguments["url"],
                    use_browser=arguments.get("use_browser", False),
                    auto_fallback=arguments.get("auto_fallback", True),
                    max_chars=arguments.get("max_chars", 80000),
                )
            elif name == "web_fetch":
                result = await web_tools.fetch(arguments["url"])
            elif name == "web_fetch_js":
                result = await web_tools.fetch_js(
                    arguments["url"],
                    wait_for=arguments.get("wait_for")
                )
            elif name == "web_search":
                result = await web_tools.search(
                    arguments["query"],
                    url=arguments.get("url")
                )
            elif name == "web_extract":
                result = await web_tools.extract(
                    arguments["url"],
                    arguments["target"]
                )
            elif name == "web_crawl":
                result = await web_tools.crawl(
                    arguments["start_url"],
                    max_pages=arguments.get("max_pages", 10),
                    max_depth=arguments.get("max_depth", 3)
                )
            elif name == "parse_html":
                result = await web_tools.parse_html(
                    arguments["html"],
                    url=arguments.get("url", "")
                )
            elif name == "get_links":
                result = await web_tools.get_links(
                    arguments["url"],
                    internal_only=arguments.get("internal_only", True)
                )
            elif name == "web_search_internet":
                result = await web_tools.web_search(
                    arguments["query"],
                    num_results=arguments.get("num_results", 10)
                )
            elif name == "web_search_combined":
                result = await web_tools.web_search_combined(
                    arguments["query"],
                    num_results=arguments.get("num_results", 20),
                    crawl_top=arguments.get("crawl_top", 3)
                )
            elif name == "web_research":
                result = await web_tools.web_research(
                    arguments["topic"],
                    max_pages=arguments.get("max_pages", 10)
                )
            elif name == "web_search_academic":
                result = await web_tools.web_search_academic(
                    arguments["query"],
                    num_results=arguments.get("num_results", 10),
                    include_code=arguments.get("include_code", True),
                    fetch_abstracts=arguments.get("fetch_abstracts", True),
                    sources=arguments.get("sources"),
                )
            elif name == "web_search_site":
                result = await web_tools.web_search_site(
                    arguments["url"],
                    arguments["query"],
                    use_browser=arguments.get("use_browser", True)
                )
            elif name == "web_deep_search":
                result = await web_tools.web_deep_search(
                    arguments["query"],
                    num_results=arguments.get("num_results", 20),
                    use_english=arguments.get("use_english", True),
                    crawl_top=arguments.get("crawl_top", 5),
                    channel_profiles=arguments.get("channel_profiles"),
                )
            elif name == "web_mindsearch":
                result = await web_tools.web_mindsearch(
                    arguments["query"],
                    max_turns=arguments.get("max_turns", 3),
                    max_branches=arguments.get("max_branches", 4),
                    num_results=arguments.get("num_results", 8),
                    crawl_top=arguments.get("crawl_top", 1),
                    use_english=arguments.get("use_english", False),
                    channel_profiles=arguments.get("channel_profiles"),
                    planner_name=arguments.get("planner_name"),
                    strict_expand=arguments.get("strict_expand"),
                )
            elif name == "web_context_snapshot":
                result = await web_tools.web_context_snapshot(
                    limit=arguments.get("limit", 20),
                    event_type=arguments.get("event_type"),
                )
            elif name == "web_artifact_snapshot":
                result = await web_tools.web_artifact_snapshot(
                    node_limit=arguments.get("node_limit", 80),
                    edge_limit=arguments.get("edge_limit", 200),
                    node_kind=arguments.get("node_kind"),
                )
            elif name == "web_runtime_events":
                result = await web_tools.web_runtime_events(
                    limit=arguments.get("limit", 50),
                    event_type=arguments.get("event_type"),
                    source=arguments.get("source"),
                    since_seq=arguments.get("since_seq"),
                )
            elif name == "web_runtime_pressure":
                result = await web_tools.web_runtime_pressure(
                    refresh=arguments.get("refresh", True),
                )
            elif name == "web_budget_telemetry":
                result = await web_tools.web_budget_telemetry(
                    refresh=arguments.get("refresh", True),
                )
            elif name == "web_postprocessors":
                result = await web_tools.web_postprocessors(
                    specs=arguments.get("specs"),
                    force=arguments.get("force", False),
                )
            elif name == "web_planners":
                result = await web_tools.web_planners(
                    specs=arguments.get("specs"),
                    force=arguments.get("force", False),
                )
            elif name == "web_challenge_profiles":
                result = await web_tools.web_challenge_profiles()
            elif name == "web_auth_profiles":
                result = await web_tools.web_auth_profiles()
            elif name == "web_auth_hint":
                result = await web_tools.web_auth_hint(arguments["url"])
            elif name == "web_auth_template":
                result = await web_tools.web_auth_template(
                    output_path=arguments.get("output_path"),
                    force=arguments.get("force", False),
                )
            elif name == "web_workflow_schema":
                result = await web_tools.web_workflow_schema()
            elif name == "web_workflow_template":
                result = await web_tools.web_workflow_template(
                    output_path=arguments.get("output_path"),
                    scenario=arguments.get("scenario", "social_comments"),
                    force=arguments.get("force", False),
                )
            elif name == "web_workflow_run":
                result = await web_tools.web_workflow_run(
                    spec=arguments["spec"],
                    variables=arguments.get("variables"),
                    strict=arguments.get("strict", False),
                )
            elif name == "web_search_social":
                result = await web_tools.web_search_social(
                    arguments["query"],
                    platforms=arguments.get("platforms"),
                )
            elif name == "web_search_tech":
                result = await web_tools.web_search_tech(
                    arguments["query"],
                    sources=arguments.get("sources"),
                )
            elif name == "web_search_commerce":
                result = await web_tools.web_search_commerce(
                    arguments["query"],
                    platforms=arguments.get("platforms"),
                )

            if result:
                return [TextContent(
                    type="text",
                    text=json.dumps(result, ensure_ascii=False, indent=2)
                )]
            else:
                return [TextContent(type="text", text="No result")]

        except Exception as e:
            logger.exception(f"Error calling tool {name}")
            return [TextContent(
                type="text",
                text=json.dumps({"error": str(e)}, ensure_ascii=False)
            )]

    return server, web_tools


async def run_mcp_server():
    """运行 MCP 服务器"""
    from mcp.server.stdio import stdio_server

    server, web_tools = await setup_mcp_server()

    print("Web-Rooter MCP Server starting...", flush=True)

    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options(),
        )

    await web_tools.close()


if __name__ == "__main__":
    asyncio.run(run_mcp_server())

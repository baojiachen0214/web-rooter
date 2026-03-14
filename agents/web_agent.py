"""
AI Web Agent - 自然语言网页访问接口
"""
import asyncio
import json
import os
import re
from copy import deepcopy
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, List, Dict, Any, Callable, TYPE_CHECKING
from datetime import datetime
from urllib.parse import urlparse, urlunparse
import logging

from core.search.engine import (
    SearchEngine,
    SearchResult,
    MultiSearchEngine,
)
from core.academic_search import (
    AcademicSource,
    PaperResult,
    CodeProjectResult,
    AcademicSearchEngine,
    is_academic_query,
    academic_search,
    code_search,
)
from core.form_search import (
    FormFiller,
    SearchFormResult,
    auto_search,
)
from core.citation import (
    build_web_citations,
    build_paper_citations,
    build_code_citations,
    build_comparison_summary,
    format_reference_block,
)
from core.search.mindsearch_pipeline import MindSearchPipeline
from core.search.research_planner import get_research_planner_registry
from core.global_context import get_global_deep_context
from core.postprocess import get_post_processor_registry
from core.challenge_workflow import get_challenge_workflow_runner
from core.auth_profiles import get_auth_profile_registry
from core.workflow import (
    WorkflowRunner,
    build_workflow_template,
    get_workflow_schema,
    available_workflow_templates,
)
from core.skills import get_skill_registry, SkillProfile
from core.command_ir import (
    build_command_ir,
    lint_command_ir,
    summarize_lint,
    has_lint_errors,
)
from core.trace_distill import distill_workflow_trace
from core.runtime_state import PageSnapshot
from core.research_kernel import ResearchKernel
from core.metrics import set_budget_telemetry_provider, clear_budget_telemetry_provider
from core.cli_entry import build_cli_command
from config import crawler_config

if TYPE_CHECKING:
    from core.crawler import CrawlResult
    from core.browser import BrowserResult

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class AgentResponse:
    """Agent 响应"""
    success: bool
    content: str
    data: Optional[Dict[str, Any]] = None
    urls: List[str] = field(default_factory=list)
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "content": self.content,
            "data": self.data,
            "urls": self.urls,
            "error": self.error,
            "metadata": self.metadata,
        }

class WebAgent:
    """
    AI Web Agent

    提供自然语言接口来访问和爬取网页
    """

    def __init__(self):
        self._kernel: Optional[ResearchKernel] = None
        self._browser = None  # backward-compatible access for MCP helper paths
        self._search_engine: Optional[MultiSearchEngine] = None
        self._academic_engine: Optional[AcademicSearchEngine] = None
        self._form_filler: Optional[FormFiller] = None

    async def __aenter__(self) -> "WebAgent":
        await self._init()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()

    async def _init(self):
        """初始化"""
        if self._kernel is not None:
            return
        self._kernel = ResearchKernel()
        await self._kernel.start()
        self._browser = None  # 延迟初始化
        set_budget_telemetry_provider(
            lambda: self.get_budget_telemetry_snapshot(refresh=False)
        )

    async def _ensure_browser(self):
        """确保浏览器已初始化"""
        if self._kernel is None:
            await self._init()
        assert self._kernel is not None
        self._browser = await self._kernel.ensure_browser()

    async def close(self):
        """关闭"""
        if self._kernel:
            await self._kernel.close()
        if self._search_engine:
            await self._search_engine.close()
        if self._academic_engine:
            await self._academic_engine.close()
        if self._form_filler:
            await self._form_filler.close()
        self._kernel = None
        self._browser = None
        self._search_engine = None
        self._academic_engine = None
        self._form_filler = None
        clear_budget_telemetry_provider()

    # ==================== 核心方法 ====================

    async def visit(self, url: str, use_browser: bool = False, auto_fallback: bool = True) -> AgentResponse:
        """
        访问网页

        Args:
            url: 目标 URL
            use_browser: 是否使用浏览器（用于 JS 渲染页面）
            auto_fallback: HTTP 失败时是否自动切换浏览器兜底

        Returns:
            AgentResponse: 访问结果
        """
        if self._kernel is None:
            await self._init()
        assert self._kernel is not None

        try:
            result = await self._kernel.visit(url, use_browser=use_browser, auto_fallback=auto_fallback)
            if not result.success or not result.payload:
                normalized_url = self._kernel.normalize_url(url)
                return AgentResponse(
                    success=False,
                    content=f"访问失败：{normalized_url}",
                    error=result.error,
                    metadata=result.metadata,
                )
            return self._build_visit_response(
                payload=result.payload,
                metadata=result.metadata,
            )

        except Exception as e:
            logger.error("Error visiting %s: %s", url, e)
            return AgentResponse(
                success=False,
                content=f"访问失败：{url}",
                error=str(e),
            )

    async def fetch_html(
        self,
        url: str,
        use_browser: bool = False,
        auto_fallback: bool = True,
        max_chars: int = 80000,
    ) -> AgentResponse:
        """
        获取原始 HTML（面向 AI 的 HTML-first 分析）。

        与 visit 的区别：
        - visit 偏向结构化抽取与文本摘要
        - fetch_html 直接返回 HTML 片段，便于 AI 自行分析 DOM 结构
        """
        if self._kernel is None:
            await self._init()
        assert self._kernel is not None

        try:
            result = await self._kernel.fetch_html(
                url=url,
                use_browser=use_browser,
                auto_fallback=auto_fallback,
                max_chars=max_chars,
            )
            if not result.success or not result.data:
                normalized_url = self._kernel.normalize_url(url)
                return AgentResponse(
                    success=False,
                    content=f"HTML 获取失败：{normalized_url}",
                    error=result.error,
                    metadata=result.metadata,
                )
            return AgentResponse(
                success=True,
                content=(
                    f"已获取 HTML：{result.data.get('title') or result.data.get('url')}\n"
                    f"模式：{result.data.get('fetch_mode')}\n"
                    f"长度：{result.data.get('html_chars')} 字符"
                ),
                data=result.data,
                urls=[
                    item.get("href")
                    for item in (result.data.get("links", []) if isinstance(result.data.get("links"), list) else [])
                    if isinstance(item, dict) and item.get("href")
                ][:30],
                metadata=result.metadata,
            )
        except Exception as e:
            logger.error("Error fetching html from %s: %s", url, e)
            return AgentResponse(
                success=False,
                content=f"HTML 获取失败：{url}",
                error=str(e),
            )

    async def search(self, query: str, url: Optional[str] = None) -> AgentResponse:
        """
        在已访问的页面或指定页面中搜索信息

        Args:
            query: 搜索关键词
            url: 可选的目标 URL

        Returns:
            AgentResponse: 搜索结果
        """
        results = []

        # 如果指定了 URL，先访问
        if self._kernel is None:
            await self._init()
        assert self._kernel is not None

        if url and not self._kernel.has_page(url):
            visit_result = await self.visit(url)
            if not visit_result.success:
                return visit_result

        # 在所有已知内容中搜索
        for knowledge in self._kernel.iter_pages():
            if query.lower() in knowledge.content.lower():
                # 找到相关段落
                content_snippets = self._find_relevant_snippets(
                    knowledge.content, query, num_snippets=3
                )
                results.append({
                    "url": knowledge.url,
                    "title": knowledge.title,
                    "snippets": content_snippets,
                })

        if results:
            content = self._format_search_in_knowledge_results(results)
            return AgentResponse(
                success=True,
                content=content,
                data={"results": results},
                urls=[r["url"] for r in results],
            )
        else:
            return AgentResponse(
                success=False,
                content=f"未找到关于 '{query}' 的信息",
            )

    async def extract(self, url: str, target_info: str) -> AgentResponse:
        """
        从网页提取特定信息

        Args:
            url: 目标 URL
            target_info: 要提取的信息描述

        Returns:
            AgentResponse: 提取结果
        """
        # 访问页面
        visit_result = await self.visit(url)
        if not visit_result.success:
            return visit_result

        if self._kernel is None:
            await self._init()
        assert self._kernel is not None

        knowledge = self._kernel.get_page(url)
        if not knowledge:
            return AgentResponse(
                success=False,
                content="页面内容不可用",
            )

        # 智能提取
        extracted = self._intelligent_extract(knowledge, target_info)

        return AgentResponse(
            success=True,
            content=f"从 {knowledge.title} 提取的信息:\n\n{extracted}",
            data={"extracted": extracted},
        )

    async def crawl(
        self,
        start_url: str,
        max_pages: int = 10,
        max_depth: int = 3,
        pattern: Optional[str] = None,
        allow_external: bool = False,
        allow_subdomains: bool = True,
    ) -> AgentResponse:
        """
        深度爬取网站

        Args:
            start_url: 起始 URL
            max_pages: 最大页面数
            max_depth: 最大深度
            pattern: URL 匹配模式（正则）
            allow_external: 是否允许跨站点爬取
            allow_subdomains: 禁止跨站时是否允许子域名

        Returns:
            AgentResponse: 爬取结果
        """
        normalized_start = self._normalize_crawl_url(start_url)
        if not normalized_start:
            return AgentResponse(
                success=False,
                content=f"无效起始 URL: {start_url}",
            )

        url_pattern = re.compile(pattern) if pattern else None
        crawled: List[Dict[str, Any]] = []
        to_visit = [(normalized_start, 0)]  # (url, depth)
        queued = {normalized_start}
        visited = set()
        base_host = (urlparse(normalized_start).hostname or "").lower()

        while to_visit and len(crawled) < max_pages:
            url, depth = to_visit.pop(0)
            queued.discard(url)

            if depth > max_depth or url in visited:
                continue
            visited.add(url)

            # 访问页面
            result = await self.visit(url)
            if result.success:
                page_data = {
                    "url": url,
                    "title": result.data["title"] if result.data else "",
                    "depth": depth,
                    "fetch_mode": result.metadata.get("fetch_mode"),
                }
                crawled.append(page_data)
                logger.info(f"Crawled [{depth}]: {url}")

                # 添加新链接
                if result.urls:
                    for link_url in result.urls:
                        normalized_link = self._normalize_crawl_url(link_url)
                        if not normalized_link:
                            continue
                        if not self._is_crawlable_url(
                            normalized_link,
                            base_host=base_host,
                            allow_external=allow_external,
                            allow_subdomains=allow_subdomains,
                        ):
                            continue
                        if url_pattern is not None and not url_pattern.match(normalized_link):
                            continue
                        if normalized_link in visited or normalized_link in queued:
                            continue

                        to_visit.append((normalized_link, depth + 1))
                        queued.add(normalized_link)

        return AgentResponse(
            success=True,
            content=f"爬取完成，共 {len(crawled)} 个页面",
            data={"pages": crawled},
            urls=[c["url"] for c in crawled],
        )

    @staticmethod
    def _normalize_crawl_url(url: str) -> Optional[str]:
        """规范化 URL，去除 fragment，过滤明显不可爬取链接。"""
        if not url:
            return None
        if not url.startswith(("http://", "https://")):
            if url.startswith("www."):
                url = "https://" + url
            else:
                return None

        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            return None

        # 过滤常见二进制/静态资源
        static_ext = {
            ".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg", ".ico",
            ".pdf", ".zip", ".rar", ".7z", ".tar", ".gz",
            ".mp3", ".wav", ".mp4", ".avi", ".mov", ".mkv",
            ".css", ".js", ".woff", ".woff2", ".ttf", ".eot",
        }
        path_lower = parsed.path.lower()
        if any(path_lower.endswith(ext) for ext in static_ext):
            return None

        normalized = parsed._replace(fragment="")
        normalized_url = urlunparse(normalized)
        return normalized_url.rstrip("/") if normalized_url.endswith("/") else normalized_url

    @staticmethod
    def _is_crawlable_url(
        url: str,
        base_host: str,
        allow_external: bool,
        allow_subdomains: bool,
    ) -> bool:
        """按域名策略判断链接是否应加入爬取队列。"""
        if allow_external:
            return True

        host = (urlparse(url).hostname or "").lower()
        if not host or not base_host:
            return False
        if host == base_host:
            return True
        if allow_subdomains and host.endswith("." + base_host):
            return True
        return False

    # ==================== 互联网搜索方法 ====================

    async def search_internet(
        self,
        query: str,
        engines: Optional[List[SearchEngine]] = None,
        num_results: int = 10,
        auto_crawl: bool = False,
        crawl_pages: int = 3,
    ) -> AgentResponse:
        """
        互联网搜索 - 支持多引擎并行搜索

        Args:
            query: 搜索关键词
            engines: 搜索引擎列表，None 则自动选择
            num_results: 结果数量
            auto_crawl: 是否自动爬取搜索结果页面
            crawl_pages: 自动爬取的页面数

        Returns:
            AgentResponse: 搜索结果
        """
        # 确保搜索引擎初始化
        if self._search_engine is None:
            self._search_engine = MultiSearchEngine()

        # 执行搜索
        if engines is None:
            engines = self._select_search_engines(query)

        responses = await self._search_engine.search(
            query, engines, num_results, deduplicate=True, parallel=True
        )

        # 检查错误
        failed = [r for r in responses if r.error]
        success = [r for r in responses if r.error is None]

        if not success:
            fallback_response = await self._search_internet_with_deep_fallback(
                query=query,
                num_results=num_results,
                auto_crawl=auto_crawl,
                crawl_pages=crawl_pages,
            )
            if fallback_response is not None:
                return fallback_response

            return AgentResponse(
                success=False,
                content=f"搜索失败：{', '.join(f.error for f in failed)}",
            )

        # 合并结果
        all_results = []
        for response in success:
            all_results.extend(response.results)

        # 去重
        seen_urls = set()
        unique_results = []
        for result in all_results:
            if result.url not in seen_urls:
                seen_urls.add(result.url)
                unique_results.append(result)

        if not unique_results:
            fallback_response = await self._search_internet_with_deep_fallback(
                query=query,
                num_results=num_results,
                auto_crawl=auto_crawl,
                crawl_pages=crawl_pages,
            )
            if fallback_response is not None:
                return fallback_response

        result_dicts = [r.to_dict() for r in unique_results]
        citations = build_web_citations(result_dicts, query=query, prefix="W")
        comparison = build_comparison_summary(result_dicts)
        references_text = format_reference_block(citations, max_items=20)

        # 自动爬取
        crawled_content = []
        if auto_crawl and unique_results:
            crawled_content = await self._crawl_search_results(unique_results[:crawl_pages])

        # 构建响应
        content = self._format_search_results(unique_results, crawled_content, citations)

        return AgentResponse(
            success=True,
            content=content,
            data={
                "results": result_dicts,
                "crawled_content": crawled_content,
                "engines_used": [e.value for e in engines],
                "citations": citations,
                "references_text": references_text,
                "comparison": comparison,
            },
            urls=[r.url for r in unique_results],
            metadata={
                "query": query,
                "total_results": len(unique_results),
                "engines": [r.engine for r in unique_results],
            },
        )

    async def _search_internet_with_deep_fallback(
        self,
        query: str,
        num_results: int,
        auto_crawl: bool,
        crawl_pages: int,
    ) -> Optional[AgentResponse]:
        """当基础搜索链路失败或空结果时，使用深搜引擎兜底。"""
        try:
            from core.search.advanced import DeepSearchEngine
        except Exception as exc:
            logger.warning("Deep search fallback import failed: %s", exc)
            return None

        requested_crawl_top = max(0, crawl_pages) if auto_crawl else 0
        crawl_attempts = [requested_crawl_top]
        if requested_crawl_top > 0:
            crawl_attempts.append(0)

        deep_result: Dict[str, Any] = {}
        raw_results: List[Dict[str, Any]] = []

        deep_search = DeepSearchEngine()
        try:
            for crawl_top in crawl_attempts:
                try:
                    candidate = await deep_search.deep_search(
                        query,
                        num_results=max(8, num_results),
                        use_english=not bool(re.search(r"[\u4e00-\u9fff]", query)),
                        crawl_top=crawl_top,
                        query_variants=1,
                    )
                except Exception as exc:
                    logger.warning("Deep search fallback failed (crawl_top=%s): %s", crawl_top, exc)
                    continue

                if not isinstance(candidate, dict) or not candidate.get("success"):
                    continue

                candidate_results = candidate.get("results", [])
                if isinstance(candidate_results, list) and candidate_results:
                    deep_result = candidate
                    raw_results = candidate_results
                    break
        finally:
            await deep_search.close()

        if not raw_results:
            return None

        converted_results: List[SearchResult] = []
        for idx, item in enumerate(raw_results, 1):
            if not isinstance(item, dict):
                continue
            metadata = item.get("metadata")
            if not isinstance(metadata, dict):
                metadata = {}
            rank_val = item.get("rank", idx)
            try:
                rank = int(rank_val)
            except (TypeError, ValueError):
                rank = idx
            converted_results.append(
                SearchResult(
                    title=str(item.get("title", "")),
                    url=str(item.get("url", "")),
                    snippet=str(item.get("snippet", "")),
                    engine=str(item.get("engine", "deep_fallback")),
                    rank=rank,
                    metadata=metadata,
                )
            )

        if not converted_results:
            return None

        crawled_content = deep_result.get("crawled_content", [])
        if not isinstance(crawled_content, list):
            crawled_content = []

        citations = deep_result.get("citations", [])
        if not isinstance(citations, list):
            citations = build_web_citations(
                [r.to_dict() for r in converted_results],
                query=query,
                prefix="W",
            )

        references_text = deep_result.get("references_text")
        if not isinstance(references_text, str) or not references_text.strip():
            references_text = format_reference_block(citations, max_items=20)

        comparison = deep_result.get("comparison")
        if not isinstance(comparison, dict):
            comparison = build_comparison_summary([r.to_dict() for r in converted_results])

        content = self._format_search_results(converted_results, crawled_content, citations)

        return AgentResponse(
            success=True,
            content=content,
            data={
                "results": [r.to_dict() for r in converted_results],
                "crawled_content": crawled_content,
                "engines_used": sorted({r.engine for r in converted_results}),
                "citations": citations,
                "references_text": references_text,
                "comparison": comparison,
                "fallback_mode": "deep_search",
            },
            urls=[r.url for r in converted_results],
            metadata={
                "query": query,
                "total_results": len(converted_results),
                "fallback_mode": "deep_search",
            },
        )

    async def search_and_fetch(
        self,
        query: str,
        num_results: int = 5,
        fetch_content: bool = True,
    ) -> AgentResponse:
        """
        搜索并获取内容 - 组合搜索和爬虫能力

        Args:
            query: 搜索关键词
            num_results: 结果数量
            fetch_content: 是否获取完整内容

        Returns:
            AgentResponse: 搜索结果和页面内容
        """
        # 第一步：搜索
        search_result = await self.search_internet(
            query, num_results=num_results, auto_crawl=fetch_content
        )

        if not search_result.success:
            return search_result

        # 第二步：访问结果页面（如果还没访问过）
        visited = []
        for url in search_result.urls[:num_results]:
            if self._kernel is None:
                await self._init()
            assert self._kernel is not None
            if not self._kernel.has_visited(url):
                visit_result = await self.visit(url)
                if visit_result.success:
                    visited.append({
                        "url": url,
                        "title": visit_result.data.get("title") if visit_result.data else "",
                        "content_preview": visit_result.content[:500],
                    })

        return AgentResponse(
            success=True,
            content=f"搜索完成，找到 {len(search_result.urls)} 个结果，获取了 {len(visited)} 个页面内容\n\n" + search_result.content,
            data={
                **search_result.data,
                "visited_pages": visited,
            },
            urls=search_result.urls,
        )

    async def research_topic(
        self,
        topic: str,
        max_searches: int = 3,
        max_pages: int = 10,
    ) -> AgentResponse:
        """
        深度研究主题 - 多次搜索 + 深度爬取

        Args:
            topic: 研究主题
            max_searches: 最大搜索次数
            max_pages: 最大爬取页面数

        Returns:
            AgentResponse: 研究结果
        """
        queries = self._generate_queries(topic, max_searches)

        # MindSearch 风格：子查询并行执行
        search_tasks = [
            self.search_internet(query, num_results=5, auto_crawl=False)
            for query in queries
        ]
        search_responses = await asyncio.gather(*search_tasks, return_exceptions=True)

        all_results: List[Dict[str, Any]] = []
        errors: List[str] = []
        for response in search_responses:
            if isinstance(response, Exception):
                errors.append(str(response))
                continue
            if not response.success:
                if response.error:
                    errors.append(response.error)
                continue
            results = response.data.get("results", []) if response.data else []
            if isinstance(results, list):
                all_results.extend(results)

        # 结果去重并规范化 URL
        seen_urls = set()
        unique_urls: List[str] = []
        for item in all_results:
            if not isinstance(item, dict):
                continue
            raw_url = item.get("url", "")
            normalized = self._normalize_crawl_url(raw_url)
            if not normalized or normalized in seen_urls:
                continue
            seen_urls.add(normalized)
            unique_urls.append(normalized)

        if not unique_urls:
            return AgentResponse(
                success=False,
                content=f"研究失败：未找到可爬取结果 - {topic}",
                data={
                    "topic": topic,
                    "queries": queries,
                    "errors": errors,
                },
                error="no_search_results",
            )

        dedup_search_items: List[Dict[str, Any]] = []
        seen_search_urls = set()
        for item in all_results:
            if not isinstance(item, dict):
                continue
            normalized_url = self._normalize_crawl_url(item.get("url", ""))
            if not normalized_url or normalized_url in seen_search_urls:
                continue
            seen_search_urls.add(normalized_url)
            normalized_item = dict(item)
            normalized_item["url"] = normalized_url
            dedup_search_items.append(normalized_item)

        citations = build_web_citations(dedup_search_items, query=topic, prefix="R")
        comparison = build_comparison_summary(dedup_search_items)
        references_text = format_reference_block(citations, max_items=20)

        # DocsGPT 风格：多种子站点分配抓取预算，避免只抓第一条结果
        crawled_pages: List[Dict[str, Any]] = []
        if max_pages > 0:
            total_budget = max(1, max_pages)
            seed_count = min(3, len(unique_urls), total_budget)
            seeds = unique_urls[:seed_count]
            base_budget = total_budget // seed_count
            extra_budget = total_budget % seed_count

            crawl_tasks = []
            for idx, seed_url in enumerate(seeds):
                budget = base_budget + (1 if idx < extra_budget else 0)
                if budget <= 0:
                    continue
                crawl_tasks.append(
                    self.crawl(
                        seed_url,
                        max_pages=budget,
                        max_depth=2,
                        allow_external=False,
                        allow_subdomains=True,
                    )
                )

            crawl_responses = await asyncio.gather(*crawl_tasks, return_exceptions=True)
            crawled_seen = set()
            for crawl_response in crawl_responses:
                if isinstance(crawl_response, Exception):
                    errors.append(str(crawl_response))
                    continue
                if not crawl_response.success:
                    if crawl_response.error:
                        errors.append(crawl_response.error)
                    continue

                pages = crawl_response.data.get("pages", []) if crawl_response.data else []
                for page in pages:
                    page_url = page.get("url") if isinstance(page, dict) else None
                    if not page_url or page_url in crawled_seen:
                        continue
                    crawled_seen.add(page_url)
                    crawled_pages.append(page)

        knowledge = self.get_knowledge_base()

        return AgentResponse(
            success=True,
            content=(
                f"完成主题研究：{topic}\n\n"
                f"执行了 {len(queries)} 次搜索\n"
                f"搜索命中 {len(unique_urls)} 个唯一 URL\n"
                f"实际爬取 {len(crawled_pages)} 个页面\n\n"
                f"{self._format_knowledge_summary(knowledge)}\n\n"
                f"{references_text}"
            ),
            data={
                "topic": topic,
                "queries": queries,
                "search_results": all_results,
                "seed_urls": unique_urls[:3],
                "crawled_pages": crawled_pages,
                "knowledge": knowledge,
                "errors": errors,
                "citations": citations,
                "references_text": references_text,
                "comparison": comparison,
            },
            urls=unique_urls[:max_pages] if max_pages > 0 else unique_urls,
        )

    async def mindsearch_research(
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
    ) -> AgentResponse:
        """
        MindSearch 风格研究（规划 + 图搜索 + 引用汇总）。
        """
        pressure_snapshot = self.get_runtime_pressure_snapshot(refresh=True)
        pressure_level = str(pressure_snapshot.get("level") or "normal")
        pressure_limits = pressure_snapshot.get("limits")
        if not isinstance(pressure_limits, dict):
            pressure_limits = {}

        pipeline = MindSearchPipeline(
            max_turns=max_turns,
            max_branches=max_branches,
            num_results=num_results,
            crawl_top=crawl_top,
            use_english=use_english,
            channel_profiles=channel_profiles or None,
            planner_name=planner_name,
            strict_expand=strict_expand,
            pressure_level=pressure_level,
            pressure_limits=pressure_limits,
        )
        result = await pipeline.run(query)

        stats = result.get("stats", {}) if isinstance(result, dict) else {}
        merged_results = result.get("results", []) if isinstance(result, dict) else []
        top_urls = [
            item.get("url")
            for item in merged_results[:20]
            if isinstance(item, dict) and item.get("url")
        ]

        content = (
            f"MindSearch 研究完成：{query}\n\n"
            f"节点总数：{stats.get('total_nodes', 0)}\n"
            f"完成节点：{stats.get('completed_nodes', 0)}\n"
            f"失败节点：{stats.get('failed_nodes', 0)}\n"
            f"聚合结果：{result.get('total_results', 0)}\n\n"
            f"{result.get('references_text', '')}"
        )

        return AgentResponse(
            success=True,
            content=content,
            data=result,
            urls=top_urls,
            metadata={
                "mode": "mindsearch",
                "query": query,
                "planner": result.get("planner", {}),
                "runtime_profile": result.get("runtime_profile", {}),
                "runtime_pressure": pressure_snapshot,
                "global_context_event_id": result.get("global_context_event_id"),
            },
        )

    def get_global_context_snapshot(self, limit: int = 20, event_type: Optional[str] = None) -> Dict[str, Any]:
        """获取全局深度抓取上下文快照。"""
        store = get_global_deep_context()
        return store.snapshot(limit=limit, event_type=event_type)

    def register_post_processors(self, specs: Optional[List[str]] = None, force: bool = False) -> Dict[str, Any]:
        """加载/查看结果后处理扩展。"""
        registry = get_post_processor_registry()
        loaded: List[str] = []
        if specs:
            loaded = registry.load_from_specs(specs, force=force)
        else:
            loaded = registry.load_from_env(force=force)

        return {
            "loaded": loaded,
            "processors": registry.list_processors(),
        }

    def register_research_planners(self, specs: Optional[List[str]] = None, force: bool = False) -> Dict[str, Any]:
        """加载/查看 MindSearch planner 扩展。"""
        registry = get_research_planner_registry()
        loaded: List[str] = []
        if specs:
            loaded = registry.load_from_specs(specs, force=force)
        else:
            loaded = registry.load_from_env(force=force)

        active = registry.resolve().name
        return {
            "loaded": loaded,
            "planners": registry.list_planners(),
            "active": active,
        }

    def get_challenge_profiles(self) -> Dict[str, Any]:
        """获取 challenge workflow profile 信息。"""
        runner = get_challenge_workflow_runner()
        return {
            "profiles": runner.describe_profiles(),
        }

    def get_auth_profiles(self) -> Dict[str, Any]:
        """获取本地登录态 profile 列表。"""
        registry = get_auth_profile_registry()
        return {
            "profiles": registry.describe_profiles(),
        }

    def get_auth_hint(self, url: str) -> Dict[str, Any]:
        """根据 URL 提示登录态配置建议。"""
        registry = get_auth_profile_registry()
        return registry.build_hint(url)

    def export_auth_template(self, output_path: Optional[str] = None, force: bool = False) -> Dict[str, Any]:
        """导出本地登录态 JSON 模板。"""
        registry = get_auth_profile_registry()
        return registry.export_template(output_path=output_path, force=force)

    async def run_workflow_spec(
        self,
        spec: Dict[str, Any],
        variable_overrides: Optional[Dict[str, Any]] = None,
        strict: bool = False,
    ) -> AgentResponse:
        """运行声明式 workflow（给外层 AI 按目标动态编排抓取流程）。"""
        runner = WorkflowRunner(self)
        payload = await runner.run_spec(
            spec=spec,
            variable_overrides=variable_overrides,
            strict=strict,
        )
        trace = distill_workflow_trace(payload)
        payload["trace_distilled"] = trace
        try:
            store = get_global_deep_context()
            event = store.record(
                event_type="workflow_trace",
                source="workflow_runner",
                payload=trace,
            )
            payload["trace_event_id"] = event.get("id")
            payload["global_context_size"] = store.size
        except Exception as exc:
            logger.debug("record workflow trace failed: %s", exc)

        reports = payload.get("reports", []) if isinstance(payload, dict) else []
        completed = sum(
            1
            for item in reports
            if isinstance(item, dict) and item.get("status") in {"completed", "soft_failed"}
        )
        total = len(reports) if isinstance(reports, list) else 0
        failed_step = payload.get("failed_step") if isinstance(payload, dict) else None
        content = (
            f"Workflow 执行完成：{payload.get('name', 'workflow')}\n"
            f"步骤：{completed}/{total}\n"
            f"硬失败步骤：{failed_step or '无'}\n"
            f"软失败步骤：{payload.get('soft_failed_steps', 0)}"
        )
        return AgentResponse(
            success=bool(payload.get("success")),
            content=content,
            data=payload,
            urls=payload.get("urls", []) if isinstance(payload.get("urls"), list) else [],
            error=(None if payload.get("success") else f"workflow_failed:{failed_step or 'unknown'}"),
            metadata={
                "mode": "workflow",
                "name": payload.get("name"),
                "failed_step": failed_step,
                "strict": strict,
            },
        )

    def get_workflow_schema(self) -> Dict[str, Any]:
        """返回 workflow 可编排 schema，便于 AI 自主决策每一步。"""
        return get_workflow_schema()

    def export_workflow_template(
        self,
        output_path: Optional[str] = None,
        scenario: str = "social_comments",
        force: bool = False,
    ) -> Dict[str, Any]:
        """导出 workflow 模板 JSON（本地可编辑）。"""
        template = build_workflow_template(scenario=scenario)
        if output_path:
            target = Path(output_path).expanduser()
            if not target.is_absolute():
                target = Path.cwd() / target
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.exists() and not force:
                raise FileExistsError(f"workflow template already exists: {target}")
            target.write_text(
                json.dumps(template, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            return {
                "success": True,
                "scenario": scenario,
                "path": str(target),
                "template": template,
                "templates": available_workflow_templates(),
            }

        return {
            "success": True,
            "scenario": scenario,
            "template": template,
            "templates": available_workflow_templates(),
        }

    def get_skill_profiles(self) -> Dict[str, Any]:
        """返回可用 skill 契约，用于 AI 阶段性唤醒。"""
        registry = get_skill_registry()
        return {
            "skills": registry.describe_profiles(),
            "default": registry.default_profile_name,
        }

    def build_skill_playbook(
        self,
        task: str,
        explicit_skill: Optional[str] = None,
        html_first: Optional[bool] = None,
        top_results: Optional[int] = None,
        use_browser: Optional[bool] = None,
        crawl_assist: Optional[bool] = None,
        crawl_pages: Optional[int] = None,
        strict: bool = False,
        command_name: str = "do-plan",
    ) -> Dict[str, Any]:
        """构建阶段化执行剧本，供外层 AI 短上下文稳定调用。"""
        compiled = self.compile_task_ir(
            task=task,
            explicit_skill=explicit_skill,
            html_first=html_first,
            top_results=top_results,
            use_browser=use_browser,
            crawl_assist=crawl_assist,
            crawl_pages=crawl_pages,
            strict=strict,
            dry_run=True,
            command_name=command_name,
        )
        if not compiled.get("success"):
            return {
                "success": False,
                "error": compiled.get("error"),
                "compiled": compiled,
            }
        return self._compose_playbook_from_compiled(task=task, compiled=compiled, strict=strict)

    def build_skill_probe(
        self,
        task: str,
        explicit_skill: Optional[str] = None,
        html_first: Optional[bool] = None,
        top_results: Optional[int] = None,
        use_browser: Optional[bool] = None,
        crawl_assist: Optional[bool] = None,
        crawl_pages: Optional[int] = None,
        strict: bool = False,
        command_name: str = "skills_probe",
    ) -> Dict[str, Any]:
        """
        生成紧凑的 skill 路由探针结果，供 CLI/外层 AI 低上下文决策。
        """
        task_text = str(task or "").strip()
        if not task_text:
            return {
                "success": False,
                "error": "empty_task",
            }

        compiled = self.compile_task_ir(
            task=task_text,
            explicit_skill=explicit_skill,
            html_first=html_first,
            top_results=top_results,
            use_browser=use_browser,
            crawl_assist=crawl_assist,
            crawl_pages=crawl_pages,
            strict=strict,
            dry_run=True,
            command_name=command_name,
        )
        if not compiled.get("success"):
            return {
                "success": False,
                "error": compiled.get("error"),
                "compiled": compiled,
            }

        ir = compiled.get("ir") if isinstance(compiled.get("ir"), dict) else {}
        lint = compiled.get("lint") if isinstance(compiled.get("lint"), dict) else {}
        profile = compiled.get("skill") if isinstance(compiled.get("skill"), dict) else {}
        skill_resolution = (
            compiled.get("skill_resolution")
            if isinstance(compiled.get("skill_resolution"), dict)
            else {}
        )
        selected_detail = (
            skill_resolution.get("selected_detail")
            if isinstance(skill_resolution.get("selected_detail"), dict)
            else {}
        )

        playbook = self._compose_playbook_from_compiled(
            task=task_text,
            compiled=compiled,
            strict=strict,
        )
        if not isinstance(playbook, dict):
            playbook = {}

        top_candidates: List[Dict[str, Any]] = []
        raw_top_scores = skill_resolution.get("top_scores")
        if isinstance(raw_top_scores, list):
            for item in raw_top_scores[:3]:
                if not isinstance(item, dict):
                    continue
                top_candidates.append(
                    {
                        "name": item.get("name"),
                        "score": item.get("score"),
                        "eligible": item.get("eligible"),
                    }
                )

        compact_resolution = {
            "mode": skill_resolution.get("mode"),
            "selected": skill_resolution.get("selected"),
            "min_margin": skill_resolution.get("min_margin"),
            "score_margin": skill_resolution.get("score_margin"),
            "fallback_reason": skill_resolution.get("fallback_reason"),
            "selected_detail": {
                "name": selected_detail.get("name"),
                "score": selected_detail.get("score"),
                "eligible": selected_detail.get("eligible"),
                "matched_keywords": selected_detail.get("matched_keywords", []),
                "activation_hits": selected_detail.get("activation_hits", []),
            },
            "top_candidates": top_candidates,
        }

        return {
            "success": True,
            "task": task_text,
            "selected_skill": str(ir.get("skill") or "default_general_research"),
            "route": str(ir.get("route") or "general"),
            "confidence": {
                "min_margin": skill_resolution.get("min_margin"),
                "score_margin": skill_resolution.get("score_margin"),
                "fallback_reason": skill_resolution.get("fallback_reason"),
                "eligible": selected_detail.get("eligible"),
                "matched_keywords": selected_detail.get("matched_keywords", []),
                "activation_hits": selected_detail.get("activation_hits", []),
            },
            "lint": {
                "valid": bool(lint.get("valid", False)),
                "error_count": int(lint.get("error_count", 0)),
                "warning_count": int(lint.get("warning_count", 0)),
                "issue_count": int(lint.get("issue_count", 0)),
            },
            "skill_profile": {
                "name": profile.get("name"),
                "description": profile.get("description"),
                "route": profile.get("route"),
                "workflow_template": profile.get("workflow_template"),
                "default_options": profile.get("default_options", {}),
                "phases": profile.get("phases", []),
            },
            "playbook": {
                "recommended_cli_sequence": (
                    playbook.get("recommended_cli_sequence")
                    if isinstance(playbook.get("recommended_cli_sequence"), list)
                    else []
                ),
                "phase_wakeup": (
                    playbook.get("phase_wakeup")
                    if isinstance(playbook.get("phase_wakeup"), list)
                    else []
                ),
                "ai_contract": (
                    playbook.get("ai_contract")
                    if isinstance(playbook.get("ai_contract"), dict)
                    else {}
                ),
            },
            "skill_resolution": compact_resolution,
        }

    async def run_do_task(
        self,
        task: str,
        html_first: Optional[bool] = None,
        top_results: Optional[int] = None,
        use_browser: Optional[bool] = None,
        crawl_assist: Optional[bool] = None,
        crawl_pages: Optional[int] = None,
        strict: bool = False,
        dry_run: bool = False,
        explicit_skill: Optional[str] = None,
        command_name: str = "do",
    ) -> AgentResponse:
        """CLI 单入口：task -> IR -> lint -> workflow。"""
        compiled = self.compile_task_ir(
            task=task,
            html_first=html_first,
            top_results=top_results,
            use_browser=use_browser,
            crawl_assist=crawl_assist,
            crawl_pages=crawl_pages,
            strict=strict,
            dry_run=dry_run,
            explicit_skill=explicit_skill,
            command_name=command_name,
        )
        if not compiled.get("success"):
            return AgentResponse(
                success=False,
                content=f"IR 编译失败：{compiled.get('error')}",
                error=str(compiled.get("error") or "compile_failed"),
                data=compiled,
                metadata={"mode": "do", "command": command_name},
            )

        if dry_run or not compiled.get("valid"):
            playbook = self._compose_playbook_from_compiled(task=task, compiled=compiled, strict=strict)
            if isinstance(compiled, dict):
                compiled["playbook"] = playbook
            return AgentResponse(
                success=bool(compiled.get("valid")),
                content=(
                    f"IR dry-run 完成：goal={task}\n"
                    f"skill={compiled.get('ir', {}).get('skill')}\n"
                    f"route={compiled.get('ir', {}).get('route')}\n"
                    f"lint={compiled.get('lint', {}).get('error_count', 0)} errors / "
                    f"{compiled.get('lint', {}).get('warning_count', 0)} warnings"
                ),
                data=compiled,
                error=(None if compiled.get("valid") else "ir_lint_failed"),
                metadata={"mode": "do_dry_run", "command": command_name},
            )

        spec = compiled["ir"]["workflow"]["spec"]
        response = await self.run_workflow_spec(spec=spec, strict=strict)
        response.metadata.update(
            {
                "mode": "do",
                "command": command_name,
                "route": compiled["ir"].get("route"),
                "skill": compiled["ir"].get("skill"),
            }
        )
        if isinstance(response.data, dict):
            response.data["ir"] = compiled.get("ir")
            response.data["lint"] = compiled.get("lint")
            response.data["skill_resolution"] = compiled.get("skill_resolution")
        response.content = (
            f"do 执行完成：{task}\n"
            f"skill={compiled['ir'].get('skill')} route={compiled['ir'].get('route')}\n\n"
            f"{response.content}"
        )
        return response

    def compile_task_ir(
        self,
        task: str,
        html_first: Optional[bool] = None,
        top_results: Optional[int] = None,
        use_browser: Optional[bool] = None,
        crawl_assist: Optional[bool] = None,
        crawl_pages: Optional[int] = None,
        strict: bool = False,
        dry_run: bool = False,
        explicit_skill: Optional[str] = None,
        command_name: str = "do",
    ) -> Dict[str, Any]:
        """将任务编译为稳定 IR，并执行 lint。"""
        task_text = str(task or "").strip()
        if not task_text:
            return {
                "success": False,
                "error": "empty_task",
            }

        registry = get_skill_registry()
        profile, skill_resolution = registry.resolve(task_text, explicit_skill=explicit_skill)
        if explicit_skill and profile is None:
            return {
                "success": False,
                "error": f"skill_not_found:{explicit_skill}",
                "skill_resolution": skill_resolution,
            }

        skill_defaults = profile.default_options if isinstance(profile, SkillProfile) else {}
        resolved_html_first = (
            self._coerce_bool(html_first, True)
            if html_first is not None
            else self._coerce_bool(skill_defaults.get("html_first"), True)
        )
        resolved_top_results = (
            self._coerce_int(top_results, 5)
            if top_results is not None
            else self._coerce_int(skill_defaults.get("top_results"), 5)
        )
        resolved_use_browser = (
            self._coerce_bool(use_browser, False)
            if use_browser is not None
            else self._coerce_bool(skill_defaults.get("use_browser"), False)
        )
        resolved_crawl_assist = (
            self._coerce_bool(crawl_assist, False)
            if crawl_assist is not None
            else self._coerce_bool(skill_defaults.get("crawl_assist"), False)
        )
        resolved_crawl_pages = (
            self._coerce_int(crawl_pages, 2)
            if crawl_pages is not None
            else self._coerce_int(skill_defaults.get("crawl_pages"), 2)
        )

        route_override: Optional[str] = None
        inferred_route = self._classify_task_route(task_text)
        if profile and str(profile.route).strip().lower() not in {"", "auto"}:
            candidate_route = str(profile.route).strip().lower()
            # First-principles guard:
            # - explicit skill can always override route
            # - inferred/default skill should not downgrade URL tasks to general search
            if explicit_skill:
                route_override = candidate_route
            elif inferred_route != "url" and profile.name != "default_general_research":
                route_override = candidate_route

        try:
            if profile and profile.workflow_template:
                route, spec = self._build_skill_template_spec(
                    task=task_text,
                    profile=profile,
                    html_first=resolved_html_first,
                    top_results=resolved_top_results,
                    use_browser=resolved_use_browser,
                    crawl_assist=resolved_crawl_assist,
                    crawl_pages=resolved_crawl_pages,
                    route_override=route_override,
                )
            else:
                route, spec = self._build_default_orchestration_spec(
                    task=task_text,
                    html_first=resolved_html_first,
                    top_results=resolved_top_results,
                    use_browser=resolved_use_browser,
                    crawl_assist=resolved_crawl_assist,
                    crawl_pages=resolved_crawl_pages,
                    route_override=route_override,
                )
                if profile:
                    self._merge_skill_variables(spec, profile.default_variables)
        except Exception as exc:
            return {
                "success": False,
                "error": f"build_spec_failed:{exc}",
                "skill_resolution": skill_resolution,
                "skill": (profile.to_dict() if profile else None),
            }

        options = {
            "html_first": resolved_html_first,
            "top_results": resolved_top_results,
            "use_browser": resolved_use_browser,
            "crawl_assist": resolved_crawl_assist,
            "crawl_pages": resolved_crawl_pages,
        }
        ir = build_command_ir(
            command=command_name,
            goal=task_text,
            route=route,
            workflow_spec=spec,
            options=options,
            skill=(profile.name if profile else "default_general_research"),
            strict=strict,
            dry_run=dry_run,
            metadata={
                "skill_source": (profile.source if profile else "fallback"),
                "skill_resolution_mode": skill_resolution.get("mode"),
            },
        )
        issues = lint_command_ir(ir, workflow_schema=get_workflow_schema())
        lint_summary = summarize_lint(issues)

        result: Dict[str, Any] = {
            "success": True,
            "valid": not has_lint_errors(issues),
            "ir": ir,
            "lint": {
                **lint_summary,
                "issues": issues,
            },
            "skill_resolution": skill_resolution,
            "skill": (profile.to_dict() if profile else None),
        }
        return result

    def _compose_playbook_from_compiled(
        self,
        task: str,
        compiled: Dict[str, Any],
        strict: bool,
    ) -> Dict[str, Any]:
        """将编译结果转成阶段化技能剧本与推荐 CLI 序列。"""
        ir = compiled.get("ir") if isinstance(compiled.get("ir"), dict) else {}
        skill = compiled.get("skill") if isinstance(compiled.get("skill"), dict) else {}
        lint = compiled.get("lint") if isinstance(compiled.get("lint"), dict) else {}

        selected_skill = str(ir.get("skill") or "default_general_research")
        route = str(ir.get("route") or "general")
        phases = skill.get("phases") if isinstance(skill.get("phases"), list) else []
        if not phases:
            phases = [
                {"id": "intent", "title": "Intent Resolve", "goal": "确认任务目标与输出格式"},
                {"id": "dry_run", "title": "Compile & Lint", "goal": "dry-run 检查 IR 与 lint"},
                {"id": "execute", "title": "Execute", "goal": "执行并产出引用证据"},
            ]

        commands = self._build_recommended_cli_sequence(
            task=task,
            selected_skill=selected_skill,
            route=route,
            strict=strict,
        )
        phase_wakeup = self._build_phase_wakeup(
            phases=phases,
            commands=commands,
        )

        return {
            "success": True,
            "selected_skill": selected_skill,
            "route": route,
            "lint_valid": bool(lint.get("valid")),
            "phases": phases,
            "recommended_cli_sequence": commands,
            "phase_wakeup": phase_wakeup,
            "ai_contract": {
                "mode": "phase_serial",
                "rules": [
                    "Run phases in order and do not skip dry-run checks.",
                    "Prefer `do-plan`/`do` over low-level commands for unstable sites.",
                    "When auth/challenge hints exist, surface them before execution.",
                ],
            },
        }

    def _build_recommended_cli_sequence(
        self,
        task: str,
        selected_skill: str,
        route: str,
        strict: bool,
    ) -> List[str]:
        task_text = str(task or "").replace('"', '\\"')
        commands: List[str] = []
        commands.append(build_cli_command(f'skills --resolve "{task_text}" --compact'))
        if route in {"social", "commerce", "url"}:
            commands.append(build_cli_command("challenge-profiles"))
            commands.append(build_cli_command("auth-template"))
        do_dry = build_cli_command(f'do "{task_text}" --skill={selected_skill} --dry-run')
        if strict:
            do_dry += " --strict"
        commands.append(do_dry)
        do_exec = build_cli_command(f'do "{task_text}" --skill={selected_skill}')
        if strict:
            do_exec += " --strict"
        commands.append(do_exec)
        commands.append(build_cli_command("context --event=workflow_trace --limit=10"))
        return commands

    @staticmethod
    def _build_phase_wakeup(
        phases: List[Dict[str, Any]],
        commands: List[str],
    ) -> List[Dict[str, Any]]:
        wakeup: List[Dict[str, Any]] = []
        command_map: Dict[str, List[str]] = {
            "intent": [cmd for cmd in commands if "skills --resolve" in cmd][:1],
            "auth": [cmd for cmd in commands if ("challenge-profiles" in cmd or "auth-template" in cmd)],
            "dry_run": [cmd for cmd in commands if "--dry-run" in cmd][:1],
            "execute": [cmd for cmd in commands if (" do \"" in cmd and "--dry-run" not in cmd)][:1],
            "verify": [cmd for cmd in commands if "context --event=workflow_trace" in cmd][:1],
        }

        for phase in phases:
            if not isinstance(phase, dict):
                continue
            phase_id = str(phase.get("id") or "").strip().lower() or "phase"
            title = str(phase.get("title") or phase_id).strip()
            goal = str(phase.get("goal") or "").strip()
            if phase_id in {"intent", "intention"}:
                checks = ["Skill selected", "Route selected"]
                cmds = command_map["intent"]
            elif phase_id in {"auth", "challenge", "auth_check"}:
                checks = ["Auth profile reviewed", "Challenge profile reviewed"]
                cmds = command_map["auth"]
            elif phase_id in {"dry_run", "compile", "lint"}:
                checks = ["IR generated", "Lint has no errors"]
                cmds = command_map["dry_run"]
            elif phase_id in {"execute", "run"}:
                checks = ["Execution completed", "Citations or evidence produced"]
                cmds = command_map["execute"]
            else:
                checks = ["Phase output captured"]
                cmds = []
            wakeup.append(
                {
                    "id": phase_id,
                    "title": title,
                    "goal": goal,
                    "checks": checks,
                    "recommended_commands": cmds,
                }
            )

        if wakeup and command_map["verify"]:
            wakeup.append(
                {
                    "id": "verify",
                    "title": "Trace Verify",
                    "goal": "Read workflow trace from global context for post-check.",
                    "checks": ["Trace event exists"],
                    "recommended_commands": command_map["verify"],
                }
            )
        return wakeup

    async def orchestrate_task(
        self,
        task: str,
        html_first: bool = True,
        top_results: int = 5,
        use_browser: bool = False,
        crawl_assist: bool = False,
        crawl_pages: int = 2,
        strict: bool = False,
    ) -> AgentResponse:
        """
        默认 AI 入口：
        - 以 workflow 编排层为主
        - 以 HTML-first 分析为主（非必要不深爬）
        """
        return await self.run_do_task(
            task=task,
            html_first=html_first,
            top_results=top_results,
            use_browser=use_browser,
            crawl_assist=crawl_assist,
            crawl_pages=crawl_pages,
            strict=strict,
            dry_run=False,
            explicit_skill=None,
            command_name="task",
        )

    def _build_default_orchestration_spec(
        self,
        task: str,
        html_first: bool,
        top_results: int,
        use_browser: bool,
        crawl_assist: bool,
        crawl_pages: int,
        route_override: Optional[str] = None,
    ) -> tuple[str, Dict[str, Any]]:
        route = str(route_override or self._classify_task_route(task)).strip().lower()
        top_hits = max(1, min(int(top_results), 20))
        assist_pages = max(1, min(int(crawl_pages), 10))

        if route == "url":
            spec: Dict[str, Any] = {
                "name": "default-url-analysis",
                "description": "Analyze a target URL with auth hint and HTML-first reading.",
                "variables": {
                    "target_url": task,
                    "use_browser": use_browser,
                    "top_hits": top_hits,
                },
                "steps": [
                    {
                        "id": "auth_hint",
                        "tool": "auth_hint",
                        "continue_on_error": True,
                        "args": {"url": "${vars.target_url}"},
                    },
                    {
                        "id": "read_target",
                        "tool": "fetch_html" if html_first else "visit",
                        "args": {
                            "url": "${vars.target_url}",
                            "use_browser": "${vars.use_browser}",
                            "auto_fallback": True,
                            "max_chars": 80000,
                        },
                    },
                ],
            }
            if crawl_assist:
                spec["steps"].append(
                    {
                        "id": "crawl_assist",
                        "tool": "crawl",
                        "continue_on_error": True,
                        "args": {
                            "url": "${vars.target_url}",
                            "max_pages": assist_pages,
                            "max_depth": 2,
                            "allow_external": False,
                            "allow_subdomains": True,
                        },
                    }
                )
            return route, spec

        if route == "academic":
            spec = build_workflow_template("academic_relations")
            spec.setdefault("variables", {})
            spec["variables"]["topic"] = task
            spec["variables"]["crawl_top_papers"] = top_hits
            if html_first:
                spec["steps"][-1] = {
                    "id": "read_top_papers_html",
                    "tool": "fetch_html",
                    "for_each": "${steps.academic_search.data.papers}",
                    "item_alias": "paper",
                    "max_items": "${vars.crawl_top_papers}",
                    "continue_on_error": True,
                    "args": {
                        "url": "${local.paper.url}",
                        "use_browser": False,
                        "auto_fallback": True,
                        "max_chars": 60000,
                    },
                }
            return route, spec

        if route == "social":
            social_query = task if any(k in task.lower() for k in ("评论", "comment", "反馈", "discussion")) else f"{task} 评论 用户反馈"
            spec = {
                "name": "default-social-analysis",
                "description": "Search social platforms then inspect top pages in HTML-first mode.",
                "variables": {
                    "query": social_query,
                    "platforms": ["xiaohongshu", "zhihu", "tieba", "douyin", "bilibili", "weibo"],
                    "top_hits": top_hits,
                    "use_browser": use_browser,
                },
                "steps": [
                    {
                        "id": "social_search",
                        "tool": "social",
                        "args": {
                            "query": "${vars.query}",
                            "platforms": "${vars.platforms}",
                        },
                    },
                    {
                        "id": "read_top_pages",
                        "tool": "fetch_html" if html_first else "visit",
                        "for_each": "${steps.social_search.results}",
                        "item_alias": "hit",
                        "max_items": "${vars.top_hits}",
                        "continue_on_error": True,
                        "args": {
                            "url": "${local.hit.url}",
                            "use_browser": "${vars.use_browser}",
                            "auto_fallback": True,
                            "max_chars": 60000,
                        },
                    },
                ],
            }
            if crawl_assist:
                spec["steps"].append(
                    {
                        "id": "crawl_assist",
                        "tool": "crawl",
                        "for_each": "${steps.read_top_pages.items}",
                        "item_alias": "page",
                        "max_items": 1,
                        "continue_on_error": True,
                        "args": {
                            "url": "${local.page.input.url}",
                            "max_pages": assist_pages,
                            "max_depth": 2,
                            "allow_external": False,
                            "allow_subdomains": True,
                        },
                    }
                )
            return route, spec

        if route == "commerce":
            commerce_query = task if any(k in task.lower() for k in ("价格", "评价", "review", "price")) else f"{task} 价格 评价"
            spec = {
                "name": "default-commerce-analysis",
                "description": "Search commerce platforms then inspect top pages in HTML-first mode.",
                "variables": {
                    "query": commerce_query,
                    "platforms": ["taobao", "jd", "pinduoduo", "meituan"],
                    "top_hits": top_hits,
                    "use_browser": use_browser,
                },
                "steps": [
                    {
                        "id": "commerce_search",
                        "tool": "commerce",
                        "args": {
                            "query": "${vars.query}",
                            "platforms": "${vars.platforms}",
                        },
                    },
                    {
                        "id": "read_top_pages",
                        "tool": "fetch_html" if html_first else "visit",
                        "for_each": "${steps.commerce_search.results}",
                        "item_alias": "hit",
                        "max_items": "${vars.top_hits}",
                        "continue_on_error": True,
                        "args": {
                            "url": "${local.hit.url}",
                            "use_browser": "${vars.use_browser}",
                            "auto_fallback": True,
                            "max_chars": 60000,
                        },
                    },
                ],
            }
            if crawl_assist:
                spec["steps"].append(
                    {
                        "id": "crawl_assist",
                        "tool": "crawl",
                        "for_each": "${steps.read_top_pages.items}",
                        "item_alias": "page",
                        "max_items": 1,
                        "continue_on_error": True,
                        "args": {
                            "url": "${local.page.input.url}",
                            "max_pages": assist_pages,
                            "max_depth": 2,
                            "allow_external": False,
                            "allow_subdomains": True,
                        },
                    }
                )
            return route, spec

        spec = {
            "name": "default-general-analysis",
            "description": "General web analysis with search + HTML-first reading.",
            "variables": {
                "query": task,
                "top_hits": top_hits,
                "num_results": max(8, top_hits * 2),
                "use_browser": use_browser,
            },
            "steps": [
                {
                    "id": "web_search",
                    "tool": "search_internet",
                    "args": {
                        "query": "${vars.query}",
                        "num_results": "${vars.num_results}",
                        "auto_crawl": False,
                    },
                },
                {
                    "id": "read_top_pages",
                    "tool": "fetch_html" if html_first else "visit",
                    "for_each": "${steps.web_search.data.results}",
                    "item_alias": "hit",
                    "max_items": "${vars.top_hits}",
                    "continue_on_error": True,
                    "args": {
                        "url": "${local.hit.url}",
                        "use_browser": "${vars.use_browser}",
                        "auto_fallback": True,
                        "max_chars": 60000,
                    },
                },
            ],
        }
        if crawl_assist:
            spec["steps"].append(
                {
                    "id": "crawl_assist",
                    "tool": "crawl",
                    "for_each": "${steps.read_top_pages.items}",
                    "item_alias": "page",
                    "max_items": 1,
                    "continue_on_error": True,
                    "args": {
                        "url": "${local.page.input.url}",
                        "max_pages": assist_pages,
                        "max_depth": 2,
                        "allow_external": False,
                        "allow_subdomains": True,
                    },
                }
            )
        return route, spec

    def _build_skill_template_spec(
        self,
        task: str,
        profile: SkillProfile,
        html_first: bool,
        top_results: int,
        use_browser: bool,
        crawl_assist: bool,
        crawl_pages: int,
        route_override: Optional[str] = None,
    ) -> tuple[str, Dict[str, Any]]:
        """按 skill 模板构建编排 spec。"""
        spec = deepcopy(build_workflow_template(profile.workflow_template or "social_comments"))
        self._merge_skill_variables(spec, profile.default_variables)

        variables = spec.setdefault("variables", {})
        if isinstance(variables, dict):
            if "topic" in variables:
                variables["topic"] = task
            if "query" in variables:
                variables["query"] = task
            if "top_hits" in variables:
                variables["top_hits"] = max(1, min(int(top_results), 20))
            if "crawl_top_papers" in variables:
                variables["crawl_top_papers"] = max(1, min(int(top_results), 20))
            if "use_browser" in variables:
                variables["use_browser"] = bool(use_browser)

        if html_first:
            self._upgrade_template_to_html_first(spec, default_use_browser=use_browser)
        if crawl_assist:
            self._append_template_crawl_assist(spec, crawl_pages=max(1, min(int(crawl_pages), 10)))

        route = str(route_override or profile.route or self._classify_task_route(task)).strip().lower()
        if route in {"", "auto"}:
            route = self._classify_task_route(task)
        return route, spec

    @staticmethod
    def _merge_skill_variables(spec: Dict[str, Any], default_variables: Optional[Dict[str, Any]]) -> None:
        if not isinstance(spec, dict) or not isinstance(default_variables, dict):
            return
        variables = spec.setdefault("variables", {})
        if not isinstance(variables, dict):
            return
        for key, value in default_variables.items():
            variables.setdefault(str(key), deepcopy(value))

    @staticmethod
    def _upgrade_template_to_html_first(spec: Dict[str, Any], default_use_browser: bool) -> None:
        steps = spec.get("steps")
        if not isinstance(steps, list):
            return
        for step in steps:
            if not isinstance(step, dict):
                continue
            tool = str(step.get("tool") or "").strip().lower()
            if tool not in {"visit", "fetch_html"}:
                continue
            args = step.get("args")
            if not isinstance(args, dict):
                args = {}
                step["args"] = args
            if tool == "visit":
                step["tool"] = "fetch_html"
            args.setdefault("use_browser", default_use_browser)
            args.setdefault("auto_fallback", True)
            args.setdefault("max_chars", 60000)

    @staticmethod
    def _append_template_crawl_assist(spec: Dict[str, Any], crawl_pages: int) -> None:
        steps = spec.get("steps")
        if not isinstance(steps, list):
            return
        if any(isinstance(item, dict) and item.get("id") == "crawl_assist" for item in steps):
            return

        source_step_id = ""
        for candidate in ("read_top_pages", "visit_top_hits", "read_top_papers_html", "visit_top_papers"):
            if any(isinstance(item, dict) and str(item.get("id")) == candidate for item in steps):
                source_step_id = candidate
                break
        if not source_step_id:
            return

        steps.append(
            {
                "id": "crawl_assist",
                "tool": "crawl",
                "for_each": f"${{steps.{source_step_id}.items}}",
                "item_alias": "page",
                "max_items": 1,
                "continue_on_error": True,
                "args": {
                    "url": "${local.page.input.url}",
                    "max_pages": max(1, crawl_pages),
                    "max_depth": 2,
                    "allow_external": False,
                    "allow_subdomains": True,
                },
            }
        )

    @staticmethod
    def _coerce_bool(value: Any, default: bool) -> bool:
        if value is None:
            return default
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return bool(value)
        text = str(value).strip().lower()
        if text in {"1", "true", "yes", "on"}:
            return True
        if text in {"0", "false", "no", "off"}:
            return False
        return default

    @staticmethod
    def _coerce_int(value: Any, default: int) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    def _classify_task_route(self, task: str) -> str:
        value = str(task or "").strip()
        lower = value.lower()
        if self._looks_like_url(value):
            return "url"

        if is_academic_query(value) or any(
            token in lower
            for token in [
                "paper", "arxiv", "doi", "citation", "benchmark", "ablation",
                "论文", "文献", "引文", "引用", "基准", "实验",
            ]
        ):
            return "academic"

        if any(
            token in lower
            for token in [
                "xiaohongshu", "zhihu", "weibo", "douyin", "bilibili", "tieba", "reddit", "twitter",
                "小红书", "知乎", "微博", "抖音", "b站", "贴吧", "评论区", "弹幕", "话题",
            ]
        ):
            return "social"

        if any(
            token in lower
            for token in [
                "taobao", "jd", "jingdong", "pinduoduo", "meituan", "dianping",
                "淘宝", "京东", "拼多多", "美团", "点评", "价格", "促销", "购买", "比价",
            ]
        ):
            return "commerce"

        return "general"

    @staticmethod
    def _looks_like_url(text: str) -> bool:
        normalized = str(text or "").strip().lower()
        return normalized.startswith(("http://", "https://", "www."))

    # ==================== 学术模式搜索方法 ====================

    async def search_academic(
        self,
        query: str,
        sources: Optional[List[AcademicSource]] = None,
        num_results: int = 10,
        fetch_abstracts: bool = True,
        include_code: bool = False,
    ) -> AgentResponse:
        """
        学术模式搜索 - 仅在论文/学术网站搜索

        Args:
            query: 搜索关键词
            sources: 学术来源列表，None 则自动选择
            num_results: 结果数量
            fetch_abstracts: 是否获取论文摘要
            include_code: 是否包含代码项目（GitHub/Gitee）

        Returns:
            AgentResponse: 学术搜索结果
        """
        # 确保学术引擎初始化
        if self._academic_engine is None:
            self._academic_engine = AcademicSearchEngine()

        # 自动选择来源
        if sources is None:
            sources = self._select_academic_sources(query, include_code)

        paper_sources = [s for s in sources if s not in {AcademicSource.GITHUB, AcademicSource.GITEE}]
        code_sources = [s for s in sources if s in {AcademicSource.GITHUB, AcademicSource.GITEE}]

        if not paper_sources:
            paper_sources = [
                AcademicSource.ARXIV,
                AcademicSource.SEMANTIC_SCHOLAR,
                AcademicSource.GOOGLE_SCHOLAR,
            ]
        if include_code and not code_sources:
            code_sources = [AcademicSource.GITHUB, AcademicSource.GITEE]

        # 搜索论文（修复：无论 include_code 是否开启，都执行论文检索）
        papers = await self._academic_engine.search_papers(
            query, paper_sources, num_results, fetch_abstracts
        )

        # 搜索代码项目
        code_projects = []
        if include_code and code_sources:
            code_projects = await self._academic_engine.search_code(query, code_sources, num_results)

        paper_dicts = [p.to_dict() for p in papers]
        code_dicts = [c.to_dict() for c in code_projects]
        citations = build_paper_citations(paper_dicts, query=query, prefix="P")
        citations.extend(build_code_citations(code_dicts, query=query, prefix="C"))
        references_text = format_reference_block(citations, max_items=30)

        # 构建响应
        content = self._format_academic_results(papers, code_projects, citations)

        return AgentResponse(
            success=True,
            content=content,
            data={
                "papers": paper_dicts,
                "code_projects": code_dicts,
                "sources": [s.value for s in sources],
                "citations": citations,
                "references_text": references_text,
            },
            urls=[p.url for p in papers] + [c.url for c in code_projects],
            metadata={
                "query": query,
                "paper_count": len(papers),
                "code_count": len(code_projects),
            },
        )

    async def search_with_form(
        self,
        url: str,
        query: str,
        form_data: Optional[Dict[str, str]] = None,
        use_browser: bool = True,
        wait_for: Optional[str] = None,
    ) -> AgentResponse:
        """
        填表搜索 - 在网站内部搜索框提交查询

        Args:
            url: 网站 URL 或搜索页面 URL
            query: 搜索关键词
            form_data: 自定义表单数据，None 则自动检测
            use_browser: 是否使用浏览器
            wait_for: 提交后等待的选择器

        Returns:
            AgentResponse: 填表搜索结果
        """
        timeout_sec = max(5, int(os.getenv("WEB_ROOTER_FORM_TIMEOUT_SEC", "75")))

        # 确保表单填写器初始化
        if self._form_filler is None:
            self._form_filler = FormFiller()

        # 自动检测并填写表单
        try:
            if form_data is None:
                result = await asyncio.wait_for(
                    auto_search(url, query, use_browser=use_browser),
                    timeout=timeout_sec,
                )
            else:
                result = await asyncio.wait_for(
                    self._form_filler.fill_and_submit(
                        url, form_data, use_browser=use_browser, wait_for=wait_for
                    ),
                    timeout=timeout_sec,
                )
        except asyncio.TimeoutError:
            return AgentResponse(
                success=False,
                content=f"站内搜索超时（>{timeout_sec}s）：{url}",
                error=f"site_search_timeout>{timeout_sec}s",
            )

        # 解析搜索结果
        if result.success:
            content = f"搜索完成，找到 {result.result_count} 个结果\n\n"
            if result.extracted_results:
                content += "搜索结果:\n"
                for i, r in enumerate(result.extracted_results[:10], 1):
                    content += f"[{i}] {r.get('title', 'N/A')}\n"
                    content += f"    {r.get('description', 'N/A')[:150]}...\n"
                    content += f"    URL: {r.get('url', 'N/A')}\n\n"

            return AgentResponse(
                success=True,
                content=content,
                data=result.to_dict(),
                urls=[r.get("url") for r in result.extracted_results if r.get("url")],
                metadata={
                    "query": query,
                    "submitted_url": result.submitted_url,
                    "result_count": result.result_count,
                },
            )
        else:
            return AgentResponse(
                success=False,
                content=f"搜索失败：{result.error}",
                error=result.error,
            )

    # ==================== 内部辅助方法 ====================

    def _select_academic_sources(
        self,
        query: str,
        include_code: bool = False,
    ) -> List[AcademicSource]:
        """根据查询选择学术来源"""
        sources = []

        # 默认：预印本 + 学术图谱 + 学术搜索
        sources.extend([
            AcademicSource.ARXIV,
            AcademicSource.SEMANTIC_SCHOLAR,
            AcademicSource.GOOGLE_SCHOLAR,
        ])

        # 中文查询添加 CNKI
        if re.search(r"[\u4e00-\u9fff]", query):
            sources.append(AcademicSource.CNKI)

        # 生物医学相关添加 PubMed
        if any(kw in query.lower() for kw in ["medical", "biology", "clinical", "医学", "生物"]):
            sources.append(AcademicSource.PUBMED)

        # 工程/电子相关添加 IEEE
        if any(kw in query.lower() for kw in ["engineering", "electronic", "IEEE", "工程", "电子"]):
            sources.append(AcademicSource.IEEE)

        # 代码相关
        if include_code or any(kw in query.lower() for kw in ["code", "github", "开源", "项目", "实现"]):
            sources.extend([AcademicSource.GITHUB, AcademicSource.GITEE])
            sources.append(AcademicSource.PAPER_WITH_CODE)

        deduped = []
        for source in sources:
            if source not in deduped:
                deduped.append(source)
        return deduped

    def _format_knowledge_summary(self, knowledge: List[Dict]) -> str:
        """格式化知识摘要"""
        lines = ["已获取的知识:\n"]
        for k in knowledge[:10]:
            lines.append(f"- {k['title']} ({k['url'][:50]}...)")
        return "\n".join(lines)

    def _select_search_engines(self, query: str) -> List[SearchEngine]:
        """根据查询选择搜索引擎"""
        engines = [SearchEngine.BING]  # Bing 默认

        # 中文优先百度
        if re.search(r"[\u4e00-\u9fff]", query):
            engines.append(SearchEngine.BAIDU)

        # 学术相关
        if any(kw in query.lower() for kw in ["paper", "research", "论文", "研究", "学术", "journal"]):
            engines.append(SearchEngine.GOOGLE_SCHOLAR)

        return engines

    def _format_academic_results(
        self,
        papers: List[PaperResult],
        code_projects: List[CodeProjectResult],
        citations: Optional[List[Dict[str, Any]]] = None,
    ) -> str:
        """格式化学术搜索结果"""
        lines = []

        if papers:
            lines.append(f"=== 找到 {len(papers)} 篇论文 ===\n")
            for i, p in enumerate(papers[:10], 1):
                citation_id = (p.metadata or {}).get("citation_id")
                marker = f"[{citation_id}] " if citation_id else f"[{i}] "
                lines.append(f"{marker}{p.title}")
                lines.append(f"    作者：{', '.join(p.authors[:3]) if p.authors else 'N/A'}")
                lines.append(f"    来源：{p.source}")
                if p.publish_date:
                    lines.append(f"    日期：{p.publish_date}")
                if p.citations:
                    lines.append(f"    引用：{p.citations}")
                if p.abstract:
                    lines.append(f"    摘要：{p.abstract[:200]}...")
                if p.pdf_url:
                    lines.append(f"    PDF: {p.pdf_url}")
                lines.append("")

        if code_projects:
            lines.append(f"\n=== 找到 {len(code_projects)} 个代码项目 ===\n")
            for i, c in enumerate(code_projects[:10], 1):
                citation_id = (c.metadata or {}).get("citation_id")
                marker = f"[{citation_id}] " if citation_id else f"[{i}] "
                lines.append(f"{marker}{c.name} ({c.source})")
                lines.append(f"    语言：{c.language}")
                lines.append(f"    Stars: {c.stars}, Forks: {c.forks}")
                lines.append(f"    {c.description[:150]}...")
                lines.append(f"    URL: {c.url}")
                lines.append("")

        if citations:
            lines.append("")
            lines.append(format_reference_block(citations, max_items=30))

        return "\n".join(lines)

    def _generate_queries(self, topic: str, count: int) -> List[str]:
        """生成多个相关查询"""
        count = max(1, count)
        queries = [topic.strip()]

        is_chinese = bool(re.search(r"[\u4e00-\u9fff]", topic))
        expansions = (
            [
                f"什么是 {topic}",
                f"如何 {topic}",
                f"{topic} 最新进展",
                f"{topic} 最佳实践",
                f"{topic} 案例分析",
            ]
            if is_chinese
            else [
                f"what is {topic}",
                f"{topic} latest updates",
                f"{topic} best practices",
                f"{topic} architecture",
                f"{topic} case study",
            ]
        )

        for expanded in expansions:
            normalized = expanded.strip()
            if normalized and normalized not in queries:
                queries.append(normalized)
            if len(queries) >= count:
                break

        return queries[:count]

    async def _crawl_search_results(
        self,
        results: List[SearchResult],
    ) -> List[Dict[str, Any]]:
        """爬取搜索结果页面（失败时自动浏览器兜底）。"""
        crawled = []
        for result in results:
            try:
                visit_result = await self.visit(result.url, use_browser=False, auto_fallback=True)
                if visit_result.success and visit_result.data:
                    text_content = visit_result.data.get("text", "")
                    crawled.append({
                        "url": result.url,
                        "title": visit_result.data.get("title", ""),
                        "content": text_content[:1500] if isinstance(text_content, str) else "",
                        "snippet": result.snippet,
                        "fetch_mode": visit_result.metadata.get("fetch_mode"),
                    })
            except Exception as e:
                logger.warning(f"Failed to crawl {result.url}: {e}")
        return crawled

    def _format_search_results(
        self,
        results: List[SearchResult],
        crawled_content: List[Dict[str, Any]],
        citations: Optional[List[Dict[str, Any]]] = None,
    ) -> str:
        """格式化搜索结果"""
        lines = [f"找到 {len(results)} 个结果:\n"]

        for i, r in enumerate(results[:10], 1):
            citation_id = (r.metadata or {}).get("citation_id")
            marker = f"[{citation_id}]" if citation_id else f"[{i}]"
            lines.append(f"{marker} {r.title}")
            lines.append(f"    URL: {r.url}")
            lines.append(f"    来源：{r.engine}")
            lines.append(f"    摘要：{r.snippet[:150]}...")
            lines.append("")

        if crawled_content:
            lines.append("\n=== 页面内容摘要 ===\n")
            for page in crawled_content:
                lines.append(f"[{page['title']}]")
                lines.append(f"{page['content'][:500]}...")
                lines.append("")

        if citations:
            lines.append(format_reference_block(citations, max_items=20))

        return "\n".join(lines)

    def _format_knowledge_summary(self, knowledge: List[Dict]) -> str:
        """格式化知识摘要"""
        lines = ["已获取的知识:\n"]
        for k in knowledge[:10]:
            lines.append(f"- {k['title']} ({k['url'][:50]}...)")
        return "\n".join(lines)

    # ==================== 内部方法 ====================

    async def _crawler_fetch(self, url: str) -> Any:
        """使用爬虫获取"""
        if self._kernel is None:
            await self._init()
        assert self._kernel is not None
        return await self._kernel.crawler_fetch(url)

    async def _browser_fetch(self, url: str) -> Any:
        """使用浏览器获取"""
        if self._kernel is None:
            await self._init()
        assert self._kernel is not None
        result = await self._kernel.browser_fetch(url)
        self._browser = self._kernel.browser
        return result

    def _should_fallback_to_browser(self, result: Any) -> bool:
        """判断是否需要从 HTTP 抓取兜底到浏览器抓取。"""
        if self._kernel is None:
            return False
        return self._kernel.should_fallback_to_browser(result)

    def _find_relevant_snippets(
        self,
        content: str,
        query: str,
        num_snippets: int = 3,
        snippet_size: int = 200,
    ) -> List[str]:
        """找到相关片段"""
        snippets = []
        lines = content.split("\n")

        for i, line in enumerate(lines):
            if query.lower() in line.lower():
                # 获取上下文
                start = max(0, i - 2)
                end = min(len(lines), i + 3)
                snippet = "\n".join(lines[start:end])
                if len(snippet) <= snippet_size:
                    snippets.append(snippet.strip())
                else:
                    snippets.append(snippet[:snippet_size] + "...")

        return snippets[:num_snippets]

    def _format_search_in_knowledge_results(self, results: List[Dict]) -> str:
        """格式化知识库中的搜索结果"""
        output = []
        for r in results:
            output.append(f"[INFO] {r['title']} ({r['url']})")
            for i, snippet in enumerate(r["snippets"], 1):
                output.append(f"  [{i}] {snippet}")
            output.append("")
        return "\n".join(output)

    def _build_visit_response(
        self,
        *,
        payload: Dict[str, Any],
        metadata: Optional[Dict[str, Any]] = None,
    ) -> AgentResponse:
        title = str(payload.get("title", "")).strip()
        text = str(payload.get("text", ""))
        links = payload.get("links", [])
        urls = []
        if isinstance(links, list):
            for item in links[:10]:
                if isinstance(item, dict) and item.get("href"):
                    urls.append(str(item["href"]))

        return AgentResponse(
            success=True,
            content=f"已访问：{title}\n\n{text[:2000]}",
            data=payload,
            urls=urls,
            metadata=metadata or {},
        )

    def _intelligent_extract(self, knowledge: PageSnapshot, target: str) -> str:
        """智能提取信息"""
        content = knowledge.content

        # 关键词匹配
        keywords = self._extract_keywords(target)
        relevant_lines = []

        for line in content.split("\n"):
            line_lower = line.lower()
            if any(kw in line_lower for kw in keywords):
                relevant_lines.append(line.strip())

        if relevant_lines:
            return "\n".join(relevant_lines[:20])

        # 返回相关内容
        return content[:1000]

    def _extract_keywords(self, text: str) -> List[str]:
        """提取关键词"""
        # 简单分词
        words = re.findall(r"[\w]+", text.lower())
        # 过滤停用词
        stopwords = {"the", "a", "an", "is", "are", "was", "were", "be", "been", "being"}
        return [w for w in words if w not in stopwords and len(w) > 2]

    def get_visited_urls(self) -> List[str]:
        """获取已访问的 URL"""
        if self._kernel is None:
            return []
        return self._kernel.get_visited_urls()

    def get_knowledge_base(self) -> List[Dict[str, Any]]:
        """获取知识库"""
        if self._kernel is None:
            return []
        return self._kernel.get_knowledge_base()

    def get_runtime_state_stats(self) -> Dict[str, Any]:
        """获取运行时状态预算与占用情况。"""
        if self._kernel is None:
            return {}
        return self._kernel.get_runtime_state_stats()

    def get_runtime_events_snapshot(
        self,
        limit: int = 50,
        event_type: Optional[str] = None,
        source: Optional[str] = None,
        since_seq: Optional[int] = None,
    ) -> Dict[str, Any]:
        """获取运行时事件流快照。"""
        if self._kernel is None:
            return {
                "stats": {},
                "filters": {
                    "limit": max(1, limit),
                    "event_type": event_type,
                    "source": source,
                    "since_seq": since_seq,
                },
                "events": [],
                "truncated": False,
                "next_cursor": since_seq or 0,
            }
        return self._kernel.get_runtime_events_snapshot(
            limit=limit,
            event_type=event_type,
            source=source,
            since_seq=since_seq,
        )

    def get_runtime_events_stats(self) -> Dict[str, Any]:
        """获取运行时事件流统计。"""
        if self._kernel is None:
            return {}
        return self._kernel.get_runtime_events_stats()

    def get_runtime_pressure_snapshot(self, refresh: bool = True) -> Dict[str, Any]:
        """获取运行时压力快照。"""
        if self._kernel is None:
            return {
                "level": "normal",
                "previous_level": "normal",
                "changed": False,
                "reason": "kernel_uninitialized",
                "memory": {},
                "errors": {},
                "limits": {},
            }
        return self._kernel.get_runtime_pressure_snapshot(refresh=refresh)

    def get_runtime_pressure_stats(self) -> Dict[str, Any]:
        """获取运行时压力统计。"""
        if self._kernel is None:
            return {}
        return self._kernel.get_runtime_pressure_stats()

    def get_budget_telemetry_snapshot(self, refresh: bool = True) -> Dict[str, Any]:
        """获取统一预算健康度快照。"""
        if self._kernel is None:
            return {
                "health_score": 100,
                "pressure_level": "normal",
                "alerts": ["kernel_uninitialized"],
                "utilization": {},
                "runtime_state": {},
                "runtime_events": {},
                "artifact_graph": {},
                "runtime_pressure": {},
            }
        return self._kernel.get_budget_telemetry_snapshot(refresh=refresh)

    def get_artifact_graph_snapshot(
        self,
        node_limit: int = 80,
        edge_limit: int = 200,
        node_kind: Optional[str] = None,
    ) -> Dict[str, Any]:
        """获取运行时 artifact graph 快照。"""
        if self._kernel is None:
            return {
                "nodes": [],
                "edges": [],
                "stats": {},
                "filters": {
                    "node_kind": node_kind,
                    "node_limit": max(1, node_limit),
                    "edge_limit": max(1, edge_limit),
                },
                "truncated": {"nodes": False, "edges": False},
            }
        return self._kernel.get_artifact_graph_snapshot(
            node_limit=node_limit,
            edge_limit=edge_limit,
            node_kind=node_kind,
        )

    def get_artifact_graph_stats(self) -> Dict[str, Any]:
        """获取 artifact graph 占用统计。"""
        if self._kernel is None:
            return {}
        return self._kernel.get_artifact_graph_stats()

    async def fetch_all(self, urls: List[str]) -> AgentResponse:
        """批量获取多个页面"""
        results = []
        success_count = 0

        for url in urls:
            result = await self.visit(url)
            if result.success:
                success_count += 1
            results.append({
                "url": url,
                "success": result.success,
                "title": result.data.get("title") if result.data else None,
            })

        return AgentResponse(
            success=True,
            content=f"批量获取完成：{success_count}/{len(urls)} 成功",
            data={"results": results},
        )

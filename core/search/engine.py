"""
搜索引擎模块 - 支持多个搜索引擎的自主搜索
"""
import asyncio
import re
import json
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any, Literal
from datetime import datetime
from enum import Enum
import logging
from urllib.parse import parse_qs, unquote, urljoin, urlparse

try:
    from core.crawler import Crawler, CrawlResult
except ModuleNotFoundError as exc:  # pragma: no cover - optional runtime dependency
    Crawler = None  # type: ignore[assignment]
    CrawlResult = Any  # type: ignore[misc,assignment]
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

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def _build_parser():
    if Parser is None:
        raise RuntimeError(
            "HTML parser runtime is unavailable. Install optional dependencies from requirements.txt."
        ) from _PARSER_IMPORT_ERROR
    return Parser()


class SearchEngine(Enum):
    """支持的搜索引擎"""
    GOOGLE = "google"
    BING = "bing"
    BAIDU = "baidu"
    DUCKDUCKGO = "duckduckgo"
    SOGOU = "sogou"
    GOOGLE_SCHOLAR = "google_scholar"


@dataclass
class SearchResult:
    """单个搜索结果"""
    title: str
    url: str
    snippet: str
    engine: str
    rank: int
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "title": self.title,
            "url": self.url,
            "snippet": self.snippet,
            "engine": self.engine,
            "rank": self.rank,
            "metadata": self.metadata,
        }


@dataclass
class SearchResponse:
    """搜索响应"""
    query: str
    engine: str
    results: List[SearchResult] = field(default_factory=list)
    total_results: int = 0
    search_time: float = 0.0
    error: Optional[str] = None
    timestamp: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "query": self.query,
            "engine": self.engine,
            "results": [r.to_dict() for r in self.results],
            "total_results": self.total_results,
            "search_time": self.search_time,
            "error": self.error,
        }


class SearchEngineClient:
    """搜索引擎客户端 - 不使用 API，通过搜索页面获取结果"""

    # 搜索引擎 URL 模板
    SEARCH_URLS = {
        SearchEngine.GOOGLE: "https://www.google.com/search?q={query}&num={count}&hl=zh-CN",
        SearchEngine.BING: "https://www.bing.com/search?q={query}&count={count}&cc=cn&setlang=zh-CN",
        SearchEngine.BAIDU: "https://www.baidu.com/s?wd={query}&rn={count}&ie=utf-8",
        SearchEngine.DUCKDUCKGO: "https://html.duckduckgo.com/html/?q={query}",
        SearchEngine.SOGOU: "https://www.sogou.com/web?query={query}&num={count}",
        SearchEngine.GOOGLE_SCHOLAR: "https://scholar.google.com/scholar?q={query}&num={count}&hl=zh-CN",
    }
    _ENGINE_BASE_URLS = {
        SearchEngine.GOOGLE: "https://www.google.com",
        SearchEngine.BING: "https://www.bing.com",
        SearchEngine.BAIDU: "https://www.baidu.com",
        SearchEngine.DUCKDUCKGO: "https://duckduckgo.com",
        SearchEngine.SOGOU: "https://www.sogou.com",
        SearchEngine.GOOGLE_SCHOLAR: "https://scholar.google.com",
    }

    # 结果选择器
    RESULT_SELECTORS = {
        SearchEngine.GOOGLE: "div.g",
        SearchEngine.BING: "li.b_algo",
        SearchEngine.BAIDU: "div.c-container",
        SearchEngine.DUCKDUCKGO: "div.result",
        SearchEngine.SOGOU: "div.fb-hint",
        SearchEngine.GOOGLE_SCHOLAR: "div.gs_ri",
    }

    def __init__(self):
        if Crawler is None:
            raise RuntimeError(
                "Search engine runtime is unavailable. Install optional dependencies from requirements.txt."
            ) from _CRAWLER_IMPORT_ERROR
        self._crawler = Crawler()

    async def search(
        self,
        query: str,
        engine: SearchEngine = SearchEngine.BING,
        num_results: int = 10,
    ) -> SearchResponse:
        """
        执行搜索

        Args:
            query: 搜索关键词
            engine: 搜索引擎
            num_results: 结果数量

        Returns:
            SearchResponse: 搜索结果
        """
        start_time = asyncio.get_event_loop().time()

        try:
            # 构建搜索 URL
            url = self.SEARCH_URLS[engine].format(
                query=self._encode_query(query),
                count=num_results,
            )

            # 获取搜索结果页面
            result = await self._crawler.fetch_with_retry(url, retries=2)

            if not result.success:
                return SearchResponse(
                    query=query,
                    engine=engine.value,
                    error=f"Search failed: {result.error}",
                )

            # 解析搜索结果
            results = self._parse_results(result.html, engine)

            search_time = asyncio.get_event_loop().time() - start_time

            return SearchResponse(
                query=query,
                engine=engine.value,
                results=results[:num_results],
                total_results=len(results),
                search_time=search_time,
            )

        except Exception as e:
            logger.exception(f"Error searching with {engine.value}")
            return SearchResponse(
                query=query,
                engine=engine.value,
                error=str(e),
            )

    def _encode_query(self, query: str) -> str:
        """编码查询词"""
        import urllib.parse
        return urllib.parse.quote(query)

    def _normalize_result_url(self, raw_url: str, engine: SearchEngine) -> str:
        """将搜索结果链接标准化为可抓取的绝对 http(s) URL。"""
        url = str(raw_url or "").strip()
        if not url:
            return ""

        lower_url = url.lower()
        if lower_url.startswith(("javascript:", "mailto:", "tel:", "#")):
            return ""

        if url.startswith("/url?") or url.startswith("url?"):
            query_str = url.split("?", 1)[1] if "?" in url else ""
            qs = parse_qs(query_str)
            target = qs.get("q", qs.get("url", [""]))[0]
            if target:
                url = unquote(target)

        if "duckduckgo.com/l/?" in lower_url:
            parsed_ddg = urlparse(url)
            uddg = parse_qs(parsed_ddg.query).get("uddg", [""])[0]
            if uddg:
                url = unquote(uddg)

        parsed = urlparse(url)
        base = self._ENGINE_BASE_URLS.get(engine, "")

        if not parsed.scheme:
            if base:
                url = urljoin(base, url)
                parsed = urlparse(url)
        elif parsed.scheme in {"http", "https"} and not parsed.netloc:
            if base:
                relative = parsed.path or "/"
                if parsed.query:
                    relative = f"{relative}?{parsed.query}"
                if parsed.fragment:
                    relative = f"{relative}#{parsed.fragment}"
                url = urljoin(base, relative)
                parsed = urlparse(url)

        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            return ""
        return url

    def _parse_results(self, html: str, engine: SearchEngine) -> List[SearchResult]:
        """解析搜索结果"""
        try:
            parser = _build_parser().parse(html)
            results = []

            if engine == SearchEngine.GOOGLE:
                results = self._parse_google(parser)
            elif engine == SearchEngine.BING:
                results = self._parse_bing(parser)
            elif engine == SearchEngine.BAIDU:
                results = self._parse_baidu(parser)
            elif engine == SearchEngine.DUCKDUCKGO:
                results = self._parse_duckduckgo(parser)
            elif engine == SearchEngine.SOGOU:
                results = self._parse_sogou(parser)
            elif engine == SearchEngine.GOOGLE_SCHOLAR:
                results = self._parse_scholar(parser)

            return results

        except Exception as e:
            logger.exception(f"Error parsing results for {engine.value}")
            return []

    def _parse_google(self, parser: Parser) -> List[SearchResult]:
        """解析 Google 搜索结果"""
        results = []
        soup = parser.soup

        for i, g in enumerate(soup.select("div.g")):
            title_tag = g.find("h3")
            url_tag = g.find("a", href=True)
            snippet_tag = g.find("div", class_=re.compile(r"VwiC3b|yDYNvb"))

            if title_tag and url_tag:
                normalized_url = self._normalize_result_url(url_tag["href"], SearchEngine.GOOGLE)
                if not normalized_url:
                    continue
                results.append(SearchResult(
                    title=title_tag.get_text(strip=True),
                    url=normalized_url,
                    snippet=snippet_tag.get_text(strip=True) if snippet_tag else "",
                    engine="google",
                    rank=i + 1,
                ))

        return results

    def _parse_bing(self, parser: Parser) -> List[SearchResult]:
        """解析 Bing 搜索结果"""
        results = []
        soup = parser.soup

        for i, algo in enumerate(soup.select("li.b_algo")):
            title_tag = algo.find("h2")
            url_tag = algo.find("a", href=True)
            snippet_tag = algo.find("div", class_=re.compile(r"b_caption|b_desc"))

            if title_tag and url_tag:
                normalized_url = self._normalize_result_url(url_tag["href"], SearchEngine.BING)
                if not normalized_url:
                    continue
                results.append(SearchResult(
                    title=title_tag.get_text(strip=True),
                    url=normalized_url,
                    snippet=snippet_tag.get_text(strip=True) if snippet_tag else "",
                    engine="bing",
                    rank=i + 1,
                ))

        return results

    def _parse_baidu(self, parser: Parser) -> List[SearchResult]:
        """解析百度搜索结果"""
        results = []
        soup = parser.soup

        for i, container in enumerate(soup.select("div.c-container")):
            title_tag = container.find("h3") or container.find("a", attrs={"data-click": True})
            url_tag = container.find("a", href=True)
            snippet_tag = container.find(class_=re.compile(r"c-abstract|abstract"))

            if title_tag and url_tag:
                href = url_tag["href"]
                # 处理百度重定向链接
                if "sogou.com" in href or "baidu.com" in href and "wd=" not in href:
                    continue
                normalized_url = self._normalize_result_url(href, SearchEngine.BAIDU)
                if not normalized_url:
                    continue
                results.append(SearchResult(
                    title=title_tag.get_text(strip=True),
                    url=normalized_url,
                    snippet=snippet_tag.get_text(strip=True) if snippet_tag else "",
                    engine="baidu",
                    rank=i + 1,
                ))

        return results

    def _parse_duckduckgo(self, parser: Parser) -> List[SearchResult]:
        """解析 DuckDuckGo 搜索结果"""
        results = []
        soup = parser.soup

        for i, result in enumerate(soup.select("div.result")):
            title_tag = result.find("a", class_=re.compile(r"result__a"))
            snippet_tag = result.find("a", class_=re.compile(r"result__snippet"))

            if title_tag:
                normalized_url = self._normalize_result_url(
                    title_tag.get("href", ""),
                    SearchEngine.DUCKDUCKGO,
                )
                if not normalized_url:
                    continue
                results.append(SearchResult(
                    title=title_tag.get_text(strip=True),
                    url=normalized_url,
                    snippet=snippet_tag.get_text(strip=True) if snippet_tag else "",
                    engine="duckduckgo",
                    rank=i + 1,
                ))

        return results

    def _parse_sogou(self, parser: Parser) -> List[SearchResult]:
        """解析搜狗搜索结果"""
        results = []
        soup = parser.soup

        for i, item in enumerate(soup.select("div.fb-hint")):
            title_tag = item.find("h3")
            url_tag = item.find("a", href=True)
            snippet_tag = item.find(class_=re.compile(r"fb-abstract|text-lightgray"))

            if title_tag and url_tag:
                normalized_url = self._normalize_result_url(url_tag["href"], SearchEngine.SOGOU)
                if not normalized_url:
                    continue
                results.append(SearchResult(
                    title=title_tag.get_text(strip=True),
                    url=normalized_url,
                    snippet=snippet_tag.get_text(strip=True) if snippet_tag else "",
                    engine="sogou",
                    rank=i + 1,
                ))

        return results

    def _parse_scholar(self, parser: Parser) -> List[SearchResult]:
        """解析 Google Scholar 搜索结果"""
        results = []
        soup = parser.soup

        for i, item in enumerate(soup.select("div.gs_ri")):
            title_tag = item.find("h3", class_=re.compile(r"gs_rt")) or item.find("h3")
            url_tag = title_tag.find("a", href=True) if title_tag else None
            snippet_tag = item.find("div", class_=re.compile(r"gs_rs"))
            author_tag = item.find("div", class_=re.compile(r"gs_a"))

            if title_tag and url_tag:
                normalized_url = self._normalize_result_url(
                    url_tag["href"],
                    SearchEngine.GOOGLE_SCHOLAR,
                )
                if not normalized_url:
                    continue
                metadata = {}
                if author_tag:
                    metadata["authors"] = author_tag.get_text(strip=True)

                results.append(SearchResult(
                    title=title_tag.get_text(strip=True).replace("[PDF]", "").strip(),
                    url=normalized_url,
                    snippet=snippet_tag.get_text(strip=True) if snippet_tag else "",
                    engine="google_scholar",
                    rank=i + 1,
                    metadata=metadata,
                ))

        return results

    async def close(self):
        """关闭爬虫"""
        await self._crawler.close()


class MultiSearchEngine:
    """
    多搜索引擎聚合器

    支持：
    - 单引擎搜索
    - 多引擎并行搜索
    - 智能引擎选择
    - 结果去重和排序
    """

    def __init__(self):
        self._client = SearchEngineClient()
        self._engine_priority = {
            SearchEngine.BING: 1,      # Bing 最稳定
            SearchEngine.GOOGLE: 2,
            SearchEngine.DUCKDUCKGO: 3,
            SearchEngine.BAIDU: 4,     # 百度适合中文
            SearchEngine.SOGOU: 5,
            SearchEngine.GOOGLE_SCHOLAR: 1,  # 学术搜索专用
        }

    async def search(
        self,
        query: str,
        engines: Optional[List[SearchEngine]] = None,
        num_results: int = 10,
        deduplicate: bool = True,
        parallel: bool = True,
    ) -> List[SearchResponse]:
        """
        多引擎搜索

        Args:
            query: 搜索关键词
            engines: 引擎列表，None 则自动选择
            num_results: 每个引擎的结果数量
            deduplicate: 是否去重
            parallel: 是否并行搜索

        Returns:
            List[SearchResponse]: 各引擎的搜索结果
        """
        # 自动选择引擎
        if engines is None:
            engines = self._select_engines(query)

        # 执行搜索
        if parallel:
            tasks = [
                self._client.search(query, engine, num_results)
                for engine in engines
            ]
            responses = await asyncio.gather(*tasks, return_exceptions=True)
            responses = [
                r if isinstance(r, SearchResponse)
                else SearchResponse(query=query, engine=str(e), error=str(r))
                for r, e in zip(responses, engines)
            ]
        else:
            responses = []
            for engine in engines:
                try:
                    response = await self._client.search(query, engine, num_results)
                    responses.append(response)
                except Exception as e:
                    responses.append(SearchResponse(
                        query=query,
                        engine=engine.value,
                        error=str(e),
                    ))

        return responses

    def _select_engines(self, query: str) -> List[SearchEngine]:
        """根据查询自动选择引擎"""
        engines = [SearchEngine.BING, SearchEngine.GOOGLE]

        # 中文查询优先百度
        if re.search(r"[\u4e00-\u9fff]", query):
            engines.insert(1, SearchEngine.BAIDU)

        # 学术相关查询使用 Google Scholar
        if any(kw in query.lower() for kw in ["paper", "research", "论文", "研究", "学术"]):
            engines.append(SearchEngine.GOOGLE_SCHOLAR)

        return engines

    async def search_combined(
        self,
        query: str,
        engines: Optional[List[SearchEngine]] = None,
        total_results: int = 20,
        deduplicate: bool = True,
    ) -> SearchResponse:
        """
        合并多引擎结果

        Args:
            query: 搜索关键词
            engines: 引擎列表
            total_results: 总结果数量
            deduplicate: 是否去重

        Returns:
            SearchResponse: 合并后的结果
        """
        responses = await self.search(query, engines, num_results=total_results)

        # 合并所有结果
        all_results = []
        for response in responses:
            if response.error is None:
                all_results.extend(response.results)

        # 去重
        if deduplicate:
            seen_urls = set()
            unique_results = []
            for result in all_results:
                if result.url not in seen_urls:
                    seen_urls.add(result.url)
                    unique_results.append(result)
            all_results = unique_results

        # 排序（按排名和引擎优先级）
        all_results.sort(key=lambda x: x.rank)

        return SearchResponse(
            query=query,
            engine="combined",
            results=all_results[:total_results],
            total_results=len(all_results),
        )

    async def smart_search(
        self,
        query: str,
        max_depth: int = 2,
    ) -> Dict[str, Any]:
        """
        智能深度搜索：搜索 -> 爬取结果页面 -> 提取信息

        Args:
            query: 搜索关键词
            max_depth: 最大爬取深度

        Returns:
            搜索结果和提取的内容
        """
        # 第一步：搜索获取结果
        search_response = await self.search_combined(query, total_results=10)

        if search_response.error or not search_response.results:
            return {
                "success": False,
                "error": search_response.error or "No results found",
            }

        # 第二步：爬取前几个结果获取内容
        crawled_pages = []
        if Crawler is None:
            raise RuntimeError(
                "Search engine runtime is unavailable. Install optional dependencies from requirements.txt."
            ) from _CRAWLER_IMPORT_ERROR
        crawler = Crawler()

        for i, result in enumerate(search_response.results[:3]):
            try:
                page_result = await crawler.fetch_with_retry(result.url)
                if page_result.success:
                    parser = _build_parser().parse(page_result.html, result.url)
                    extracted = parser.extract()
                    crawled_pages.append({
                        "url": result.url,
                        "title": extracted.title,
                        "content": extracted.text[:2000],
                        "links": extracted.links[:10],
                    })
            except Exception as e:
                logger.warning(f"Failed to crawl {result.url}: {e}")

        await crawler.close()

        # 第三步：提取关键信息
        all_content = "\n\n".join([p["content"] for p in crawled_pages])

        return {
            "success": True,
            "search_results": search_response.to_dict(),
            "crawled_pages": crawled_pages,
            "combined_content": all_content[:10000],
        }

    async def __aenter__(self) -> "MultiSearchEngine":
        """异步上下文管理器入口"""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """异步上下文管理器出口"""
        await self.close()

    async def close(self):
        """关闭"""
        await self._client.close()


# 便捷函数
async def web_search(
    query: str,
    engine: SearchEngine = SearchEngine.BING,
    num_results: int = 10,
) -> SearchResponse:
    """快速搜索"""
    client = SearchEngineClient()
    result = await client.search(query, engine, num_results)
    await client.close()
    return result


async def web_search_multi(
    query: str,
    engines: Optional[List[SearchEngine]] = None,
    num_results: int = 10,
) -> List[SearchResponse]:
    """多引擎搜索"""
    multi = MultiSearchEngine()
    results = await multi.search(query, engines, num_results)
    await multi.close()
    return results


async def web_search_smart(
    query: str,
    max_depth: int = 2,
) -> Dict[str, Any]:
    """智能深度搜索"""
    multi = MultiSearchEngine()
    result = await multi.smart_search(query, max_depth)
    await multi.close()
    return result

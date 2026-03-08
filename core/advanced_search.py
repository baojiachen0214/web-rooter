"""
高级搜索引擎 - 支持多引擎、多语言深度搜索

功能:
- 支持更多搜索引擎 (Yandex, Bilibili, Zhihu, Reddit, Twitter 等)
- 多语言搜索 (中文 + 英文并行)
- 深度搜索模式 (所有引擎并行)
- 社交媒体搜索
- 技术社区搜索
- 内存优化和缓存清理
"""
import asyncio
import json
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any, Literal
from datetime import datetime
from enum import Enum
import logging

from core.crawler import Crawler, CrawlResult
from core.parser import Parser
from core.memory_optimizer import (
    get_session_cleaner,
    mark_result_as_final,
    cleanup_search_session,
    get_memory_optimizer
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class AdvancedSearchEngine(Enum):
    """支持的搜索引擎（扩展版）"""
    # 通用搜索引擎
    GOOGLE = "google"
    BING = "bing"
    BAIDU = "baidu"
    DUCKDUCKGO = "duckduckgo"
    SOGOU = "sogou"
    YANDEX = "yandex"  # 俄罗斯搜索引擎，适合英文和俄文
    Naver = "naver"  # 韩国搜索引擎

    # 英文社区/技术搜索
    GOOGLE_US = "google_us"  # Google 美国版
    BING_US = "bing_us"  # Bing 美国版

    # 社交媒体
    BILIBILI = "bilibili"  # B 站
    ZHIHU = "zhihu"  # 知乎
    WEIBO = "weibo"  # 微博
    REDDIT = "reddit"  # Reddit
    TWITTER = "twitter"  # Twitter/X
    HACKERNEWS = "hackernews"  # Hacker News

    # 技术社区
    GITHUB = "github"  # GitHub
    STACKOVERFLOW = "stackoverflow"  # Stack Overflow
    MEDIUM = "medium"  # Medium

    # 学术搜索
    GOOGLE_SCHOLAR = "google_scholar"
    ARXIV = "arxiv"
    SEMANTIC_SCHOLAR = "semantic_scholar"


@dataclass
class SearchResult:
    """单个搜索结果"""
    title: str
    url: str
    snippet: str
    engine: str
    rank: int
    language: str = "zh"  # 语言标识
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "title": self.title,
            "url": self.url,
            "snippet": self.snippet,
            "engine": self.engine,
            "rank": self.rank,
            "language": self.language,
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


class AdvancedSearchEngineClient:
    """高级搜索引擎客户端"""

    # 搜索引擎 URL 模板（支持多语言）
    SEARCH_URLS = {
        # 通用搜索引擎 - 中文版
        AdvancedSearchEngine.GOOGLE: "https://www.google.com/search?q={query}&num={count}&hl=zh-CN",
        AdvancedSearchEngine.BING: "https://cn.bing.com/search?q={query}&first={count}&cc=cn&setlang=zh-CN",
        AdvancedSearchEngine.BAIDU: "https://www.baidu.com/s?wd={query}&rn={count}&ie=utf-8",
        AdvancedSearchEngine.DUCKDUCKGO: "https://html.duckduckgo.com/html/?q={query}&kl=cn",
        AdvancedSearchEngine.SOGOU: "https://www.sogou.com/web?query={query}&num={count}",

        # 通用搜索引擎 - 英文版
        AdvancedSearchEngine.GOOGLE_US: "https://www.google.com/search?q={query}&num={count}&hl=en&gl=us",
        AdvancedSearchEngine.BING_US: "https://www.bing.com/search?q={query}&count={count}&cc=us&setlang=en",
        AdvancedSearchEngine.YANDEX: "https://yandex.com/search/?text={query}&lr={count}",

        # 社交媒体
        AdvancedSearchEngine.BILIBILI: "https://search.bilibili.com/all?keyword={query}&page={count}",
        AdvancedSearchEngine.ZHIHU: "https://www.zhihu.com/search?type=content&q={query}",
        AdvancedSearchEngine.WEIBO: "https://s.weibo.com/weibo?q={query}",
        AdvancedSearchEngine.REDDIT: "https://www.reddit.com/search/?q={query}&limit={count}",
        AdvancedSearchEngine.TWITTER: "https://twitter.com/search?q={query}&f=live",
        AdvancedSearchEngine.HACKERNEWS: "https://hn.algolia.com/?query={query}&type=story",

        # 技术社区
        AdvancedSearchEngine.GITHUB: "https://github.com/search?q={query}&type=repositories",
        AdvancedSearchEngine.STACKOVERFLOW: "https://stackoverflow.com/search?q={query}",
        AdvancedSearchEngine.MEDIUM: "https://medium.com/search?q={query}",

        # 学术搜索
        AdvancedSearchEngine.GOOGLE_SCHOLAR: "https://scholar.google.com/scholar?q={query}&hl=en&num={count}",
        AdvancedSearchEngine.ARXIV: "https://arxiv.org/search/?query={query}&searchtype=all",
        AdvancedSearchEngine.SEMANTIC_SCHOLAR: "https://www.semanticscholar.org/search?q={query}",
    }

    # 结果选择器
    RESULT_SELECTORS = {
        AdvancedSearchEngine.GOOGLE: "div.g, div.tF2Cxc",
        AdvancedSearchEngine.BING: "li.b_algo",
        AdvancedSearchEngine.BAIDU: "div.c-container, div.result-op",
        AdvancedSearchEngine.DUCKDUCKGO: "div.result",
        AdvancedSearchEngine.SOGOU: "div.fb-hint, div.vmid",
        AdvancedSearchEngine.YANDEX: "li.serp-item",

        # 社交媒体
        AdvancedSearchEngine.BILIBILI: "div.video-card",
        AdvancedSearchEngine.ZHIHU: "div.List-item, div.SearchResult",
        AdvancedSearchEngine.WEIBO: "div.card-wrap",
        AdvancedSearchEngine.REDDIT: "shreddit-post, post-timestamp",
        AdvancedSearchEngine.TWITTER: "article[data-testid='tweet']",
        AdvancedSearchEngine.HACKERNEWS: "span.titleline",

        # 技术社区
        AdvancedSearchEngine.GITHUB: "div.repo-list-item",
        AdvancedSearchEngine.STACKOVERFLOW: "div.question-summary",
        AdvancedSearchEngine.MEDIUM: "div.postArticle",

        # 学术搜索
        AdvancedSearchEngine.GOOGLE_SCHOLAR: "div.gs_ri",
        AdvancedSearchEngine.ARXIV: "div.list-results li",
        AdvancedSearchEngine.SEMANTIC_SCHOLAR: "div.search-result",
    }

    # 标题选择器
    TITLE_SELECTORS = {
        AdvancedSearchEngine.GOOGLE: "h3",
        AdvancedSearchEngine.BING: "h2 a",
        AdvancedSearchEngine.BAIDU: "h3 a, c-title a",
        AdvancedSearchEngine.DUCKDUCKGO: "a.result__title",
        AdvancedSearchEngine.SOGOU: "h3 a, a[href*='wenwen']",
        AdvancedSearchEngine.YANDEX: "h2 a",

        AdvancedSearchEngine.BILIBILI: "a[href*='/video/']",
        AdvancedSearchEngine.ZHIHU: "h2 a, .ContentItem-title a",
        AdvancedSearchEngine.WEIBO: "p.txt a",
        AdvancedSearchEngine.REDDIT: "h3 a, shreddit-title a",
        AdvancedSearchEngine.TWITTER: "[data-testid='tweetText']",
        AdvancedSearchEngine.HACKERNEWS: "a.storylink",

        AdvancedSearchEngine.GITHUB: "a.v-align-middle",
        AdvancedSearchEngine.STACKOVERFLOW: "h3 a",
        AdvancedSearchEngine.MEDIUM: "h2 a",

        AdvancedSearchEngine.GOOGLE_SCHOLAR: "h3 a",
        AdvancedSearchEngine.ARXIV: "a",
        AdvancedSearchEngine.SEMANTIC_SCHOLAR: "h3 a",
    }

    # URL 选择器
    URL_SELECTORS = {
        AdvancedSearchEngine.GOOGLE: "a",
        AdvancedSearchEngine.BING: "a",
        AdvancedSearchEngine.BAIDU: "a",
        AdvancedSearchEngine.DUCKDUCKGO: "a.result__url",
        AdvancedSearchEngine.SOGOU: "a",
        AdvancedSearchEngine.YANDEX: "a",

        AdvancedSearchEngine.BILIBILI: "a[href*='/video/']",
        AdvancedSearchEngine.ZHIHU: "a",
        AdvancedSearchEngine.WEIBO: "a",
        AdvancedSearchEngine.REDDIT: "a",
        AdvancedSearchEngine.TWITTER: "a",
        AdvancedSearchEngine.HACKERNEWS: "a.storylink",

        AdvancedSearchEngine.GITHUB: "a",
        AdvancedSearchEngine.STACKOVERFLOW: "a",
        AdvancedSearchEngine.MEDIUM: "a",

        AdvancedSearchEngine.GOOGLE_SCHOLAR: "a",
        AdvancedSearchEngine.ARXIV: "a",
        AdvancedSearchEngine.SEMANTIC_SCHOLAR: "a",
    }

    # 摘要选择器
    SNIPPET_SELECTORS = {
        AdvancedSearchEngine.GOOGLE: "span.aCOpRe, div.VwiC3b",
        AdvancedSearchEngine.BING: "p.b_algoSlug",
        AdvancedSearchEngine.BAIDU: "span.c-color-gray2",
        AdvancedSearchEngine.DUCKDUCKGO: "a.result__snippet",
        AdvancedSearchEngine.SOGOU: "p.txt-info",
        AdvancedSearchEngine.YANDEX: "div.Path",

        AdvancedSearchEngine.BILIBILI: "span.desc",
        AdvancedSearchEngine.ZHIHU: "div.RichText, div.excerpt",
        AdvancedSearchEngine.WEIBO: "p.txt",
        AdvancedSearchEngine.REDDIT: "shreddit-post",
        AdvancedSearchEngine.TWITTER: "[data-testid='tweetText']",
        AdvancedSearchEngine.HACKERNEWS: "span.score",

        AdvancedSearchEngine.GITHUB: "p.mb-1",
        AdvancedSearchEngine.STACKOVERFLOW: "div.excerpt",
        AdvancedSearchEngine.MEDIUM: "p",

        AdvancedSearchEngine.GOOGLE_SCHOLAR: "div.gs_abs",
        AdvancedSearchEngine.ARXIV: "span.search-results-data",
        AdvancedSearchEngine.SEMANTIC_SCHOLAR: "p",
    }

    def __init__(self):
        self._crawler = Crawler()
        self._headers = {
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        }

    async def search(
        self,
        engine: AdvancedSearchEngine,
        query: str,
        num_results: int = 10,
        language: str = "zh",  # 'zh' 或 'en'
    ) -> SearchResponse:
        """执行搜索"""
        start_time = datetime.now()

        # 构建搜索 URL
        url_template = self.SEARCH_URLS.get(engine)
        if not url_template:
            return SearchResponse(
                query=query,
                engine=engine.value,
                error=f"不支持的搜索引擎：{engine.value}",
            )

        # 根据语言调整 URL
        if language == "en" and engine in [AdvancedSearchEngine.GOOGLE, AdvancedSearchEngine.BING]:
            # 使用英文版
            engine = AdvancedSearchEngine.GOOGLE_US if engine == AdvancedSearchEngine.GOOGLE else AdvancedSearchEngine.BING_US
            url_template = self.SEARCH_URLS[engine]

        search_url = url_template.format(query=query, count=num_results)

        try:
            # 使用 crawler 获取搜索结果
            result = await self._crawler.fetch(
                search_url,
                headers=self._headers,
            )

            if not result.success:
                return SearchResponse(
                    query=query,
                    engine=engine.value,
                    error=f"搜索失败：{result.error}",
                )

            # 解析结果
            results = self._parse_results(engine, result.html)

            # 设置语言标识
            for r in results:
                r.language = language

            search_time = (datetime.now() - start_time).total_seconds()

            return SearchResponse(
                query=query,
                engine=engine.value,
                results=results,
                total_results=len(results),
                search_time=search_time,
            )

        except Exception as e:
            logger.exception(f"搜索失败 {engine.value}: {e}")
            return SearchResponse(
                query=query,
                engine=engine.value,
                error=str(e),
            )

    def _parse_results(self, engine: AdvancedSearchEngine, html: str) -> List[SearchResult]:
        """解析搜索结果"""
        parser = Parser().parse(html)
        results = []

        selector = self.RESULT_SELECTORS.get(engine)
        if not selector:
            return []

        items = parser.select(selector)

        title_selector = self.TITLE_SELECTORS.get(engine)
        url_selector = self.URL_SELECTORS.get(engine)
        snippet_selector = self.SNIPPET_SELECTORS.get(engine)

        for i, item in enumerate(items[:10]):
            try:
                # 提取标题
                title = ""
                if title_selector:
                    title_elem = item.select_one(title_selector) if hasattr(item, 'select_one') else item.find()
                    if title_elem:
                        title = title_elem.get_text(strip=True)[:200]

                # 提取 URL
                url = ""
                if url_selector:
                    url_elem = item.select_one(url_selector) if hasattr(item, 'select_one') else item.find()
                    if url_elem and url_elem.get('href'):
                        url = url_elem.get('href', '')

                # 提取摘要
                snippet = ""
                if snippet_selector:
                    snippet_elem = item.select_one(snippet_selector) if hasattr(item, 'select_one') else item.find()
                    if snippet_elem:
                        snippet = snippet_elem.get_text(strip=True)[:500]

                if title and url:
                    results.append(SearchResult(
                        title=title,
                        url=url,
                        snippet=snippet,
                        engine=engine.value,
                        rank=i + 1,
                    ))
            except Exception as e:
                logger.debug(f"解析结果失败：{e}")
                continue

        return results


class DeepSearchEngine:
    """
    深度搜索引擎 - 并行多引擎搜索

    功能:
    - 所有引擎并行搜索
    - 中英文双语搜索
    - 结果去重合并
    - 按来源分类
    - 内存优化和缓存清理
    """

    def __init__(self, auto_cleanup: bool = True):
        self._client = AdvancedSearchEngineClient()
        self._crawler = Crawler(use_cache=True)
        self._auto_cleanup = auto_cleanup
        self._session_cleaner = get_session_cleaner()

    async def deep_search(
        self,
        query: str,
        num_results: int = 20,
        use_english: bool = True,  # 是否同时使用英文搜索
        engines: Optional[List[AdvancedSearchEngine]] = None,
        crawl_top: int = 0,  # 爬取前 N 个结果
        auto_cleanup: Optional[bool] = None,  # 搜索后是否自动清理缓存
    ) -> Dict[str, Any]:
        """
        深度搜索

        Args:
            query: 搜索关键词
            num_results: 每个引擎的结果数量
            use_english: 是否同时使用英文搜索
            engines: 指定使用的引擎（默认使用全部）
            crawl_top: 爬取前 N 个结果
            auto_cleanup: 搜索后是否自动清理缓存（默认使用实例设置）

        Returns:
            搜索结果字典
        """
        if engines is None:
            # 默认使用通用搜索引擎
            engines = [
                AdvancedSearchEngine.GOOGLE,
                AdvancedSearchEngine.BING,
                AdvancedSearchEngine.BAIDU,
                AdvancedSearchEngine.DUCKDUCKGO,
            ]

        tasks = []

        # 中文版搜索
        for engine in engines:
            tasks.append(self._client.search(engine, query, num_results, language="zh"))

        # 英文版搜索
        if use_english:
            english_query = self._translate_query(query)
            for engine in engines:
                if engine in [AdvancedSearchEngine.GOOGLE, AdvancedSearchEngine.BING, AdvancedSearchEngine.YANDEX]:
                    tasks.append(self._client.search(engine, english_query, num_results, language="en"))

        # 并行执行所有搜索
        responses = await asyncio.gather(*tasks, return_exceptions=True)

        # 合并结果
        all_results = []
        errors = []

        for response in responses:
            if isinstance(response, Exception):
                errors.append(str(response))
            elif isinstance(response, SearchResponse):
                if response.error:
                    errors.append(response.error)
                else:
                    all_results.extend(response.results)

        # 去重
        seen_urls = set()
        unique_results = []
        for result in all_results:
            if result.url not in seen_urls:
                seen_urls.add(result.url)
                unique_results.append(result)

        # 按排名排序
        unique_results.sort(key=lambda x: x.rank)

        # 爬取前 N 个结果
        crawled_content = []
        if crawl_top > 0:
            crawl_tasks = []
            for result in unique_results[:crawl_top]:
                crawl_tasks.append(self._crawler.fetch(result.url))

            crawl_results = await asyncio.gather(*crawl_tasks, return_exceptions=True)

            for i, (result, crawl_result) in enumerate(zip(unique_results[:crawl_top], crawl_results)):
                if isinstance(crawl_result, CrawlResult) and crawl_result.success:
                    crawled_content.append({
                        "url": result.url,
                        "title": result.title,
                        "content": crawl_result.html[:10000],
                    })

        # 构建最终结果
        final_result = {
            "success": True,
            "query": query,
            "total_results": len(unique_results),
            "results": [r.to_dict() for r in unique_results],
            "crawled_content": crawled_content,
            "errors": errors,
            "search_summary": f"使用 {len(engines)} 个引擎搜索，共找到 {len(unique_results)} 条结果",
        }

        # 标记最终结果
        result_key = f"deep_search:{query}:{datetime.now().strftime('%Y%m%d%H%M%S')}"
        mark_result_as_final(result_key)

        # 自动清理缓存
        cleanup_flag = auto_cleanup if auto_cleanup is not None else self._auto_cleanup
        if cleanup_flag:
            await cleanup_search_session(keep_final_results=True)
            logger.info(f"Search session cleanup completed for query: {query}")

        return final_result

    def _translate_query(self, query: str) -> str:
        """
        简单翻译查询（关键词级别）

        实际应用中可以调用翻译 API
        这里只做简单的中英文对照
        """
        # 常见技术术语中英文对照
        translations = {
            "苹果": "Apple",
            "发布会": "event keynote",
            "手机": "smartphone iPhone",
            "电脑": "computer Mac",
            "芯片": "chip processor M-series",
            "用户评价": "user review reaction",
            "最新": "latest 2025 2024",
            "新闻": "news update",
            "怎么样": "review opinion",
            "好不好": "worth buying",
        }

        result = query
        for cn, en in translations.items():
            result = result.replace(cn, f"{cn} {en}")

        # 如果查询主要是中文，添加英文关键词
        if any(c in query for c in "的中文"):
            result = f"{query} English version"

        return result


# 便捷函数
async def search_all(
    query: str,
    num_results: int = 10,
    use_english: bool = True,
    crawl_top: int = 3,
) -> Dict[str, Any]:
    """
    便捷函数：使用所有引擎搜索

    Args:
        query: 搜索关键词
        num_results: 结果数量
        use_english: 是否使用英文搜索
        crawl_top: 爬取前 N 个结果

    Returns:
        搜索结果
    """
    deep_search = DeepSearchEngine()
    return await deep_search.deep_search(
        query,
        num_results=num_results,
        use_english=use_english,
        crawl_top=crawl_top,
    )


async def search_social_media(
    query: str,
    platforms: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    搜索社交媒体

    Args:
        query: 搜索关键词
        platforms: 指定平台（默认全部）

    Returns:
        搜索结果
    """
    if platforms is None:
        platforms = ["bilibili", "zhihu", "weibo", "reddit", "twitter"]

    engines = []
    platform_map = {
        "bilibili": AdvancedSearchEngine.BILIBILI,
        "zhihu": AdvancedSearchEngine.ZHIHU,
        "weibo": AdvancedSearchEngine.WEIBO,
        "reddit": AdvancedSearchEngine.REDDIT,
        "twitter": AdvancedSearchEngine.TWITTER,
        "hackernews": AdvancedSearchEngine.HACKERNEWS,
    }

    for platform in platforms:
        if platform in platform_map:
            engines.append(platform_map[platform])

    deep_search = DeepSearchEngine()
    return await deep_search.deep_search(
        query,
        num_results=10,
        use_english=False,
        engines=engines,
    )


async def search_tech(
    query: str,
    sources: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    搜索技术内容

    Args:
        query: 搜索关键词
        sources: 指定来源（默认全部）

    Returns:
        搜索结果
    """
    if sources is None:
        sources = ["github", "stackoverflow", "medium", "hackernews"]

    engines = []
    source_map = {
        "github": AdvancedSearchEngine.GITHUB,
        "stackoverflow": AdvancedSearchEngine.STACKOVERFLOW,
        "medium": AdvancedSearchEngine.MEDIUM,
        "hackernews": AdvancedSearchEngine.HACKERNEWS,
    }

    for source in sources:
        if source in source_map:
            engines.append(source_map[source])

    deep_search = DeepSearchEngine()
    return await deep_search.deep_search(
        query,
        num_results=15,
        use_english=True,  # 技术内容默认用英文搜索
        engines=engines,
    )

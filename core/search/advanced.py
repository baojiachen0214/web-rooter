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
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, List, Dict, Any, Literal
from datetime import datetime
from enum import Enum
import logging
from urllib.parse import parse_qs, parse_qsl, quote, quote_plus, unquote, urlencode, urljoin, urlparse, urlunparse

from core.search.engine_config import ConfigLoader
from core.memory_optimizer import (
    get_session_cleaner,
    mark_result_as_final,
    cleanup_search_session,
    get_memory_optimizer
)
from core.citation import build_web_citations, build_comparison_summary, format_reference_block
from core.global_context import get_global_deep_context
from core.postprocess import PostProcessContext, run_post_processors
from core.auth_profiles import get_auth_profile_registry

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

try:
    from core.crawler import Crawler, CrawlResult
except ModuleNotFoundError as exc:  # pragma: no cover - optional runtime dependency
    Crawler = None  # type: ignore[assignment]
    CrawlResult = Any  # type: ignore[misc,assignment]
    _CRAWLER_IMPORT_ERROR: Optional[Exception] = exc
else:
    _CRAWLER_IMPORT_ERROR = None

try:
    from core.browser import BrowserManager
except ModuleNotFoundError as exc:  # pragma: no cover - optional runtime dependency
    BrowserManager = None  # type: ignore[assignment]
    _BROWSER_IMPORT_ERROR: Optional[Exception] = exc
else:
    _BROWSER_IMPORT_ERROR = None

try:
    from core.parser import Parser
except ModuleNotFoundError as exc:  # pragma: no cover - optional runtime dependency
    Parser = None  # type: ignore[assignment]
    _PARSER_IMPORT_ERROR: Optional[Exception] = exc
else:
    _PARSER_IMPORT_ERROR = None


def _build_parser():
    if Parser is None:
        raise RuntimeError(
            "HTML parser runtime is unavailable. Install optional dependencies from requirements.txt."
        ) from _PARSER_IMPORT_ERROR
    return Parser()


class AdvancedSearchEngine(Enum):
    """支持的搜索引擎（扩展版）"""
    # 通用搜索引擎
    GOOGLE = "google"
    BING = "bing"
    BAIDU = "baidu"
    QUARK = "quark"
    DUCKDUCKGO = "duckduckgo"
    SOGOU = "sogou"
    YANDEX = "yandex"  # 俄罗斯搜索引擎，适合英文和俄文
    Naver = "naver"  # 韩国搜索引擎

    # 英文社区/技术搜索
    GOOGLE_US = "google_us"  # Google 美国版
    BING_US = "bing_us"  # Bing 美国版

    # 社交媒体
    XIAOHONGSHU = "xiaohongshu"  # 小红书
    BILIBILI = "bilibili"  # B 站
    ZHIHU = "zhihu"  # 知乎
    TIEBA = "tieba"  # 百度贴吧
    DOUYIN = "douyin"  # 抖音
    WEIBO = "weibo"  # 微博
    REDDIT = "reddit"  # Reddit
    TWITTER = "twitter"  # Twitter/X
    HACKERNEWS = "hackernews"  # Hacker News

    # 电商与本地生活
    TAOBAO = "taobao"  # 淘宝
    JD = "jd"  # 京东
    PINDUODUO = "pinduoduo"  # 拼多多
    MEITUAN = "meituan"  # 美团

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

    _PATH_QUERY_ENGINES = {
        AdvancedSearchEngine.DOUYIN,
        AdvancedSearchEngine.MEITUAN,
    }

    # 搜索引擎 URL 模板（支持多语言）
    SEARCH_URLS = {
        # 通用搜索引擎 - 中文版
        AdvancedSearchEngine.GOOGLE: "https://www.google.com/search?q={query}&num={count}&hl=zh-CN",
        AdvancedSearchEngine.BING: "https://cn.bing.com/search?q={query}&first={count}&cc=cn&setlang=zh-CN",
        AdvancedSearchEngine.BAIDU: "https://www.baidu.com/s?wd={query}&rn={count}&ie=utf-8",
        AdvancedSearchEngine.QUARK: "https://www.quark.cn/s?q={query}",
        AdvancedSearchEngine.DUCKDUCKGO: "https://html.duckduckgo.com/html/?q={query}&kl=cn",
        AdvancedSearchEngine.SOGOU: "https://www.sogou.com/web?query={query}&num={count}",

        # 通用搜索引擎 - 英文版
        AdvancedSearchEngine.GOOGLE_US: "https://www.google.com/search?q={query}&num={count}&hl=en&gl=us",
        AdvancedSearchEngine.BING_US: "https://www.bing.com/search?q={query}&count={count}&cc=us&setlang=en",
        AdvancedSearchEngine.YANDEX: "https://yandex.com/search/?text={query}&lr={count}",

        # 社交媒体
        AdvancedSearchEngine.XIAOHONGSHU: "https://www.xiaohongshu.com/search_result?keyword={query}&source=web_explore_feed",
        AdvancedSearchEngine.BILIBILI: "https://search.bilibili.com/all?keyword={query}",
        AdvancedSearchEngine.ZHIHU: "https://www.zhihu.com/search?type=content&q={query}",
        AdvancedSearchEngine.TIEBA: "https://tieba.baidu.com/f/search/res?ie=utf-8&qw={query}",
        AdvancedSearchEngine.DOUYIN: "https://www.douyin.com/search/{query}",
        AdvancedSearchEngine.WEIBO: "https://s.weibo.com/weibo?q={query}",
        AdvancedSearchEngine.REDDIT: "https://www.reddit.com/search/?q={query}&limit={count}",
        AdvancedSearchEngine.TWITTER: "https://twitter.com/search?q={query}&f=live",
        AdvancedSearchEngine.HACKERNEWS: "https://hn.algolia.com/?query={query}&type=story",

        # 电商与本地生活
        AdvancedSearchEngine.TAOBAO: "https://s.taobao.com/search?q={query}",
        AdvancedSearchEngine.JD: "https://search.jd.com/Search?keyword={query}&enc=utf-8",
        AdvancedSearchEngine.PINDUODUO: "https://mobile.yangkeduo.com/search_result.html?search_key={query}",
        AdvancedSearchEngine.MEITUAN: "https://www.meituan.com/s/{query}/",

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
        AdvancedSearchEngine.QUARK: "div[class*='result'], div[class*='result-item'], .search-content .pc-s-grid-content-left-content",
        AdvancedSearchEngine.DUCKDUCKGO: "div.result",
        AdvancedSearchEngine.SOGOU: "div.fb-hint, div.vmid",
        AdvancedSearchEngine.YANDEX: "li.serp-item",

        # 社交媒体
        AdvancedSearchEngine.BILIBILI: "div.video-card, .bili-video-card, .video-list-item, .bili-video-card__wrap",
        AdvancedSearchEngine.ZHIHU: "div.List-item, div.SearchResult",
        AdvancedSearchEngine.WEIBO: "div.card-wrap",
        AdvancedSearchEngine.REDDIT: "shreddit-post, post-timestamp",
        AdvancedSearchEngine.TWITTER: "article[data-testid='tweet']",
        AdvancedSearchEngine.HACKERNEWS: "span.titleline",
        AdvancedSearchEngine.XIAOHONGSHU: "section.note-item, .note-item, .feeds-container section",
        AdvancedSearchEngine.TIEBA: "li.j_thread_list, ul#thread_list li",
        AdvancedSearchEngine.DOUYIN: "div[data-e2e='search-card'], a[href*='/video/']",

        # 电商与本地生活
        AdvancedSearchEngine.TAOBAO: "div.items div.item, div[data-category='auctions'], div.item.J_MouserOnverReq",
        AdvancedSearchEngine.JD: "li.gl-item, .gl-warp .gl-item",
        AdvancedSearchEngine.PINDUODUO: "div.goods-item, a[href*='goods.html'], a[href*='yangkeduo.com/goods']",
        AdvancedSearchEngine.MEITUAN: "div.common-list-main li, div.search-list-item, a[href*='meituan.com']",

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
        AdvancedSearchEngine.QUARK: "a.qk-link-wrapper.qk-link-action-hover, a.qk-link-wrapper, a[href^='http']",
        AdvancedSearchEngine.DUCKDUCKGO: "a.result__title",
        AdvancedSearchEngine.SOGOU: "h3 a, a[href*='wenwen']",
        AdvancedSearchEngine.YANDEX: "h2 a",

        AdvancedSearchEngine.BILIBILI: "a[href*='/video/'] h3, .bili-video-card__info--tit, a[href*='/video/']",
        AdvancedSearchEngine.ZHIHU: "h2 a, .ContentItem-title a",
        AdvancedSearchEngine.WEIBO: "p.txt a",
        AdvancedSearchEngine.REDDIT: "h3 a, shreddit-title a",
        AdvancedSearchEngine.TWITTER: "[data-testid='tweetText']",
        AdvancedSearchEngine.HACKERNEWS: "a.storylink",
        AdvancedSearchEngine.XIAOHONGSHU: "a[href*='/explore/'], .title span, .note-item .title",
        AdvancedSearchEngine.TIEBA: "a.j_th_tit, a[href*='/p/']",
        AdvancedSearchEngine.DOUYIN: "a[href*='/video/'] [data-e2e*='desc'], a[href*='/video/'] p, a[href*='/video/'] span",

        # 电商与本地生活
        AdvancedSearchEngine.TAOBAO: "a.J_ClickStat, a.title, a[title]",
        AdvancedSearchEngine.JD: ".p-name a em, .p-name a",
        AdvancedSearchEngine.PINDUODUO: ".goods-name, a[href*='goods'] span, a[href*='goods']",
        AdvancedSearchEngine.MEITUAN: "h3, .title, a",

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
        AdvancedSearchEngine.QUARK: "a.qk-link-wrapper.qk-link-action-hover[href], a.qk-link-wrapper[href], a[href^='http']",
        AdvancedSearchEngine.DUCKDUCKGO: "a.result__url",
        AdvancedSearchEngine.SOGOU: "a",
        AdvancedSearchEngine.YANDEX: "a",

        AdvancedSearchEngine.BILIBILI: "a[href*='/video/']",
        AdvancedSearchEngine.ZHIHU: "a",
        AdvancedSearchEngine.WEIBO: "a",
        AdvancedSearchEngine.REDDIT: "a",
        AdvancedSearchEngine.TWITTER: "a",
        AdvancedSearchEngine.HACKERNEWS: "a.storylink",
        AdvancedSearchEngine.XIAOHONGSHU: "a[href*='/explore/'], a[href*='/discovery/item/']",
        AdvancedSearchEngine.TIEBA: "a.j_th_tit, a[href*='/p/']",
        AdvancedSearchEngine.DOUYIN: "a[href*='/video/'], a[href*='douyin.com']",

        # 电商与本地生活
        AdvancedSearchEngine.TAOBAO: "a[href*='item.taobao.com'], a[href*='detail.tmall.com'], a.J_ClickStat",
        AdvancedSearchEngine.JD: ".p-name a[href]",
        AdvancedSearchEngine.PINDUODUO: "a[href*='goods'], a[href*='yangkeduo.com']",
        AdvancedSearchEngine.MEITUAN: "a[href]",

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
        AdvancedSearchEngine.QUARK: "div[class*='desc'], p",
        AdvancedSearchEngine.DUCKDUCKGO: "a.result__snippet",
        AdvancedSearchEngine.SOGOU: "p.txt-info",
        AdvancedSearchEngine.YANDEX: "div.Path",

        AdvancedSearchEngine.BILIBILI: "span.desc, .bili-video-card__info--desc, p",
        AdvancedSearchEngine.ZHIHU: "div.RichText, div.excerpt",
        AdvancedSearchEngine.WEIBO: "p.txt",
        AdvancedSearchEngine.REDDIT: "shreddit-post",
        AdvancedSearchEngine.TWITTER: "[data-testid='tweetText']",
        AdvancedSearchEngine.HACKERNEWS: "span.score",
        AdvancedSearchEngine.XIAOHONGSHU: ".desc, .note-text, .content",
        AdvancedSearchEngine.TIEBA: ".threadlist_abs, .threadlist_text, .threadlist_rep_num",
        AdvancedSearchEngine.DOUYIN: "a[href*='/video/'] p, a[href*='/video/'] span",

        # 电商与本地生活
        AdvancedSearchEngine.TAOBAO: ".deal-cnt, .shop, .ctx-box",
        AdvancedSearchEngine.JD: ".p-shop a, .p-commit, .p-price",
        AdvancedSearchEngine.PINDUODUO: ".sales, .price, span",
        AdvancedSearchEngine.MEITUAN: "p, .desc, .sub-title",

        AdvancedSearchEngine.GITHUB: "p.mb-1",
        AdvancedSearchEngine.STACKOVERFLOW: "div.excerpt",
        AdvancedSearchEngine.MEDIUM: "p",

        AdvancedSearchEngine.GOOGLE_SCHOLAR: "div.gs_abs",
        AdvancedSearchEngine.ARXIV: "span.search-results-data",
        AdvancedSearchEngine.SEMANTIC_SCHOLAR: "p",
    }

    def __init__(self):
        if Crawler is None:
            raise RuntimeError(
                "Advanced search runtime is unavailable. Install optional dependencies from requirements.txt."
            ) from _CRAWLER_IMPORT_ERROR
        self._crawler = Crawler()
        self._browser_manager: Optional[BrowserManager] = None
        self._browser_lock = asyncio.Lock()

    async def close(self):
        """释放内部 crawler 资源。"""
        if self._browser_manager:
            await self._browser_manager.close()
            self._browser_manager = None
        await self._crawler.close()

    async def _ensure_browser_manager(self):
        """按需初始化浏览器管理器（用于搜索结果解析兜底）。"""
        if self._browser_manager is not None:
            return
        async with self._browser_lock:
            if self._browser_manager is None:
                if BrowserManager is None:
                    raise RuntimeError(
                        "Browser runtime is unavailable. Install optional dependencies from requirements.txt."
                    ) from _BROWSER_IMPORT_ERROR
                self._browser_manager = BrowserManager()
                await self._browser_manager.start("search-fallback")

    async def search(
        self,
        engine: AdvancedSearchEngine,
        query: str,
        num_results: int = 10,
        language: str = "zh",  # 'zh' 或 'en'
    ) -> SearchResponse:
        """执行搜索"""
        start_time = datetime.now()

        if engine not in self.SEARCH_URLS:
            return SearchResponse(
                query=query,
                engine=engine.value,
                error=f"不支持的搜索引擎：{engine.value}",
            )

        # 根据语言调整引擎
        if language == "en" and engine in [AdvancedSearchEngine.GOOGLE, AdvancedSearchEngine.BING]:
            engine = AdvancedSearchEngine.GOOGLE_US if engine == AdvancedSearchEngine.GOOGLE else AdvancedSearchEngine.BING_US
        url_templates = _get_engine_search_url_templates(engine)
        if not url_templates:
            return SearchResponse(
                query=query,
                engine=engine.value,
                error=f"未找到可用搜索入口模板：{engine.value}",
            )

        try:
            candidate_urls: List[str] = []
            for template in url_templates:
                if "{query}" not in template:
                    continue
                encoded_query = quote(query, safe="") if engine in self._PATH_QUERY_ENGINES else quote_plus(query)
                try:
                    search_url = template.format(query=encoded_query, count=num_results)
                except Exception:
                    continue
                if search_url and search_url not in candidate_urls:
                    candidate_urls.append(search_url)

            if not candidate_urls:
                return SearchResponse(
                    query=query,
                    engine=engine.value,
                    error=f"搜索入口模板不可用：{engine.value}",
                )

            http_attempt_errors: List[str] = []
            any_http_failure = False
            for search_url in candidate_urls:
                result = await self._crawler.fetch_with_retry(search_url, retries=2)
                if result.success:
                    parsed_results = self._parse_results(engine, result.html)
                    if parsed_results:
                        for r in parsed_results:
                            r.language = language
                            r.metadata.setdefault("fetch_mode", "http")
                            r.metadata.setdefault("search_url", search_url)

                        search_time = (datetime.now() - start_time).total_seconds()
                        return SearchResponse(
                            query=query,
                            engine=engine.value,
                            results=parsed_results,
                            total_results=len(parsed_results),
                            search_time=search_time,
                        )

                    http_attempt_errors.append(f"http_empty:{search_url}")
                    logger.info(
                        "HTTP search got 0 parsed results for %s via %s",
                        engine.value,
                        search_url,
                    )
                    continue

                any_http_failure = True
                http_attempt_errors.append(f"http_failed:{search_url}:{result.error or result.status_code}")
                logger.info(
                    "HTTP search failed for %s via %s (%s)",
                    engine.value,
                    search_url,
                    result.error or result.status_code,
                )

            # 兜底：配置驱动浏览器搜索（playwright-search-mcp 风格）
            browser_attempt_errors: List[str] = []
            browser_max_urls = max(1, int(os.getenv("WEB_ROOTER_BROWSER_URL_CANDIDATES", "2")))
            for search_url in candidate_urls[:browser_max_urls]:
                fallback = await self._search_with_browser_configured(
                    engine=engine,
                    query=query,
                    search_url=search_url,
                    num_results=num_results,
                    language=language,
                )

                if fallback.error is None and fallback.results:
                    for item in fallback.results:
                        item.metadata.setdefault("search_url", search_url)
                    return fallback

                if fallback.error:
                    browser_attempt_errors.append(f"{search_url}:{fallback.error}")

            error_prefix = "HTTP搜索失败" if any_http_failure else "HTTP搜索结果为空"
            fallback_error_text = "; ".join(browser_attempt_errors[:2]) if browser_attempt_errors else "浏览器兜底未解析到结果"
            return SearchResponse(
                query=query,
                engine=engine.value,
                error=f"{error_prefix}; 浏览器兜底失败：{fallback_error_text}",
            )

        except Exception as e:
            logger.exception(f"搜索失败 {engine.value}: {e}")
            return SearchResponse(
                query=query,
                engine=engine.value,
                error=str(e),
            )

    async def _search_with_browser_configured(
        self,
        engine: AdvancedSearchEngine,
        query: str,
        search_url: str,
        num_results: int,
        language: str,
    ) -> SearchResponse:
        """
        使用配置驱动浏览器搜索做兜底。
        参考 playwright-search-mcp 的 ConfigLoader + UniversalResultParser 架构。
        """
        from core.search.engine_base import ConfigurableSearchEngine

        engine_map = {
            AdvancedSearchEngine.GOOGLE: "google",
            AdvancedSearchEngine.GOOGLE_US: "google",
            AdvancedSearchEngine.BING: "bing",
            AdvancedSearchEngine.BING_US: "bing",
            AdvancedSearchEngine.BAIDU: "baidu",
            AdvancedSearchEngine.QUARK: "quark",
            AdvancedSearchEngine.DUCKDUCKGO: "duckduckgo",
            AdvancedSearchEngine.XIAOHONGSHU: "xiaohongshu",
            AdvancedSearchEngine.BILIBILI: "bilibili",
            AdvancedSearchEngine.ZHIHU: "zhihu",
        }
        engine_id = engine_map.get(engine)
        if not engine_id:
            return await self._search_with_browser_generic(
                engine=engine,
                query=query,
                search_url=search_url,
                num_results=num_results,
                language=language,
            )

        config_loader = ConfigLoader.get_instance()
        if not config_loader.is_engine_supported(engine_id):
            return await self._search_with_browser_generic(
                engine=engine,
                query=query,
                search_url=search_url,
                num_results=num_results,
                language=language,
            )

        await self._ensure_browser_manager()
        searcher = ConfigurableSearchEngine(
            engine_id=engine_id,
            browser_manager=self._browser_manager,
            options={"save_html": False},
        )
        result = await searcher.search(query, limit=num_results)
        if result.error:
            return SearchResponse(
                query=query,
                engine=engine.value,
                error=result.error,
            )

        parsed_results: List[SearchResult] = []
        for idx, item in enumerate(result.results[:num_results], 1):
            raw_url = item.get("link") or item.get("url") or ""
            normalized_url = self._normalize_result_url(raw_url, engine)
            title = (item.get("title") or "").strip()
            if title and normalized_url:
                parsed_results.append(
                    SearchResult(
                        title=title,
                        url=normalized_url,
                        snippet=(item.get("snippet") or "").strip(),
                        engine=engine.value,
                        rank=idx,
                        language=language,
                        metadata={"fetch_mode": "browser_configurable_fallback"},
                    )
                )

        return SearchResponse(
            query=query,
            engine=engine.value,
            results=parsed_results,
            total_results=len(parsed_results),
            search_time=result.search_time or 0.0,
            error=None if parsed_results else "浏览器兜底未解析到结果",
        )

    async def _search_with_browser_generic(
        self,
        engine: AdvancedSearchEngine,
        query: str,
        search_url: str,
        num_results: int,
        language: str,
    ) -> SearchResponse:
        """
        无配置引擎的浏览器兜底：
        - 直接打开搜索页
        - 用当前引擎选择器解析
        - 失败时退化为通用链接提取
        """
        await self._ensure_browser_manager()
        browser_result = await self._browser_manager.fetch(
            search_url,
            wait_for_timeout=12000,
            perform_anti_bot=True,
            engine_id=engine.value,
        )
        if browser_result.error:
            return SearchResponse(
                query=query,
                engine=engine.value,
                error=f"浏览器打开失败: {browser_result.error}",
            )

        parsed_results = self._parse_results(engine, browser_result.html)
        if not parsed_results:
            parser = _build_parser().parse(browser_result.html, search_url)
            for idx, link in enumerate(parser.soup.select("a[href]")[: max(20, num_results * 4)], 1):
                href = (link.get("href") or "").strip()
                title = link.get_text(strip=True)
                normalized_url = self._normalize_result_url(href, engine)
                if not title or not normalized_url:
                    continue
                parsed_results.append(
                    SearchResult(
                        title=title[:200],
                        url=normalized_url,
                        snippet="",
                        engine=engine.value,
                        rank=idx,
                        language=language,
                        metadata={"fetch_mode": "browser_generic_fallback"},
                    )
                )
                if len(parsed_results) >= num_results:
                    break
        else:
            for item in parsed_results:
                item.metadata.setdefault("fetch_mode", "browser_generic_fallback")
                item.language = language

        return SearchResponse(
            query=query,
            engine=engine.value,
            results=parsed_results[:num_results],
            total_results=len(parsed_results[:num_results]),
            search_time=0.0,
            error=None if parsed_results else "浏览器通用兜底未解析到结果",
        )

    def _parse_results(self, engine: AdvancedSearchEngine, html: str) -> List[SearchResult]:
        """解析搜索结果"""
        parser = _build_parser().parse(html)
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

                normalized_url = self._normalize_result_url(url, engine)
                if title and normalized_url:
                    results.append(SearchResult(
                        title=title,
                        url=normalized_url,
                        snippet=snippet,
                        engine=engine.value,
                        rank=i + 1,
                    ))
            except Exception as e:
                logger.debug(f"解析结果失败：{e}")
                continue

        return results

    def _normalize_result_url(self, raw_url: str, engine: AdvancedSearchEngine) -> str:
        """标准化搜索结果 URL，尽量转成可直接抓取的 http(s) 链接。"""
        if not raw_url:
            return ""

        url = raw_url.strip()
        if not url:
            return ""

        lower_url = url.lower()
        if lower_url.startswith(("javascript:", "mailto:", "tel:", "#")):
            return ""

        # Google 常见跳转格式：/url?q=https://target...
        if url.startswith("/url?") or url.startswith("url?"):
            query_str = url.split("?", 1)[1] if "?" in url else ""
            qs = parse_qs(query_str)
            target = qs.get("q", qs.get("url", [""]))[0]
            if target:
                url = unquote(target)

        # DuckDuckGo 跳转格式：https://duckduckgo.com/l/?uddg=...
        if "duckduckgo.com/l/?" in lower_url:
            parsed = urlparse(url)
            uddg = parse_qs(parsed.query).get("uddg", [""])[0]
            if uddg:
                url = unquote(uddg)

        engine_base_map = {
            AdvancedSearchEngine.GOOGLE: "https://www.google.com",
            AdvancedSearchEngine.GOOGLE_US: "https://www.google.com",
            AdvancedSearchEngine.BING: "https://www.bing.com",
            AdvancedSearchEngine.BING_US: "https://www.bing.com",
            AdvancedSearchEngine.BAIDU: "https://www.baidu.com",
            AdvancedSearchEngine.QUARK: "https://www.quark.cn",
            AdvancedSearchEngine.DUCKDUCKGO: "https://duckduckgo.com",
            AdvancedSearchEngine.SOGOU: "https://www.sogou.com",
            AdvancedSearchEngine.YANDEX: "https://yandex.com",
            AdvancedSearchEngine.GITHUB: "https://github.com",
            AdvancedSearchEngine.STACKOVERFLOW: "https://stackoverflow.com",
            AdvancedSearchEngine.MEDIUM: "https://medium.com",
            AdvancedSearchEngine.REDDIT: "https://www.reddit.com",
            AdvancedSearchEngine.ZHIHU: "https://www.zhihu.com",
            AdvancedSearchEngine.XIAOHONGSHU: "https://www.xiaohongshu.com",
            AdvancedSearchEngine.TIEBA: "https://tieba.baidu.com",
            AdvancedSearchEngine.DOUYIN: "https://www.douyin.com",
            AdvancedSearchEngine.WEIBO: "https://s.weibo.com",
            AdvancedSearchEngine.BILIBILI: "https://search.bilibili.com",
            AdvancedSearchEngine.TAOBAO: "https://s.taobao.com",
            AdvancedSearchEngine.JD: "https://search.jd.com",
            AdvancedSearchEngine.PINDUODUO: "https://mobile.yangkeduo.com",
            AdvancedSearchEngine.MEITUAN: "https://www.meituan.com",
            AdvancedSearchEngine.HACKERNEWS: "https://news.ycombinator.com",
            AdvancedSearchEngine.GOOGLE_SCHOLAR: "https://scholar.google.com",
            AdvancedSearchEngine.ARXIV: "https://arxiv.org",
            AdvancedSearchEngine.SEMANTIC_SCHOLAR: "https://www.semanticscholar.org",
            AdvancedSearchEngine.TWITTER: "https://x.com",
        }

        parsed = urlparse(url)
        if (not parsed.scheme) or (parsed.scheme in {"http", "https"} and not parsed.netloc):
            base = engine_base_map.get(engine)
            if base:
                if parsed.scheme in {"http", "https"} and not parsed.netloc:
                    # 修复 `https:///path` 这类“有协议但无主机”的 malformed URL。
                    relative = parsed.path or "/"
                    if parsed.query:
                        relative = f"{relative}?{parsed.query}"
                    if parsed.fragment:
                        relative = f"{relative}#{parsed.fragment}"
                    url = urljoin(base, relative)
                else:
                    url = urljoin(base, url)
                parsed = urlparse(url)

        if parsed.scheme not in {"http", "https"}:
            return ""
        if not parsed.netloc:
            return ""

        return url


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

    _CHANNEL_DOMAINS: Dict[str, List[str]] = {
        "news": [
            "reuters.com",
            "apnews.com",
            "bbc.com",
            "nytimes.com",
            "theguardian.com",
            "wsj.com",
            "bloomberg.com",
            "npr.org",
            "xinhuanet.com",
            "people.com.cn",
            "caixin.com",
            "thepaper.cn",
            "36kr.com",
        ],
        "platforms": [
            "github.com",
            "stackoverflow.com",
            "reddit.com",
            "medium.com",
            "producthunt.com",
            "hackernews.com",
            "news.ycombinator.com",
            "kaggle.com",
            "zhihu.com",
            "xiaohongshu.com",
            "tieba.baidu.com",
            "douyin.com",
            "bilibili.com",
            "weibo.com",
            "x.com",
            "youtube.com",
            "linkedin.com",
        ],
        "commerce": [
            "taobao.com",
            "tmall.com",
            "jd.com",
            "pinduoduo.com",
            "yangkeduo.com",
            "meituan.com",
            "dianping.com",
        ],
    }

    _CHANNEL_PROFILE_ALIASES: Dict[str, str] = {
        "news": "news",
        "media": "news",
        "press": "news",
        "platform": "platforms",
        "platforms": "platforms",
        "community": "platforms",
        "communities": "platforms",
        "commerce": "commerce",
        "shopping": "commerce",
        "ecommerce": "commerce",
        "mall": "commerce",
    }

    _MAX_CHANNEL_DOMAINS_PER_PROFILE = 5
    _MAX_CHANNEL_EXPANDED_QUERIES = 40
    _MAX_CONCURRENT_SEARCH_TASKS = 12
    _SEARCH_TASK_TIMEOUT_SEC = 45
    _BROWSER_FIRST_DOMAINS = {
        "xiaohongshu.com",
        "xhslink.com",
        "zhihu.com",
        "tieba.baidu.com",
        "douyin.com",
        "iesdouyin.com",
        "bilibili.com",
        "weibo.com",
        "weibo.cn",
        "taobao.com",
        "tmall.com",
        "jd.com",
        "pinduoduo.com",
        "yangkeduo.com",
        "meituan.com",
        "dianping.com",
    }

    def __init__(self, auto_cleanup: bool = True):
        self._client = AdvancedSearchEngineClient()
        if Crawler is None:
            raise RuntimeError(
                "Deep search runtime is unavailable. Install optional dependencies from requirements.txt."
            ) from _CRAWLER_IMPORT_ERROR
        self._crawler = Crawler(use_cache=True)
        self._browser: Optional[BrowserManager] = None
        self._browser_lock = asyncio.Lock()
        self._auto_cleanup = auto_cleanup
        self._session_cleaner = get_session_cleaner()

    async def close(self):
        """关闭内部资源，避免 aiohttp 会话泄漏。"""
        if self._browser:
            await self._browser.close()
            self._browser = None
        await self._client.close()
        await self._crawler.close()

    async def _ensure_browser(self):
        """按需初始化浏览器，作为 HTTP 抓取失败兜底。"""
        if self._browser is not None:
            return
        async with self._browser_lock:
            if self._browser is None:
                if BrowserManager is None:
                    raise RuntimeError(
                        "Browser runtime is unavailable. Install optional dependencies from requirements.txt."
                    ) from _BROWSER_IMPORT_ERROR
                self._browser = BrowserManager()
                await self._browser.start()

    async def _run_search_task(
        self,
        semaphore: asyncio.Semaphore,
        engine: AdvancedSearchEngine,
        query: str,
        num_results: int,
        language: str,
        timeout_sec: int,
    ) -> SearchResponse:
        """执行单个搜索任务（并发受控 + 超时保护）。"""
        async with semaphore:
            try:
                return await asyncio.wait_for(
                    self._client.search(engine, query, num_results, language=language),
                    timeout=max(5, timeout_sec),
                )
            except asyncio.TimeoutError:
                return SearchResponse(
                    query=query,
                    engine=engine.value,
                    error=f"search timeout>{max(5, timeout_sec)}s",
                )
            except Exception as exc:
                return SearchResponse(
                    query=query,
                    engine=engine.value,
                    error=str(exc),
                )

    async def deep_search(
        self,
        query: str,
        num_results: int = 20,
        use_english: bool = True,  # 是否同时使用英文搜索
        engines: Optional[List[AdvancedSearchEngine]] = None,
        crawl_top: int = 0,  # 爬取前 N 个结果
        auto_cleanup: Optional[bool] = None,  # 搜索后是否自动清理缓存
        query_variants: int = 1,  # MindSearch 风格：子查询分解数量
        channel_profiles: Optional[List[str]] = None,  # 站点渠道扩展：news/platforms
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
            query_variants: 查询分解数量（>=1，默认1表示关闭分解）
            channel_profiles: 站点渠道档案（如 news/platforms）

        Returns:
            搜索结果字典
        """
        if engines is None:
            # 默认使用通用搜索引擎
            engines = [
                AdvancedSearchEngine.GOOGLE,
                AdvancedSearchEngine.BING,
                AdvancedSearchEngine.QUARK,
                AdvancedSearchEngine.BAIDU,
                AdvancedSearchEngine.DUCKDUCKGO,
            ]
        query_variants = max(1, min(query_variants, 8))

        timeout_sec = max(
            5,
            int(os.getenv("WEB_ROOTER_SEARCH_TIMEOUT_SEC", str(self._SEARCH_TASK_TIMEOUT_SEC))),
        )
        max_parallel = max(
            1,
            int(os.getenv("WEB_ROOTER_MAX_PARALLEL_SEARCHES", str(self._MAX_CONCURRENT_SEARCH_TASKS))),
        )
        semaphore = asyncio.Semaphore(max_parallel)

        tasks = []
        decomposed_queries = self._decompose_query(query, query_variants)
        normalized_profiles = self._normalize_channel_profiles(channel_profiles)
        expanded_queries = self._expand_queries_with_channels(
            decomposed_queries,
            normalized_profiles,
        )

        # MindSearch 风格：主查询 + 子查询并行
        for q in expanded_queries:
            for engine in engines:
                tasks.append(
                    asyncio.create_task(
                        self._run_search_task(
                            semaphore=semaphore,
                            engine=engine,
                            query=q,
                            num_results=num_results,
                            language="zh",
                            timeout_sec=timeout_sec,
                        )
                    )
                )

            if use_english:
                english_query = self._translate_query(q)
                for engine in engines:
                    if engine in [AdvancedSearchEngine.GOOGLE, AdvancedSearchEngine.BING, AdvancedSearchEngine.YANDEX]:
                        tasks.append(
                            asyncio.create_task(
                                self._run_search_task(
                                    semaphore=semaphore,
                                    engine=engine,
                                    query=english_query,
                                    num_results=num_results,
                                    language="en",
                                    timeout_sec=timeout_sec,
                                )
                            )
                        )

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
                    for result in response.results:
                        source_queries = result.metadata.setdefault("source_queries", [])
                        source_engines = result.metadata.setdefault("source_engines", [])
                        if response.query not in source_queries:
                            source_queries.append(response.query)
                        if response.engine not in source_engines:
                            source_engines.append(response.engine)
                    all_results.extend(response.results)

        # 去重
        deduped_map: Dict[str, SearchResult] = {}
        for result in all_results:
            canonical_url = self._canonicalize_url(result.url)
            if not canonical_url:
                continue
            result.url = canonical_url

            if canonical_url not in deduped_map:
                deduped_map[canonical_url] = result
                continue

            existing = deduped_map[canonical_url]
            existing_queries = existing.metadata.setdefault("source_queries", [])
            existing_engines = existing.metadata.setdefault("source_engines", [])

            for query_item in result.metadata.get("source_queries", []):
                if query_item not in existing_queries:
                    existing_queries.append(query_item)
            for engine_item in result.metadata.get("source_engines", []):
                if engine_item not in existing_engines:
                    existing_engines.append(engine_item)

            # 合并时保留更丰富摘要，并取更靠前排名
            if len(result.snippet) > len(existing.snippet):
                existing.snippet = result.snippet
            if result.rank < existing.rank:
                existing.rank = result.rank
                existing.engine = result.engine

        unique_results = list(deduped_map.values())

        # 按排名 + 覆盖来源排序
        unique_results.sort(
            key=lambda x: (
                x.rank,
                -len(x.metadata.get("source_engines", [])),
                -len(x.metadata.get("source_queries", [])),
            )
        )

        result_dicts = [r.to_dict() for r in unique_results]
        citations = build_web_citations(result_dicts, query=query, prefix="W")
        comparison = build_comparison_summary(result_dicts)

        # 爬取前 N 个结果（HTTP 失败自动浏览器兜底）
        crawled_content = []
        if crawl_top > 0:
            for result in unique_results[:crawl_top]:
                if not self._is_supported_url(result.url):
                    errors.append(f"跳过不支持的 URL: {result.url}")
                    continue

                page_data, crawl_error = await self._crawl_with_fallback(result)
                if page_data:
                    crawled_content.append(page_data)
                elif crawl_error:
                    errors.append(crawl_error)

        # 构建最终结果
        final_result = {
            "success": True,
            "query": query,
            "queries_used": expanded_queries,
            "base_queries": decomposed_queries,
            "channel_profiles": normalized_profiles,
            "total_results": len(unique_results),
            "results": result_dicts,
            "crawled_content": crawled_content,
            "errors": errors,
            "citations": citations,
            "references_text": format_reference_block(citations, max_items=40),
            "comparison": comparison,
            "search_summary": (
                f"使用 {len(engines)} 个引擎、{len(expanded_queries)} 个查询并行搜索，"
                f"共找到 {len(unique_results)} 条结果"
            ),
        }
        final_result = _finalize_payload_with_extensions(
            payload=final_result,
            query=query,
            mode="deep_search",
            source="deep_search_engine",
        )

        # 标记最终结果
        result_key = f"deep_search:{query}:{datetime.now().strftime('%Y%m%d%H%M%S')}"
        mark_result_as_final(result_key)

        # 自动清理缓存
        cleanup_flag = auto_cleanup if auto_cleanup is not None else self._auto_cleanup
        if cleanup_flag:
            await cleanup_search_session(keep_final_results=True)
            logger.info(f"Search session cleanup completed for query: {query}")

        return final_result

    def _normalize_channel_profiles(self, profiles: Optional[List[str]]) -> List[str]:
        if not profiles:
            return []

        normalized: List[str] = []
        for raw in profiles:
            key = str(raw or "").strip().lower()
            if not key:
                continue
            canonical = self._CHANNEL_PROFILE_ALIASES.get(key)
            if not canonical:
                continue
            if canonical not in normalized:
                normalized.append(canonical)
        return normalized

    def _expand_queries_with_channels(
        self,
        base_queries: List[str],
        channel_profiles: List[str],
    ) -> List[str]:
        if not base_queries:
            return []

        expanded: List[str] = []
        seen = set()

        def _append_query(q: str) -> None:
            candidate = (q or "").strip()
            if not candidate or candidate in seen:
                return
            seen.add(candidate)
            expanded.append(candidate)

        for query in base_queries:
            _append_query(query)
            for profile in channel_profiles:
                domains = self._CHANNEL_DOMAINS.get(profile, [])
                for domain in domains[: self._MAX_CHANNEL_DOMAINS_PER_PROFILE]:
                    _append_query(f"{query} site:{domain}")
                    if len(expanded) >= self._MAX_CHANNEL_EXPANDED_QUERIES:
                        return expanded

        return expanded

    @staticmethod
    def _canonicalize_url(url: str) -> str:
        """
        URL 规范化用于跨引擎去重。
        保留业务参数，剔除常见追踪参数与 fragment。
        """
        parsed = urlparse(url or "")
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            return ""

        tracking_keys = {
            "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
            "gclid", "fbclid", "msclkid", "spm", "ref", "ref_src",
        }
        query_pairs = parse_qsl(parsed.query, keep_blank_values=True)
        filtered_query = [
            (k, v)
            for k, v in query_pairs
            if not k.lower().startswith("utm_") and k.lower() not in tracking_keys
        ]
        canonical_query = urlencode(filtered_query, doseq=True)

        path = parsed.path or "/"
        if path != "/" and path.endswith("/"):
            path = path[:-1]

        canonical = parsed._replace(path=path, query=canonical_query, fragment="")
        return urlunparse(canonical)

    async def _crawl_with_fallback(self, result: SearchResult) -> tuple[Optional[Dict[str, Any]], Optional[str]]:
        """抓取单个结果；社交/电商站点优先浏览器兜底。"""
        target_url = result.url
        browser_first = self._is_browser_first_domain(target_url)

        if browser_first:
            page_data, browser_error = await self._run_browser_fetch(result, mode="browser_first")
            if page_data:
                return page_data, None
            crawl_result = await self._crawler.fetch(target_url)
            if crawl_result.success and crawl_result.html:
                return {
                    "url": target_url,
                    "title": result.title,
                    "content": crawl_result.html[:10000],
                    "fetch_mode": "http_after_browser_first",
                }, None
            return None, (
                f"抓取失败 {target_url}: Browser({browser_error or 'empty'}) "
                f"+ HTTP({crawl_result.status_code}/{crawl_result.error})"
            )

        crawl_result = await self._crawler.fetch(target_url)
        if crawl_result.success and crawl_result.html:
            return {
                "url": target_url,
                "title": result.title,
                "content": crawl_result.html[:10000],
                "fetch_mode": "http",
            }, None

        if self._should_fallback_to_browser(crawl_result):
            page_data, browser_error = await self._run_browser_fetch(result, mode="browser_fallback")
            if page_data:
                return page_data, None
            return None, (
                f"抓取失败 {target_url}: HTTP({crawl_result.status_code}/{crawl_result.error}) "
                f"+ Browser({browser_error or 'empty'})"
            )

        return None, f"抓取失败 {target_url}: HTTP({crawl_result.status_code}/{crawl_result.error})"

    async def _run_browser_fetch(
        self,
        result: SearchResult,
        mode: str,
    ) -> tuple[Optional[Dict[str, Any]], Optional[str]]:
        target_url = result.url
        try:
            await self._ensure_browser()
            browser_result = await self._browser.fetch(target_url)
            if browser_result.error is None and browser_result.html:
                if browser_result.cookies:
                    try:
                        await self._crawler.seed_cookies(
                            browser_result.url or target_url,
                            browser_result.cookies,
                        )
                    except Exception as cookie_exc:
                        logger.debug("浏览器 cookies 回灌失败（忽略） %s: %s", target_url, cookie_exc)
                return {
                    "url": target_url,
                    "title": browser_result.title or result.title,
                    "content": browser_result.html[:10000],
                    "fetch_mode": mode,
                }, None

            browser_error = (browser_result.error or "").strip() or "empty"
            return None, browser_error
        except Exception as exc:
            return None, str(exc).strip() or exc.__class__.__name__

    def _is_browser_first_domain(self, url: str) -> bool:
        parsed = urlparse(url or "")
        host = (parsed.hostname or "").lower()
        if not host:
            return False
        return any(host == domain or host.endswith("." + domain) for domain in self._BROWSER_FIRST_DOMAINS)

    @staticmethod
    def _is_supported_url(url: str) -> bool:
        parsed = urlparse(url or "")
        return parsed.scheme in {"http", "https"} and bool(parsed.netloc)

    @staticmethod
    def _should_fallback_to_browser(result: CrawlResult) -> bool:
        if result.success:
            return False

        if result.status_code in {
            0, 401, 403, 404, 406, 408, 409, 410, 412, 418, 421, 425, 426,
            429, 451, 500, 502, 503, 504, 520, 521, 522, 523, 524, 525,
        }:
            return True

        error_text = (result.error or "").lower()
        fallback_keywords = [
            "timeout", "ssl", "cloudflare", "captcha", "forbidden", "blocked",
            "connection", "reset", "refused", "challenge", "javascript",
            "login", "sign in", "访问受限", "登录后查看",
        ]
        return any(keyword in error_text for keyword in fallback_keywords)

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

    def _decompose_query(self, query: str, query_variants: int = 1) -> List[str]:
        """
        MindSearch 风格的轻量查询分解。
        不引入额外 LLM，仅做规则扩展，提升召回覆盖面。
        """
        if query_variants <= 1:
            return [query]

        variants = [query]
        is_chinese = any("\u4e00" <= c <= "\u9fff" for c in query)
        candidates = (
            [f"{query} 最新进展", f"{query} 原理", f"{query} 最佳实践", f"{query} 案例"]
            if is_chinese
            else [f"{query} latest trends", f"{query} architecture", f"{query} best practices", f"{query} case study"]
        )

        for candidate in candidates:
            if candidate not in variants:
                variants.append(candidate)
            if len(variants) >= query_variants:
                break

        return variants


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
    try:
        return await deep_search.deep_search(
            query,
            num_results=num_results,
            use_english=use_english,
            crawl_top=crawl_top,
        )
    finally:
        await deep_search.close()


def _dedupe_result_dicts(results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    deduped: Dict[str, Dict[str, Any]] = {}
    for item in results:
        if not isinstance(item, dict):
            continue
        canonical_url = DeepSearchEngine._canonicalize_url(item.get("url", ""))
        if not canonical_url:
            continue
        normalized = dict(item)
        normalized["url"] = canonical_url

        existing = deduped.get(canonical_url)
        if not existing:
            deduped[canonical_url] = normalized
            continue

        if len(str(normalized.get("snippet", ""))) > len(str(existing.get("snippet", ""))):
            existing["snippet"] = normalized.get("snippet", "")
        try:
            if int(normalized.get("rank", 9999)) < int(existing.get("rank", 9999)):
                existing["rank"] = normalized.get("rank", existing.get("rank"))
                existing["engine"] = normalized.get("engine", existing.get("engine"))
        except Exception:
            pass

    return list(deduped.values())


def _extract_query_tokens(query: str) -> List[str]:
    tokens = re.split(r"[\s,，;；/|]+", str(query or "").strip().lower())
    return [token for token in tokens if len(token) >= 2]


_COMMENT_INTENT_TERMS = (
    "评论", "评价", "反馈", "吐槽", "测评", "体验", "弹幕", "讨论", "口碑", "回复",
    "comment", "comments", "review", "reviews", "rating", "ratings", "feedback", "discussion",
)

_SOCIAL_HIGH_SIGNAL_HINTS = (
    "/explore/", "/question/", "/answer/", "/p/", "/video/", "/status/", "/comments/",
    "/read/cv", "/opus/", "/note/",
)

_SOCIAL_NAV_NOISE_HINTS = (
    "/jingxuan", "/follow", "/friend", "/anime", "/match/home", "/platform", "/home",
    "/hot", "/rank", "/topic", "/discover", "/aisearch",
)

_COMMERCE_HIGH_SIGNAL_HINTS = (
    "item.taobao.com/item.htm", "detail.tmall.com/item.htm", "item.jd.com/",
    "yangkeduo.com/goods", "goods.html", "/deal/", "/shop/", "/poi/",
)

_COMMERCE_NAV_NOISE_HINTS = (
    "/win-together", "/technology", "/csr", "/passport", "/reg", "/club", "/union",
    "/order", "/buyertrade", "/daxue", "/help", "/service", "/about", "/login",
)

_BACKUP_DOMAIN_PRIORITY: Dict[str, int] = {
    # social
    "zhihu.com": 100,
    "bilibili.com": 98,
    "tieba.baidu.com": 96,
    "weibo.com": 95,
    "weibo.cn": 94,
    "douyin.com": 92,
    "iesdouyin.com": 91,
    "xiaohongshu.com": 84,
    "xhslink.com": 70,
    # commerce
    "jd.com": 96,
    "taobao.com": 94,
    "tmall.com": 93,
    "dianping.com": 92,
    "meituan.com": 90,
    "pinduoduo.com": 88,
    "yangkeduo.com": 87,
}

_BACKUP_DOMAIN_QUERY_HINTS: Dict[str, str] = {
    "zhihu.com": "question 回答 评论",
    "xiaohongshu.com": "explore 笔记 评论",
    "xhslink.com": "小红书 笔记 评论",
    "bilibili.com": "video 弹幕 评论",
    "tieba.baidu.com": "贴吧 回复 评论",
    "douyin.com": "video 评论",
    "iesdouyin.com": "video 评论",
    "weibo.com": "status 评论",
    "weibo.cn": "status 评论",
    "taobao.com": "商品 评价 评论 item",
    "tmall.com": "商品 评价 评论 item",
    "jd.com": "商品 评价 评论 item",
    "pinduoduo.com": "商品 评价 评论",
    "yangkeduo.com": "商品 评价 评论",
    "meituan.com": "团购 店铺 评价 评论",
    "dianping.com": "店铺 评价 评论",
}

_ENGINE_URL_FALLBACK_TEMPLATES: Dict[str, List[str]] = {
    # 主入口常见 404/跳转时尝试备用网址
    "quark": [
        "https://www.quark.cn/s?q={query}",
        "https://www.quark.cn/s?wd={query}",
        "https://quark.sm.cn/s?wd={query}",
    ],
    "meituan": [
        "https://i.meituan.com/s/{query}",
        "https://www.dianping.com/search/keyword/1/0_{query}",
    ],
    "pinduoduo": [
        "https://mobile.yangkeduo.com/search_result.html?search_key={query}",
        "https://www.pinduoduo.com/search_result.html?search_key={query}",
    ],
    "douyin": [
        "https://www.douyin.com/search/{query}",
        "https://www.iesdouyin.com/share/search/{query}",
    ],
    "bilibili": [
        "https://search.bilibili.com/all?keyword={query}",
        "https://search.bilibili.com/video?keyword={query}",
    ],
    "xiaohongshu": [
        "https://www.xiaohongshu.com/search_result?keyword={query}&source=web_explore_feed",
        "https://www.xiaohongshu.com/search_result?keyword={query}",
    ],
}

_PLATFORM_PROFILE_CACHE: Optional[Dict[str, Any]] = None


def _project_root() -> Path:
    return Path(__file__).resolve().parent.parent.parent


def _to_bool_env(name: str, default: bool = False) -> bool:
    raw = str(os.getenv(name, "1" if default else "0")).strip().lower()
    return raw in {"1", "true", "yes", "on"}


def _default_platform_profile_path() -> Path:
    return _project_root() / "profiles" / "search_templates" / "platform_profiles.json"


def _load_platform_profile_cache(force: bool = False) -> Dict[str, Any]:
    global _PLATFORM_PROFILE_CACHE
    if _PLATFORM_PROFILE_CACHE is not None and not force:
        return _PLATFORM_PROFILE_CACHE

    profile_data: Dict[str, Any] = {
        "engine_search_urls": {},
        "backup_domain_priority": {},
        "backup_domain_query_hints": {},
    }

    file_candidates: List[Path] = []
    env_file = str(os.getenv("WEB_ROOTER_PLATFORM_PROFILE_FILE", "")).strip()
    if env_file:
        file_candidates.append(Path(env_file).expanduser())
    file_candidates.append(_default_platform_profile_path())

    loaded_path: Optional[Path] = None
    for candidate in file_candidates:
        path = candidate.resolve()
        if not path.exists() or not path.is_file():
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.warning("加载平台模板配置失败 %s: %s", path, exc)
            continue
        if not isinstance(payload, dict):
            continue

        raw_engine_urls = payload.get("engine_search_urls", {})
        if isinstance(raw_engine_urls, dict):
            for engine_name, urls in raw_engine_urls.items():
                key = str(engine_name or "").strip().lower()
                if not key or not isinstance(urls, list):
                    continue
                normalized_urls = [
                    str(item or "").strip()
                    for item in urls
                    if str(item or "").strip()
                ]
                if normalized_urls:
                    profile_data["engine_search_urls"][key] = normalized_urls

        raw_priority = payload.get("backup_domain_priority", {})
        if isinstance(raw_priority, dict):
            for domain, value in raw_priority.items():
                key = str(domain or "").strip().lower()
                if not key:
                    continue
                try:
                    profile_data["backup_domain_priority"][key] = int(value)
                except Exception:
                    continue

        raw_hints = payload.get("backup_domain_query_hints", {})
        if isinstance(raw_hints, dict):
            for domain, hint in raw_hints.items():
                key = str(domain or "").strip().lower()
                val = str(hint or "").strip()
                if key and val:
                    profile_data["backup_domain_query_hints"][key] = val

        loaded_path = path
        break

    _PLATFORM_PROFILE_CACHE = profile_data
    if loaded_path is not None:
        logger.info("已加载平台模板配置: %s", loaded_path)
    return _PLATFORM_PROFILE_CACHE


def _get_engine_search_url_templates(engine: AdvancedSearchEngine) -> List[str]:
    base_template = AdvancedSearchEngineClient.SEARCH_URLS.get(engine)
    templates: List[str] = []
    if base_template:
        templates.append(base_template)

    key = str(engine.value or "").strip().lower()
    fallback_templates = _ENGINE_URL_FALLBACK_TEMPLATES.get(key, [])
    for tpl in fallback_templates:
        if tpl not in templates:
            templates.append(tpl)

    profile_data = _load_platform_profile_cache()
    custom_templates = profile_data.get("engine_search_urls", {}).get(key, [])
    if isinstance(custom_templates, list):
        for tpl in custom_templates:
            candidate = str(tpl or "").strip()
            if candidate and candidate not in templates:
                templates.append(candidate)

    max_templates = max(1, int(os.getenv("WEB_ROOTER_ENGINE_URL_CANDIDATES", "3")))
    return templates[:max_templates]


def _get_backup_domain_priority(domain: str) -> int:
    token = str(domain or "").strip().lower()
    if not token:
        return 50
    profile_data = _load_platform_profile_cache()
    custom_value = profile_data.get("backup_domain_priority", {}).get(token)
    if isinstance(custom_value, int):
        return custom_value
    return _BACKUP_DOMAIN_PRIORITY.get(token, 50)


def _get_backup_domain_query_hint(domain: str) -> str:
    token = str(domain or "").strip().lower()
    if not token:
        return ""
    profile_data = _load_platform_profile_cache()
    custom_hint = profile_data.get("backup_domain_query_hints", {}).get(token)
    if isinstance(custom_hint, str) and custom_hint.strip():
        return custom_hint.strip()
    return _BACKUP_DOMAIN_QUERY_HINTS.get(token, "")


def _build_auth_guidance(target_domains: List[str]) -> Dict[str, Any]:
    rows: List[Dict[str, Any]] = []
    requires_user_input = False
    any_configured = False
    any_disabled = False
    try:
        registry = get_auth_profile_registry()
    except Exception as exc:
        return {
            "summary": "auth_registry_unavailable",
            "errors": [str(exc)],
            "profiles": [],
            "requires_user_input": False,
            "any_configured": False,
        }

    seen = set()
    for raw_domain in target_domains:
        domain = str(raw_domain or "").strip().lower()
        if not domain or domain in seen:
            continue
        seen.add(domain)
        hint = registry.build_hint(f"https://{domain}/")
        row = {
            "domain": domain,
            "matched": hint.get("matched"),
            "configured": bool(hint.get("configured")),
            "requires_user_input": bool(hint.get("requires_user_input")),
            "hint": hint.get("hint", ""),
            "login_url": hint.get("login_url"),
            "disabled_profiles": hint.get("disabled_profiles", []),
        }
        if row["configured"]:
            any_configured = True
        if row["requires_user_input"]:
            requires_user_input = True
        if isinstance(row.get("disabled_profiles"), list) and row["disabled_profiles"]:
            any_disabled = True
        rows.append(row)

    if requires_user_input:
        summary = "matched_but_requires_local_credentials"
    elif any_configured:
        summary = "auth_profiles_ready"
    elif any_disabled:
        summary = "matched_profiles_disabled"
    else:
        summary = "no_configured_auth_profiles"

    return {
        "summary": summary,
        "profiles": rows,
        "requires_user_input": requires_user_input,
        "any_configured": any_configured,
        "any_disabled": any_disabled,
    }


def _domain_auth_priority_boost(domain: str) -> int:
    token = str(domain or "").strip().lower()
    if not token:
        return 0
    try:
        registry = get_auth_profile_registry()
        payload = registry.collect_auth_payload(f"https://{token}/")
    except Exception:
        return 0

    if not isinstance(payload, dict):
        return 0
    if payload.get("configured"):
        return 18
    if payload.get("matched"):
        return 8
    return 0


def _attach_platform_runtime_hints(
    payload: Dict[str, Any],
    target_domains: List[str],
    mode: Literal["social", "commerce", "generic"],
) -> Dict[str, Any]:
    result = dict(payload or {})
    auth_guidance = _build_auth_guidance(target_domains)
    result["auth_guidance"] = auth_guidance

    total_results = int(result.get("total_results", 0) or 0)
    next_actions: List[str] = []
    if total_results <= 0:
        if auth_guidance.get("summary") == "matched_profiles_disabled":
            next_actions.append(
                "检测到本地存在匹配 profile 但为 disabled。请将对应条目的 `enabled` 设为 true，并补充 cookies/storage_state。"
            )
        elif auth_guidance.get("requires_user_input"):
            next_actions.append(
                "该场景存在登录门槛。请先调用 `web_auth_hint` 定位目标域名，再用 `web_auth_template` 导出并补全本地登录态。"
            )
        next_actions.append(
            "若仍无结果，建议调高 `WEB_ROOTER_SEARCH_TIMEOUT_SEC` 与 `WEB_ROOTER_PLATFORM_BACKUP_TIMEOUT_SEC` 后重试。"
        )
        next_actions.append(
            "可用 `web_challenge_profiles` 检查挑战配置，并在本地 profile JSON 中按目标站点补充规则。"
        )
    elif _to_bool_env("WEB_ROOTER_ENABLE_RECOVERY_MODE", default=True):
        if isinstance(result.get("recovery_mode"), dict) and result["recovery_mode"].get("active"):
            next_actions.append(
                "当前结果来自 recovery 模式（低置信）。建议继续收集登录态后再次抓取同一查询。"
            )

    if next_actions:
        result["next_actions"] = next_actions
    result["platform_mode"] = mode
    return result


def _has_comment_intent(query: str) -> bool:
    text = str(query or "").strip().lower()
    return any(term in text for term in _COMMENT_INTENT_TERMS)


def _is_low_signal_url(url: str) -> bool:
    parsed = urlparse(url or "")
    path = (parsed.path or "").lower()
    if path in {"", "/"}:
        return True

    low_signal_keywords = (
        "login", "signup", "register", "privacy", "agreement", "terms", "help", "about",
        "account", "my", "cart", "coupon", "customer", "service", "download",
        "protocol", "policy", "setting", "settings", "user/self",
        "win-together", "technology", "csr", "passport", "reg", "club", "union", "buyertrade",
        "jingxuan", "follow", "friend", "match/home", "anime", "platform",
    )
    return any(keyword in path for keyword in low_signal_keywords)


def _is_challenge_or_gate_url(url: str) -> bool:
    parsed = urlparse(url or "")
    host = (parsed.hostname or "").lower()
    path = (parsed.path or "").lower()
    query = (parsed.query or "").lower()
    text = f"{host}{path}?{query}"
    markers = (
        "captcha",
        "challenge",
        "verify",
        "spiderindefence",
        "wappass.baidu.com",
        "cf-challenge",
        "turnstile",
        "recaptcha",
        "hcaptcha",
        "/error/404",
    )
    return any(marker in text for marker in markers)


def _platform_signal_score(
    item: Dict[str, Any],
    mode: Literal["social", "commerce", "generic"],
    query: str,
) -> int:
    url = str(item.get("url") or "")
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    path = (parsed.path or "").lower()
    title = str(item.get("title") or "")
    snippet = str(item.get("snippet") or item.get("description") or "")
    text = f"{host}{path} {title} {snippet} {url}".lower()

    score = 0

    if _is_challenge_or_gate_url(url):
        score -= 8

    if mode == "social":
        # 平台特异高信号：帖子/视频/问答详情页
        if host.endswith("bilibili.com") and path.startswith("/video/"):
            score += 6
        if host.endswith("bilibili.com") and (path.startswith("/read/cv") or path.startswith("/opus/")):
            score += 5
        if host.endswith("xiaohongshu.com") and re.match(r"^/(explore|discovery/item)/[a-z0-9]+", path):
            score += 6
        if host.endswith("zhihu.com") and "/question/" in path:
            score += 6
        if host.endswith("tieba.baidu.com") and path.startswith("/p/"):
            score += 6
        if host.endswith("douyin.com") and "/video/" in path:
            score += 6
        if host.endswith("weibo.com") and "/status/" in path:
            score += 6
        if host.endswith("reddit.com") and "/comments/" in path:
            score += 6
        if (host.endswith("x.com") or host.endswith("twitter.com")) and "/status/" in path:
            score += 6

        # 平台特异低信号：导航/账号/创作者后台
        if host.startswith("creator.xiaohongshu.com"):
            score -= 7
        if host.startswith("account.bilibili.com"):
            score -= 7
        if path in {
            "/explore", "/notification", "/jingxuan", "/follow", "/friend",
            "/anime", "/match/home", "/platform", "/platform/home.html",
        }:
            score -= 7

        if any(hint in text for hint in _SOCIAL_HIGH_SIGNAL_HINTS):
            score += 4
        if any(hint in text for hint in _SOCIAL_NAV_NOISE_HINTS):
            score -= 4
    elif mode == "commerce":
        # 平台特异高信号：商品/团购详情页
        if host.startswith("item.taobao.com") and "item.htm" in path:
            score += 6
        if host.startswith("detail.tmall.com") and "item.htm" in path:
            score += 6
        if host.startswith("item.jd.com"):
            score += 6
        if (
            (host.endswith("yangkeduo.com") or host.endswith("pinduoduo.com"))
            and ("goods" in path or "goods_id=" in parsed.query.lower())
        ):
            score += 6
        if (host.endswith("meituan.com") or host.endswith("dianping.com")) and any(
            seg in path for seg in ("/deal/", "/shop/", "/poi/")
        ):
            score += 5

        # 平台特异低信号：品牌页/账号/帮助中心
        if host.startswith((
            "wj-dongjian.jd.com",
            "passport.jd.com",
            "reg.jd.com",
            "club.jd.com",
            "union.jd.com",
            "buyertrade.taobao.com",
            "ishop.taobao.com",
        )):
            score -= 7
        if path in {"/contact", "/win-together", "/technology", "/csr"}:
            score -= 7

        if any(hint in text for hint in _COMMERCE_HIGH_SIGNAL_HINTS):
            score += 4
        if any(hint in text for hint in _COMMERCE_NAV_NOISE_HINTS):
            score -= 4

    tokens = _extract_query_tokens(query)
    if tokens and any(token in text for token in tokens):
        score += 1

    if _has_comment_intent(query):
        matched_comment_terms = sum(1 for term in _COMMENT_INTENT_TERMS if term in text)
        if matched_comment_terms > 0:
            score += min(3, matched_comment_terms)
        else:
            score -= 1

    if _is_low_signal_url(url):
        score -= 2
    if path in {"", "/"}:
        score -= 2
    if not title and not snippet:
        score -= 1

    return score


def _count_high_signal_results(
    results: List[Dict[str, Any]],
    query: str,
    target_domains: Optional[List[str]] = None,
    mode: Literal["social", "commerce", "generic"] = "generic",
) -> int:
    if not isinstance(results, list) or not results:
        return 0

    domains = [d.lower() for d in (target_domains or []) if d]
    tokens = _extract_query_tokens(query)
    count = 0

    for item in results:
        if not isinstance(item, dict):
            continue
        url = str(item.get("url") or "")
        parsed = urlparse(url)
        host = (parsed.hostname or "").lower()
        if domains and host and not any(host == d or host.endswith("." + d) for d in domains):
            continue
        score = _platform_signal_score(item, mode=mode, query=query)
        if score >= 2:
            count += 1
            continue
        if mode == "generic" and not _is_low_signal_url(url):
            text = " ".join(
                [
                    str(item.get("title") or ""),
                    str(item.get("snippet") or ""),
                    str(item.get("description") or ""),
                    url,
                ]
            ).lower()
            if not tokens or any(token in text for token in tokens):
                count += 1

    return count


def _filter_platform_results(
    results: List[Dict[str, Any]],
    query: str,
    mode: Literal["social", "commerce", "generic"] = "generic",
    target_domains: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    if not isinstance(results, list):
        return []

    domains = [d.lower() for d in (target_domains or []) if d]
    scored_items: List[Dict[str, Any]] = []
    for item in results:
        if not isinstance(item, dict):
            continue
        url = str(item.get("url") or "")
        if not url:
            continue
        parsed = urlparse(url)
        host = (parsed.hostname or "").lower()
        if domains and host and not any(host == d or host.endswith("." + d) for d in domains):
            continue
        signal_score = _platform_signal_score(item, mode=mode, query=query)
        if signal_score <= -3:
            continue
        normalized = dict(item)
        metadata = normalized.get("metadata", {})
        if not isinstance(metadata, dict):
            metadata = {}
        metadata = dict(metadata)
        metadata["signal_score"] = signal_score
        normalized["metadata"] = metadata
        normalized["_signal_score"] = signal_score
        scored_items.append(normalized)

    if not scored_items:
        return []

    scored_items.sort(
        key=lambda it: (
            int(it.get("_signal_score", 0)),
            -int(it.get("rank", 9999) or 9999),
        ),
        reverse=True,
    )

    comment_intent = _has_comment_intent(query)
    high_signal = [it for it in scored_items if int(it.get("_signal_score", 0)) >= 2]
    medium_signal = [it for it in scored_items if 0 <= int(it.get("_signal_score", 0)) < 2]

    if comment_intent:
        if high_signal or medium_signal:
            selected = high_signal + medium_signal
        else:
            selected = scored_items[: min(max(3, len(scored_items)), 8)]
    else:
        selected = high_signal + medium_signal if (high_signal or medium_signal) else scored_items

    for item in selected:
        item.pop("_signal_score", None)

    return _dedupe_result_dicts(selected)


def _build_recovery_results(
    results: List[Dict[str, Any]],
    query: str,
    mode: Literal["social", "commerce", "generic"] = "generic",
    target_domains: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    if not isinstance(results, list) or not results:
        return []

    domains = [d.lower() for d in (target_domains or []) if d]
    candidates: List[Dict[str, Any]] = []
    for item in results:
        if not isinstance(item, dict):
            continue
        url = str(item.get("url") or "")
        if not url or _is_challenge_or_gate_url(url):
            continue
        parsed = urlparse(url)
        host = (parsed.hostname or "").lower()
        if domains and host and not any(host == d or host.endswith("." + d) for d in domains):
            continue

        signal_score = _platform_signal_score(item, mode=mode, query=query)
        # recovery 模式允许低信号，但仍过滤掉明显噪声
        if signal_score <= -6:
            continue

        normalized = dict(item)
        metadata = normalized.get("metadata", {})
        if not isinstance(metadata, dict):
            metadata = {}
        metadata = dict(metadata)
        metadata["signal_score"] = signal_score
        metadata["recovery_mode"] = True
        metadata["confidence"] = "low"
        normalized["metadata"] = metadata
        normalized["_signal_score"] = signal_score
        candidates.append(normalized)

    if not candidates:
        return []

    candidates.sort(
        key=lambda it: (
            int(it.get("_signal_score", -999)),
            -int(it.get("rank", 9999) or 9999),
        ),
        reverse=True,
    )
    max_items = max(1, int(os.getenv("WEB_ROOTER_RECOVERY_MAX_RESULTS", "3")))
    selected = candidates[:max_items]
    for item in selected:
        item.pop("_signal_score", None)
    return _dedupe_result_dicts(selected)


def _refine_platform_payload(
    payload: Dict[str, Any],
    query: str,
    mode: Literal["social", "commerce", "generic"] = "generic",
    target_domains: Optional[List[str]] = None,
) -> Dict[str, Any]:
    result = dict(payload or {})
    raw_results = result.get("results", []) if isinstance(result.get("results"), list) else []
    filtered_results = _filter_platform_results(
        raw_results,
        query=query,
        mode=mode,
        target_domains=target_domains,
    )
    if not filtered_results:
        recovery_enabled = _to_bool_env("WEB_ROOTER_ENABLE_RECOVERY_MODE", default=True)
        recovery_results = (
            _build_recovery_results(
                raw_results,
                query=query,
                mode=mode,
                target_domains=target_domains,
            )
            if recovery_enabled
            else []
        )
        if recovery_results:
            result["results"] = recovery_results
            result["total_results"] = len(recovery_results)
            result["citations"] = build_web_citations(recovery_results, query=query, prefix="W")
            result["comparison"] = build_comparison_summary(recovery_results)
            result["references_text"] = format_reference_block(result["citations"], max_items=40)
            result["recovery_mode"] = {
                "active": True,
                "reason": "all_platform_results_filtered_as_low_signal",
                "max_results": len(recovery_results),
            }
            errors = result.get("errors", []) if isinstance(result.get("errors"), list) else []
            if "recovery_mode_active_low_confidence" not in errors:
                errors = list(errors) + ["recovery_mode_active_low_confidence"]
            result["errors"] = errors
            return result

        result["results"] = []
        result["total_results"] = 0
        result["citations"] = []
        result["comparison"] = build_comparison_summary([])
        result["references_text"] = ""
        if raw_results:
            errors = result.get("errors", []) if isinstance(result.get("errors"), list) else []
            if "all_platform_results_filtered_as_low_signal" not in errors:
                errors = list(errors) + ["all_platform_results_filtered_as_low_signal"]
            result["errors"] = errors
        return result

    result["results"] = filtered_results
    result["total_results"] = len(filtered_results)
    result["citations"] = build_web_citations(filtered_results, query=query, prefix="W")
    result["comparison"] = build_comparison_summary(filtered_results)
    result["references_text"] = format_reference_block(result["citations"], max_items=40)
    return result


def _merge_search_payload(
    primary: Dict[str, Any],
    backup: Dict[str, Any],
    query: str,
) -> Dict[str, Any]:
    merged = dict(primary)
    primary_results = primary.get("results", []) if isinstance(primary.get("results"), list) else []
    backup_results = backup.get("results", []) if isinstance(backup.get("results"), list) else []
    merged_results = _dedupe_result_dicts(primary_results + backup_results)

    primary_errors = primary.get("errors", []) if isinstance(primary.get("errors"), list) else []
    backup_errors = backup.get("errors", []) if isinstance(backup.get("errors"), list) else []
    merged_errors = list(primary_errors)
    for err in backup_errors:
        if err not in merged_errors:
            merged_errors.append(err)

    merged["success"] = len(merged_results) > 0
    merged["results"] = merged_results
    merged["total_results"] = len(merged_results)
    merged["errors"] = merged_errors
    merged["citations"] = build_web_citations(merged_results, query=query, prefix="W")
    merged["comparison"] = build_comparison_summary(merged_results)
    merged["references_text"] = format_reference_block(merged["citations"], max_items=40)
    merged["search_summary"] = (
        f"平台级策略合并结果，共 {len(merged_results)} 条；"
        f"主链路 {len(primary_results)} 条，备份链路 {len(backup_results)} 条"
    )
    return merged


def _finalize_payload_with_extensions(
    payload: Dict[str, Any],
    query: str,
    mode: str,
    source: str = "advanced_search",
) -> Dict[str, Any]:
    """
    统一补充：
    - postprocess 扩展
    - 全局上下文事件
    """
    result = dict(payload or {})
    result, post_report = run_post_processors(
        result,
        PostProcessContext(
            query=query,
            mode=mode,
            metadata={
                "total_results": int(result.get("total_results", 0) or 0),
            },
        ),
    )
    result["postprocess"] = post_report

    try:
        context_store = get_global_deep_context()
        event = context_store.record(
            event_type=f"{mode}_complete",
            source=source,
            payload={
                "query": query,
                "total_results": int(result.get("total_results", 0) or 0),
                "errors": list(result.get("errors", []) or [])[:6],
                "top_urls": [
                    item.get("url")
                    for item in (result.get("results", []) if isinstance(result.get("results"), list) else [])[:10]
                    if isinstance(item, dict) and item.get("url")
                ],
            },
        )
        result["global_context_event_id"] = event.get("id")
        result["global_context_size"] = context_store.size
    except Exception as exc:
        logger.debug("record global context failed: %s", exc)

    return result


async def _run_platform_backup_search(
    query: str,
    target_domains: List[str],
    profile: Optional[str],
    intent_hint: Optional[str] = None,
    use_english: bool = False,
) -> Dict[str, Any]:
    """平台站点直连结果不足时，使用通用搜索引擎 + site:domain 兜底。"""
    _ = profile  # reserved for future per-profile backup tuning
    if not target_domains:
        return {"success": False, "results": [], "errors": ["no_target_domains"]}

    normalized_domains: List[str] = []
    seen_domains = set()
    for raw_domain in target_domains:
        domain = str(raw_domain or "").strip().lower()
        if not domain or domain in seen_domains:
            continue
        seen_domains.add(domain)
        normalized_domains.append(domain)

    if not normalized_domains:
        return {"success": False, "results": [], "errors": ["no_normalized_target_domains"]}

    # 站点级备份优先探测命中率较高的域名，避免短链/高挑战域名耗尽预算。
    indexed_domains = list(enumerate(normalized_domains))
    indexed_domains.sort(
        key=lambda pair: (
            _get_backup_domain_priority(pair[1]) + _domain_auth_priority_boost(pair[1]),
            -pair[0],
        ),
        reverse=True,
    )
    prioritized_domains = [domain for _, domain in indexed_domains]

    # 平台兜底场景优先保证可达性，中文环境默认走 Baidu/Bing。
    backup_engines = (
        [
            AdvancedSearchEngine.GOOGLE,
            AdvancedSearchEngine.BING,
            AdvancedSearchEngine.QUARK,
            AdvancedSearchEngine.BAIDU,
            AdvancedSearchEngine.DUCKDUCKGO,
        ]
        if use_english
        else [AdvancedSearchEngine.QUARK, AdvancedSearchEngine.BAIDU]
    )
    max_domains = max(2, int(os.getenv("WEB_ROOTER_PLATFORM_BACKUP_DOMAINS", "6")))
    task_timeout = max(25, int(os.getenv("WEB_ROOTER_PLATFORM_BACKUP_TIMEOUT_SEC", "80")))

    deep_search = DeepSearchEngine()
    merged_results: List[Dict[str, Any]] = []
    merged_errors: List[str] = []
    used_queries: List[str] = []

    try:
        for domain in prioritized_domains[:max_domains]:
            domain_hint = _get_backup_domain_query_hint(domain)
            query_with_hint = " ".join(
                part
                for part in [
                    str(query or "").strip(),
                    str(intent_hint or "").strip(),
                    domain_hint,
                ]
                if part
            ).strip()
            domain_query = f"{query_with_hint or query} site:{domain}"
            used_queries.append(domain_query)
            try:
                response = await asyncio.wait_for(
                    deep_search.deep_search(
                        domain_query,
                        num_results=6,
                        use_english=use_english,
                        engines=backup_engines,
                        crawl_top=0,
                        query_variants=1,
                        channel_profiles=None,
                    ),
                    timeout=task_timeout,
                )
            except asyncio.TimeoutError:
                merged_errors.append(f"platform backup timeout for {domain}")
                continue
            except Exception as exc:
                merged_errors.append(str(exc))
                continue

            if isinstance(response, dict):
                if isinstance(response.get("results"), list):
                    merged_results.extend(response["results"])
                if isinstance(response.get("errors"), list):
                    for err in response["errors"]:
                        if err not in merged_errors:
                            merged_errors.append(err)
    finally:
        await deep_search.close()

    deduped = _dedupe_result_dicts(merged_results)
    citations = build_web_citations(deduped, query=query, prefix="W")
    return {
        "success": len(deduped) > 0,
        "query": query,
        "queries_used": used_queries,
        "total_results": len(deduped),
        "results": deduped,
        "errors": merged_errors,
        "citations": citations,
        "comparison": build_comparison_summary(deduped),
        "references_text": format_reference_block(citations, max_items=40),
    }


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
        platforms = ["xiaohongshu", "zhihu", "tieba", "douyin", "bilibili", "weibo", "reddit", "twitter"]

    engines = []
    platform_map = {
        "xiaohongshu": AdvancedSearchEngine.XIAOHONGSHU,
        "xhs": AdvancedSearchEngine.XIAOHONGSHU,
        "bilibili": AdvancedSearchEngine.BILIBILI,
        "bili": AdvancedSearchEngine.BILIBILI,
        "zhihu": AdvancedSearchEngine.ZHIHU,
        "tieba": AdvancedSearchEngine.TIEBA,
        "douyin": AdvancedSearchEngine.DOUYIN,
        "weibo": AdvancedSearchEngine.WEIBO,
        "reddit": AdvancedSearchEngine.REDDIT,
        "twitter": AdvancedSearchEngine.TWITTER,
        "x": AdvancedSearchEngine.TWITTER,
        "hackernews": AdvancedSearchEngine.HACKERNEWS,
    }
    platform_domains = {
        "xiaohongshu": ["xiaohongshu.com", "xhslink.com"],
        "xhs": ["xiaohongshu.com", "xhslink.com"],
        "zhihu": ["zhihu.com"],
        "tieba": ["tieba.baidu.com"],
        "douyin": ["douyin.com", "iesdouyin.com"],
        "bilibili": ["bilibili.com"],
        "bili": ["bilibili.com"],
        "weibo": ["weibo.com", "weibo.cn"],
        "reddit": ["reddit.com"],
        "twitter": ["x.com", "twitter.com"],
        "x": ["x.com", "twitter.com"],
        "hackernews": ["news.ycombinator.com"],
    }
    selected_domains: List[str] = []

    for platform in platforms:
        normalized = str(platform or "").strip().lower()
        if normalized in platform_map:
            engine = platform_map[normalized]
            if engine not in engines:
                engines.append(engine)
        for domain in platform_domains.get(normalized, []):
            if domain not in selected_domains:
                selected_domains.append(domain)

    if not engines:
        engines = [
            AdvancedSearchEngine.XIAOHONGSHU,
            AdvancedSearchEngine.ZHIHU,
            AdvancedSearchEngine.TIEBA,
            AdvancedSearchEngine.DOUYIN,
            AdvancedSearchEngine.BILIBILI,
            AdvancedSearchEngine.WEIBO,
        ]
        selected_domains = [
            "xiaohongshu.com",
            "zhihu.com",
            "tieba.baidu.com",
            "douyin.com",
            "bilibili.com",
            "weibo.com",
        ]

    deep_search = DeepSearchEngine()
    try:
        primary = await deep_search.deep_search(
            query,
            num_results=10,
            use_english=False,
            engines=engines,
        )
    finally:
        await deep_search.close()

    min_expected = max(2, min(len(engines), 4))
    required_high_signal = max(1, min_expected - 1)
    comment_intent = _has_comment_intent(query)
    primary = _refine_platform_payload(
        primary,
        query=query,
        mode="social",
        target_domains=selected_domains,
    )
    primary_results = int(primary.get("total_results", 0) or 0)
    primary_high_signal = _count_high_signal_results(
        primary.get("results", []) if isinstance(primary.get("results"), list) else [],
        query=query,
        target_domains=selected_domains,
        mode="social",
    )
    force_low_signal_backup = str(os.getenv("WEB_ROOTER_FORCE_PLATFORM_BACKUP_ON_LOW_SIGNAL", "0")).lower() in {
        "1", "true", "yes", "on"
    }
    require_high_signal = str(os.getenv("WEB_ROOTER_REQUIRE_HIGH_SIGNAL_PRIMARY", "0")).lower() in {
        "1", "true", "yes", "on"
    }
    enforce_high_signal = require_high_signal or comment_intent
    if primary_results >= min_expected and (
        primary_high_signal >= required_high_signal
        or (not force_low_signal_backup and not enforce_high_signal)
    ):
        primary["success"] = True
        primary = _attach_platform_runtime_hints(
            primary,
            target_domains=selected_domains,
            mode="social",
        )
        return _finalize_payload_with_extensions(
            payload=primary,
            query=query,
            mode="social_search",
            source="advanced_search_social",
        )

    backup = await _run_platform_backup_search(
        query=query,
        target_domains=selected_domains,
        profile="platforms",
        intent_hint="评论 讨论 用户反馈 弹幕" if comment_intent else None,
        use_english=False,
    )
    merged = _merge_search_payload(primary, backup, query=query)
    merged = _refine_platform_payload(
        merged,
        query=query,
        mode="social",
        target_domains=selected_domains,
    )
    merged = _attach_platform_runtime_hints(
        merged,
        target_domains=selected_domains,
        mode="social",
    )
    return _finalize_payload_with_extensions(
        payload=merged,
        query=query,
        mode="social_search",
        source="advanced_search_social",
    )


async def search_commerce(
    query: str,
    platforms: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    搜索电商和本地生活平台

    Args:
        query: 搜索关键词
        platforms: 指定平台（默认全部）

    Returns:
        搜索结果
    """
    if platforms is None:
        platforms = ["taobao", "jd", "pinduoduo", "meituan"]

    engines = []
    platform_map = {
        "taobao": AdvancedSearchEngine.TAOBAO,
        "tmall": AdvancedSearchEngine.TAOBAO,
        "jd": AdvancedSearchEngine.JD,
        "jingdong": AdvancedSearchEngine.JD,
        "pinduoduo": AdvancedSearchEngine.PINDUODUO,
        "pdd": AdvancedSearchEngine.PINDUODUO,
        "meituan": AdvancedSearchEngine.MEITUAN,
        "dianping": AdvancedSearchEngine.MEITUAN,
    }
    platform_domains = {
        "taobao": ["taobao.com", "tmall.com"],
        "tmall": ["tmall.com", "taobao.com"],
        "jd": ["jd.com"],
        "jingdong": ["jd.com"],
        "pinduoduo": ["pinduoduo.com", "yangkeduo.com"],
        "pdd": ["pinduoduo.com", "yangkeduo.com"],
        "meituan": ["meituan.com", "dianping.com"],
        "dianping": ["dianping.com", "meituan.com"],
    }
    selected_domains: List[str] = []

    for platform in platforms:
        normalized = str(platform or "").strip().lower()
        if normalized in platform_map:
            engine = platform_map[normalized]
            if engine not in engines:
                engines.append(engine)
        for domain in platform_domains.get(normalized, []):
            if domain not in selected_domains:
                selected_domains.append(domain)

    if not engines:
        engines = [
            AdvancedSearchEngine.TAOBAO,
            AdvancedSearchEngine.JD,
            AdvancedSearchEngine.PINDUODUO,
            AdvancedSearchEngine.MEITUAN,
        ]
        selected_domains = [
            "taobao.com",
            "tmall.com",
            "jd.com",
            "pinduoduo.com",
            "yangkeduo.com",
            "meituan.com",
            "dianping.com",
        ]

    deep_search = DeepSearchEngine()
    try:
        primary = await deep_search.deep_search(
            query,
            num_results=12,
            use_english=False,
            engines=engines,
            channel_profiles=["commerce"] if not platforms else None,
        )
    finally:
        await deep_search.close()

    min_expected = max(2, min(len(engines), 4))
    required_high_signal = max(1, min_expected - 1)
    comment_intent = _has_comment_intent(query)
    primary = _refine_platform_payload(
        primary,
        query=query,
        mode="commerce",
        target_domains=selected_domains,
    )
    primary_results = int(primary.get("total_results", 0) or 0)
    primary_high_signal = _count_high_signal_results(
        primary.get("results", []) if isinstance(primary.get("results"), list) else [],
        query=query,
        target_domains=selected_domains,
        mode="commerce",
    )
    force_low_signal_backup = str(os.getenv("WEB_ROOTER_FORCE_PLATFORM_BACKUP_ON_LOW_SIGNAL", "0")).lower() in {
        "1", "true", "yes", "on"
    }
    require_high_signal = str(os.getenv("WEB_ROOTER_REQUIRE_HIGH_SIGNAL_PRIMARY", "0")).lower() in {
        "1", "true", "yes", "on"
    }
    enforce_high_signal = require_high_signal or comment_intent
    if primary_results >= min_expected and (
        primary_high_signal >= required_high_signal
        or (not force_low_signal_backup and not enforce_high_signal)
    ):
        primary["success"] = True
        primary = _attach_platform_runtime_hints(
            primary,
            target_domains=selected_domains,
            mode="commerce",
        )
        return _finalize_payload_with_extensions(
            payload=primary,
            query=query,
            mode="commerce_search",
            source="advanced_search_commerce",
        )

    backup = await _run_platform_backup_search(
        query=query,
        target_domains=selected_domains,
        profile="commerce",
        intent_hint="评价 评论 开箱 购买反馈" if comment_intent else None,
        use_english=False,
    )
    merged = _merge_search_payload(primary, backup, query=query)
    merged = _refine_platform_payload(
        merged,
        query=query,
        mode="commerce",
        target_domains=selected_domains,
    )
    merged = _attach_platform_runtime_hints(
        merged,
        target_domains=selected_domains,
        mode="commerce",
    )
    return _finalize_payload_with_extensions(
        payload=merged,
        query=query,
        mode="commerce_search",
        source="advanced_search_commerce",
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
    try:
        return await deep_search.deep_search(
            query,
            num_results=15,
            use_english=True,  # 技术内容默认用英文搜索
            engines=engines,
        )
    finally:
        await deep_search.close()

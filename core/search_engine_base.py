"""
可配置的搜索引擎基类
灵感来自 playwright-search-mcp 的 ConfigurableSearchEngine

功能:
- 配置驱动的搜索引擎
- 统一的搜索接口
- 反爬虫检测和处理
- HTML 保存功能
"""
import asyncio
import json
import os
from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List
import logging

from playwright.async_api import Page, BrowserContext
from core.engine_config import EngineConfig, ConfigLoader
from core.universal_parser import UniversalResultParser
from core.browser import BrowserManager, AntiBotActions, SearchResult, EngineState

logger = logging.getLogger(__name__)


class BaseSearchEngine(ABC):
    """
    搜索引擎基类 - 提供通用的搜索功能
    """

    def __init__(
        self,
        engine_id: str,
        browser_manager: BrowserManager,
        config: Optional[EngineConfig] = None,
        options: Optional[Dict[str, Any]] = None,
    ):
        self.engine_id = engine_id
        self.browser_manager = browser_manager
        self.config = config or ConfigLoader.get_instance().get_engine_config(engine_id)
        self.options = options or {}
        self.parser: Optional[UniversalResultParser] = None
        self._page: Optional[Page] = None

        if self.config:
            self.parser = UniversalResultParser(self.config)

    @abstractmethod
    async def search(self, query: str, limit: int = 10) -> SearchResult:
        """
        执行搜索

        Args:
            query: 搜索查询
            limit: 结果数量限制

        Returns:
            SearchResult: 搜索结果
        """
        pass

    def build_search_url(self, query: str) -> str:
        """构建搜索 URL"""
        if not self.config:
            raise ValueError("引擎配置未加载")

        encoded_query = query.replace(' ', '+')
        return f"{self.config.baseUrl}{self.config.searchPath}{encoded_query}"

    async def setup_page_headers(self, page: Page) -> None:
        """设置页面头信息"""
        if self.config and self.config.headers:
            await page.set_extra_http_headers(self.config.headers)

    async def navigate_to_search_page(self, page: Page, query: str) -> None:
        """导航到搜索页面"""
        search_url = self.build_search_url(query)
        logger.info(f"正在导航到{self.config.name if self.config else self.engine_id}搜索页面：{search_url}")

        await page.goto(search_url, wait_until="domcontentloaded")

    async def wait_for_page_load(self, page: Page, timeout: int = 15000) -> None:
        """等待页面加载"""
        if not self.config:
            return

        result_selector = self.config.selectors.get('resultContainer', '')
        if result_selector:
            try:
                await page.wait_for_selector(result_selector, timeout=timeout)
            except asyncio.TimeoutError:
                logger.warning(f"等待搜索结果超时，继续处理")

    async def handle_anti_bot(self, page: Page) -> None:
        """处理反爬虫检测"""
        if not self.config:
            return

        anti_bot_config = self.config.antiBot
        if not anti_bot_config or not anti_bot_config.enabled:
            return

        logger.info(f"开始检测{self.config.name}反爬虫机制...")

        anti_bot = AntiBotActions(page)

        # 检查特定的反爬虫检测器
        detectors = anti_bot_config.detectors
        if detectors:
            for selector in detectors:
                try:
                    if await anti_bot.check_for_captcha([selector]):
                        error_msg = anti_bot_config.errorMessage or f"{self.config.name}检测到验证"
                        logger.warning(error_msg)
                        await anti_bot.handle_captcha(error_msg)
                except Exception as e:
                    logger.debug(f"检查选择器 {selector} 失败：{e}")

        # 执行基本反检测措施
        await anti_bot.perform_anti_detection()

    async def save_html(self, page: Page, query: str, output_dir: str = "search_results") -> Optional[str]:
        """保存 HTML 内容"""
        if not self.options.get('save_html'):
            return None

        try:
            html = await page.content()
            timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            filename = f"{self.engine_id}_{query.replace(' ', '_')}_{timestamp}.html"

            output_path = Path(output_dir) / filename
            output_path.parent.mkdir(parents=True, exist_ok=True)

            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(html)

            logger.info(f"HTML 内容已保存到：{output_path}")
            return str(output_path)

        except Exception as e:
            logger.error(f"保存 HTML 失败：{e}")
            return None

    @staticmethod
    def clean_text(text: Optional[str]) -> str:
        """清理文本"""
        if not text:
            return ""

        import re
        # 移除零宽字符
        text = re.sub(r'[\u200B-\u200D\uFEFF]', '', text)
        # 规范化空白
        text = ' '.join(text.split())
        # 移除首尾空白
        text = text.strip()

        return text

    @staticmethod
    def is_valid_link(href: str, base_url: str = "") -> bool:
        """验证链接"""
        try:
            from urllib.parse import urlparse, urljoin
            full_url = urljoin(base_url, href)
            parsed = urlparse(full_url)
            return parsed.scheme in ('http', 'https')
        except Exception:
            return False

    async def get_page(self) -> Page:
        """获取页面实例"""
        if self._page is None:
            if not self.browser_manager._context:
                await self.browser_manager.start(self.engine_id)
            self._page = await self.browser_manager._context.new_page()
        return self._page

    async def close_page(self) -> None:
        """关闭页面"""
        if self._page:
            await self._page.close()
            self._page = None


class ConfigurableSearchEngine(BaseSearchEngine):
    """
    可配置的搜索引擎实现 - 使用配置驱动
    """

    def __init__(
        self,
        engine_id: str,
        browser_manager: BrowserManager,
        config: Optional[EngineConfig] = None,
        options: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(engine_id, browser_manager, config, options)
        self._start_time: float = 0

    async def search(self, query: str, limit: int = 10) -> SearchResult:
        """执行搜索"""
        import time
        self._start_time = time.time()

        try:
            # 获取页面
            page = await self.get_page()

            # 设置页面头信息
            await self.setup_page_headers(page)

            # 导航到搜索页面
            await self.navigate_to_search_page(page, query)

            # 处理反爬虫检测
            await self.handle_anti_bot(page)

            # 等待页面加载
            await self.wait_for_page_load(page)

            # 保存 HTML（如果配置）
            await self.save_html(page, query)

            # 解析搜索结果
            results = []
            if self.parser:
                results = await self.parser.parse_results(page, limit)
            else:
                # 使用备用解析方法
                results = await self._fallback_parse(page, limit)

            search_time = time.time() - self._start_time

            logger.info(f"{self.config.name if self.config else self.engine_id}搜索完成："
                       f"{len(results)} 个结果，耗时 {search_time:.2f}s")

            return SearchResult(
                query=query,
                engine=self.engine_id,
                url=page.url,
                html=await page.content(),
                title=await page.title(),
                results=results,
                total_results=len(results),
                search_time=search_time,
            )

        except Exception as e:
            logger.error(f"搜索失败：{e}")
            return SearchResult(
                query=query,
                engine=self.engine_id,
                url="",
                html="",
                title="",
                results=[],
                total_results=0,
                search_time=0,
                error=str(e),
            )

        finally:
            await self.close_page()

    async def _fallback_parse(self, page: Page, limit: int) -> List[Dict[str, str]]:
        """备用解析方法"""
        try:
            # 使用 JavaScript 解析
            parser = UniversalResultParser(self.config) if self.config else None
            if parser:
                return await parser.parse_with_javascript(page)

            # 简单的链接提取
            links = await page.query_selector_all('a[href^="http"]')
            results = []

            for link in links[:limit]:
                href = await link.get_attribute('href')
                text = await link.text_content()
                if href and text.strip():
                    results.append({
                        'title': self.clean_text(text),
                        'link': href,
                        'snippet': '',
                    })

            return results

        except Exception as e:
            logger.error(f"备用解析失败：{e}")
            return []


class SearchEngineFactory:
    """
    搜索引擎工厂 - 创建搜索引擎实例
    """

    _engines: Dict[str, type] = {}
    _aliases: Dict[str, str] = {}

    @classmethod
    def register_engine(cls, engine_id: str, engine_class: type, aliases: Optional[List[str]] = None) -> None:
        """注册搜索引擎"""
        cls._engines[engine_id] = engine_class
        if aliases:
            for alias in aliases:
                cls._aliases[alias] = engine_id

    @classmethod
    def create_engine(
        cls,
        engine_id: str,
        browser_manager: BrowserManager,
        options: Optional[Dict[str, Any]] = None,
    ) -> BaseSearchEngine:
        """创建搜索引擎实例"""
        # 解析别名
        actual_id = cls._aliases.get(engine_id, engine_id)

        if actual_id not in cls._engines:
            # 使用默认的 ConfigurableSearchEngine
            logger.info(f"使用默认搜索引擎：{actual_id}")
            return ConfigurableSearchEngine(actual_id, browser_manager, options=options)

        engine_class = cls._engines[actual_id]
        return engine_class(actual_id, browser_manager, options=options)

    @classmethod
    def get_supported_engines(cls) -> List[str]:
        """获取支持的引擎列表"""
        return list(cls._engines.keys()) + list(cls._aliases.keys())

    @classmethod
    def is_engine_supported(cls, engine_id: str) -> bool:
        """检查引擎是否被支持"""
        actual_id = cls._aliases.get(engine_id, engine_id)
        return actual_id in cls._engines


# 注册默认搜索引擎
SearchEngineFactory.register_engine("google", ConfigurableSearchEngine, ["goog"])
SearchEngineFactory.register_engine("baidu", ConfigurableSearchEngine, ["bd"])
SearchEngineFactory.register_engine("bing", ConfigurableSearchEngine, ["msn"])
SearchEngineFactory.register_engine("duckduckgo", ConfigurableSearchEngine, ["ddg", "duck"])
SearchEngineFactory.register_engine("zhihu", ConfigurableSearchEngine, ["zh"])

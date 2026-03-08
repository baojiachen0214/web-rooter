"""
通用结果解析器 - 解析任何搜索引擎的搜索结果
灵感来自 playwright-search-mcp 的 UniversalResultParser
"""
import re
from typing import List, Dict, Any, Optional
from playwright.async_api import Page
import logging

logger = logging.getLogger(__name__)


class UniversalResultParser:
    """
    通用搜索结果解析器

    功能:
    - 使用配置的选择器解析结果
    - 支持备用选择器
    - 链接验证
    - 文本清理
    """

    def __init__(self, engine_config: Any):
        """
        初始化解析器

        Args:
            engine_config: 引擎配置对象（来自 EngineConfig）
        """
        self.config = engine_config
        self.selectors = engine_config.selectors if hasattr(engine_config, 'selectors') else {}
        self.fallback_selector = (
            engine_config.fallbackSelector
            if hasattr(engine_config, 'fallbackSelector')
            else 'div:has(a[href*="http"])'
        )
        self.link_validation = (
            engine_config.linkValidation
            if hasattr(engine_config, 'linkValidation')
            else ['http']
        )

    async def parse_results(
        self,
        page: Page,
        limit: int = 10,
    ) -> List[Dict[str, str]]:
        """
        解析搜索结果

        Args:
            page: Playwright Page 对象
            limit: 结果数量限制

        Returns:
            搜索结果列表
        """
        results = []

        try:
            # 使用配置的选择器查找结果容器
            result_containers = await self._find_result_containers(page)

            if not result_containers:
                logger.warning(f"未找到搜索结果容器，尝试使用备用选择器：{self.fallback_selector}")
                result_containers = await page.query_selector_all(self.fallback_selector)

            logger.info(f"找到 {len(result_containers)} 个结果容器")

            # 解析每个结果容器
            for container in result_containers[:limit]:
                try:
                    result = await self._parse_result_container(container)
                    if result and self._validate_result(result):
                        results.append(result)

                        if len(results) >= limit:
                            break

                except Exception as e:
                    logger.debug(f"解析单个结果失败：{e}")
                    continue

        except Exception as e:
            logger.error(f"解析搜索结果失败：{e}")

        return results

    async def _find_result_containers(self, page: Page) -> List[Any]:
        """查找结果容器"""
        if not self.selectors:
            return []

        result_selector = self.selectors.get('resultContainer', '')
        if not result_selector:
            return []

        # 支持多个选择器（用逗号分隔）
        selectors = [s.strip() for s in result_selector.split(',')]

        for selector in selectors:
            try:
                containers = await page.query_selector_all(selector)
                if containers:
                    logger.info(f"使用选择器 '{selector}' 找到 {len(containers)} 个结果")
                    return containers
            except Exception as e:
                logger.debug(f"选择器 '{selector}' 失败：{e}")

        return []

    async def _parse_result_container(self, container: Any) -> Optional[Dict[str, str]]:
        """
        解析单个结果容器

        Args:
            container: 结果容器元素

        Returns:
            解析后的结果字典
        """
        try:
            # 查找标题
            title = await self._extract_text(container, self.selectors.get('title', ''))

            # 查找链接
            link = await self._extract_href(container, self.selectors.get('link', ''))

            # 查找摘要
            snippet = await self._extract_text(container, self.selectors.get('snippet', ''))

            if not link:
                return None

            return {
                'title': self._clean_text(title),
                'link': self._clean_text(link),
                'snippet': self._clean_text(snippet),
            }

        except Exception as e:
            logger.debug(f"解析结果容器失败：{e}")
            return None

    async def _extract_text(self, container: Any, selector: str) -> str:
        """提取文本内容"""
        if not selector:
            return ""

        try:
            # 支持多个选择器
            selectors = [s.strip() for s in selector.split(',')]

            for sel in selectors:
                try:
                    element = await container.query_selector(sel)
                    if element:
                        text = await element.text_content()
                        if text:
                            return text
                except Exception:
                    continue

        except Exception:
            pass

        return ""

    async def _extract_href(self, container: Any, selector: str) -> str:
        """提取链接地址"""
        if not selector:
            return ""

        try:
            # 支持多个选择器
            selectors = [s.strip() for s in selector.split(',')]

            for sel in selectors:
                try:
                    element = await container.query_selector(sel)
                    if element:
                        href = await element.get_attribute('href')
                        if href:
                            # 处理相对 URL
                            if href.startswith('/'):
                                # 需要基础 URL，这里返回原始 href
                                pass
                            return href
                except Exception:
                    continue

        except Exception:
            pass

        return ""

    def _clean_text(self, text: Optional[str]) -> str:
        """清理文本"""
        if not text:
            return ""

        # 移除零宽字符
        text = re.sub(r'[\u200B-\u200D\uFEFF]', '', text)
        # 规范化空白
        text = ' '.join(text.split())
        # 移除首尾空白
        text = text.strip()

        return text

    def _validate_result(self, result: Dict[str, str]) -> bool:
        """验证结果"""
        link = result.get('link', '')

        if not link:
            return False

        # 链接验证
        if self.link_validation:
            for pattern in self.link_validation:
                if pattern.lower() in link.lower():
                    return True
            return False

        # 基本的 http/https 验证
        return link.startswith('http://') or link.startswith('https://')

    async def parse_with_javascript(self, page: Page) -> List[Dict[str, str]]:
        """
        使用 JavaScript 解析结果（当选择器失败时）

        Args:
            page: Playwright Page 对象

        Returns:
            搜索结果列表
        """
        try:
            results = await page.evaluate("""
                () => {
                    const results = [];
                    // 查找所有链接
                    const links = document.querySelectorAll('a[href^="http"]');

                    links.forEach(link => {
                        const title = link.querySelector('h1, h2, h3, .title, [class*="title"]');
                        const snippet = link.querySelector('p, .snippet, .abstract, [class*="snippet"]');

                        results.push({
                            title: title ? title.textContent.trim() : link.textContent.trim(),
                            link: link.href,
                            snippet: snippet ? snippet.textContent.trim() : ''
                        });
                    });

                    return results;
                }
            """)

            # 过滤和清理结果
            cleaned_results = []
            for result in results:
                if result.get('link'):
                    cleaned_results.append({
                        'title': self._clean_text(result.get('title', '')),
                        'link': self._clean_text(result.get('link', '')),
                        'snippet': self._clean_text(result.get('snippet', '')),
                    })

            return cleaned_results

        except Exception as e:
            logger.error(f"使用 JavaScript 解析失败：{e}")
            return []

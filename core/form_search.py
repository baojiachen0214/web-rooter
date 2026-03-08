"""
表单填写和站内搜索模块

支持：
- 自动检测页面搜索框
- 填写表单并提交
- 站内搜索功能
- 处理搜索结果
"""
import asyncio
import re
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any, Tuple
from datetime import datetime
import logging

from core.crawler import Crawler, CrawlResult
from core.parser import Parser, ExtractedData
from core.browser import BrowserManager, BrowserResult

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class FormField:
    """表单字段"""
    name: str
    field_type: str  # text, search, input, textarea, select
    placeholder: Optional[str]
    required: bool
    value: Optional[str] = None
    options: List[str] = field(default_factory=list)  # select 选项


@dataclass
class SearchForm:
    """搜索表单"""
    form_action: str
    form_method: str
    fields: List[FormField]
    submit_button: Optional[str]
    page_url: str


@dataclass
class SearchFormResult:
    """表单搜索结果"""
    success: bool
    query: str
    submitted_url: str
    result_html: str
    extracted_results: List[Dict[str, Any]]
    result_count: int
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "query": self.query,
            "submitted_url": self.submitted_url,
            "result_count": self.result_count,
            "extracted_results": self.extracted_results[:20],
            "error": self.error,
        }


class FormFiller:
    """
    表单填写器

    支持：
    - 自动检测页面表单
    - 识别搜索框
    - 填写并提交表单
    """

    # 搜索框常见 name/id/class
    SEARCH_FIELD_PATTERNS = [
        re.compile(r'search'), re.compile(r'query'), re.compile(r'\bq\b'),
        re.compile(r'keyword'), re.compile(r'\bkw\b'), re.compile(r'\bs\b'),
        re.compile(r'wd'), re.compile(r'查询'), re.compile(r'搜索'),
        re.compile(r'查找'),
    ]

    # 搜索表单常见特征
    SEARCH_FORM_PATTERNS = [
        r'search.*form', r'form.*search', r'search-box', r'searchbox',
    ]

    def __init__(self, browser: Optional[BrowserManager] = None):
        self._browser = browser
        self._crawler = Crawler()

    async def _ensure_browser(self):
        """确保浏览器已初始化"""
        if self._browser is None:
            self._browser = BrowserManager()
            await self._browser.start()

    async def close(self):
        """关闭"""
        await self._crawler.close()
        if self._browser:
            await self._browser.close()

    async def detect_search_forms(self, url: str) -> List[SearchForm]:
        """
        检测页面搜索表单

        Args:
            url: 页面 URL

        Returns:
            搜索表单列表
        """
        try:
            result = await self._crawler.fetch(url)
            if not result.success:
                return []

            return self._parse_forms(result.html, url)
        except Exception as e:
            logger.warning(f"Error detecting forms on {url}: {e}")
            return []

    async def fill_and_submit(
        self,
        url: str,
        form_data: Dict[str, str],
        form_index: int = 0,
        use_browser: bool = True,
        wait_for: Optional[str] = None,
    ) -> SearchFormResult:
        """
        填写表单并提交

        Args:
            url: 页面 URL
            form_data: 表单数据 {name: value}
            form_index: 表单索引（如果页面有多个表单）
            use_browser: 是否使用浏览器（推荐用于 JS 表单）
            wait_for: 提交后等待的选择器

        Returns:
            搜索结果
        """
        if use_browser:
            return await self._fill_and_submit_browser(url, form_data, form_index, wait_for)
        else:
            return await self._fill_and_submit_crawler(url, form_data, form_index)

    async def _fill_and_submit_browser(
        self,
        url: str,
        form_data: Dict[str, str],
        form_index: int,
        wait_for: Optional[str],
    ) -> SearchFormResult:
        """使用浏览器填写并提交表单"""
        await self._ensure_browser()

        try:
            page = await self._browser._context.new_page()
            page.set_default_timeout(30000)

            # 导航到页面
            await page.goto(url, wait_until="domcontentloaded")

            # 等待表单加载
            await page.wait_for_load_state("networkidle")

            # 填写表单
            for name, value in form_data.items():
                try:
                    # 尝试多种选择器
                    selectors = [
                        f"[name='{name}']",
                        f"[id='{name}']",
                        f"[class*='{name}']",
                    ]
                    for selector in selectors:
                        try:
                            await page.fill(selector, value, timeout=1000)
                            break
                        except:
                            continue
                except Exception as e:
                    logger.warning(f"Could not fill field {name}: {e}")

            # 提交表单
            query = list(form_data.values())[0] if form_data else ""

            # 尝试点击提交按钮
            submit_selectors = [
                "button[type='submit']",
                "input[type='submit']",
                "[class*='search-btn']",
                "[class*='submit']",
                "form button",
            ]
            for selector in submit_selectors:
                try:
                    await page.click(selector, timeout=1000)
                    break
                except:
                    continue
            else:
                # 如果没有找到提交按钮，模拟回车提交
                await page.press("input[type='search']", "Enter")

            # 等待结果
            if wait_for:
                try:
                    await page.wait_for_selector(wait_for, timeout=5000)
                except:
                    pass
            else:
                await page.wait_for_load_state("networkidle")

            # 获取结果
            result_html = await page.content()
            result_url = page.url

            await page.close()

            # 解析结果
            extracted = self._parse_search_results(result_html, result_url, query)

            return SearchFormResult(
                success=True,
                query=query,
                submitted_url=result_url,
                result_html=result_html[:10000],
                extracted_results=extracted,
                result_count=len(extracted),
            )

        except Exception as e:
            logger.exception(f"Error in fill_and_submit_browser")
            return SearchFormResult(
                success=False,
                query=str(form_data),
                submitted_url=url,
                result_html="",
                extracted_results=[],
                result_count=0,
                error=str(e),
            )

    async def _fill_and_submit_crawler(
        self,
        url: str,
        form_data: Dict[str, str],
        form_index: int,
    ) -> SearchFormResult:
        """使用爬虫提交表单（仅限 GET 表单）"""
        try:
            # 先获取页面找到表单 action
            result = await self._crawler.fetch(url)
            if not result.success:
                return SearchFormResult(
                    success=False, query="", submitted_url=url,
                    result_html="", extracted_results=[], result_count=0,
                    error=f"Failed to fetch page: {result.error}"
                )

            forms = self._parse_forms(result.html, url)
            if not forms or form_index >= len(forms):
                return SearchFormResult(
                    success=False, query="", submitted_url=url,
                    result_html="", extracted_results=[], result_count=0,
                    error="No form found"
                )

            form = forms[form_index]
            query = list(form_data.values())[0] if form_data else ""

            # 构建提交 URL
            if form.form_method.upper() == "GET":
                from urllib.parse import urlencode, urljoin
                action_url = urljoin(url, form.form_action) if form.form_action else url
                submit_url = f"{action_url}?{urlencode(form_data)}"
                submit_result = await self._crawler.fetch(submit_url)
            else:
                # POST 表单需要使用浏览器
                return await self._fill_and_submit_browser(url, form_data, form_index, None)

            if not submit_result.success:
                return SearchFormResult(
                    success=False, query=query, submitted_url=url,
                    result_html="", extracted_results=[], result_count=0,
                    error=f"Form submission failed: {submit_result.error}"
                )

            # 解析结果
            extracted = self._parse_search_results(submit_result.html, submit_result.url, query)

            return SearchFormResult(
                success=True,
                query=query,
                submitted_url=submit_result.url,
                result_html=submit_result.html[:10000],
                extracted_results=extracted,
                result_count=len(extracted),
            )

        except Exception as e:
            logger.exception(f"Error in fill_and_submit_crawler")
            return SearchFormResult(
                success=False, query="", submitted_url=url,
                result_html="", extracted_results=[], result_count=0,
                error=str(e)
            )

    async def site_search(
        self,
        base_url: str,
        query: str,
        search_path: Optional[str] = None,
        use_browser: bool = True,
    ) -> SearchFormResult:
        """
        站内搜索快捷方法

        Args:
            base_url: 网站基础 URL
            query: 搜索词
            search_path: 搜索路径（如 /search, /s 等）
            use_browser: 是否使用浏览器

        Returns:
            搜索结果
        """
        from urllib.parse import urljoin, urlparse

        # 尝试常见搜索路径
        search_paths = [
            search_path,
            "/search",
            "/s",
            "/query",
            "/find",
            "/articles/search",
            "/papers/search",
        ]

        for path in search_paths:
            if path is None:
                continue
            search_url = urljoin(base_url, path)
            try:
                result = await self.fill_and_submit(
                    search_url,
                    {"q": query, "query": query, "search": query},
                    use_browser=use_browser,
                )
                if result.success and result.result_count > 0:
                    return result
            except Exception as e:
                logger.warning(f"Search at {search_url} failed: {e}")

        # 如果直接访问搜索路径失败，尝试先检测表单
        forms = await self.detect_search_forms(base_url)
        if forms:
            return await self.fill_and_submit(
                base_url,
                {"q": query},
                use_browser=use_browser,
            )

        return SearchFormResult(
            success=False, query=query, submitted_url=base_url,
            result_html="", extracted_results=[], result_count=0,
            error="Could not find search form"
        )

    def _parse_forms(self, html: str, base_url: str) -> List[SearchForm]:
        """解析页面表单"""
        parser = Parser().parse(html, base_url)
        forms = []

        for form_tag in parser.soup.find_all("form"):
            action = form_tag.get("action", "")
            method = form_tag.get("method", "get")

            fields = []
            for input_tag in form_tag.find_all(["input", "textarea", "select"]):
                name = input_tag.get("name", "")
                if not name:
                    continue

                field_type = input_tag.get("type", "text")
                if input_tag.name == "textarea":
                    field_type = "textarea"
                elif input_tag.name == "select":
                    field_type = "select"

                # 获取选项
                options = []
                if input_tag.name == "select":
                    for option in input_tag.find_all("option"):
                        options.append(option.get("value") or option.get_text(strip=True))

                fields.append(FormField(
                    name=name,
                    field_type=field_type,
                    placeholder=input_tag.get("placeholder"),
                    required=input_tag.has_attr("required"),
                    options=options,
                ))

            # 查找提交按钮
            submit_button = None
            submit_tag = form_tag.find("button", type="submit") or form_tag.find("input", type="submit")
            if submit_tag:
                submit_button = submit_tag.get("value") or submit_tag.get_text(strip=True)

            forms.append(SearchForm(
                form_action=action,
                form_method=method,
                fields=fields,
                submit_button=submit_button,
                page_url=base_url,
            ))

        return forms

    def _is_search_field(self, field: FormField) -> bool:
        """判断是否为搜索字段"""
        patterns = self.SEARCH_FIELD_PATTERNS
        name_lower = field.name.lower()
        placeholder_lower = (field.placeholder or "").lower()

        return any(
            re.search(p, name_lower) or re.search(p, placeholder_lower)
            for p in patterns
        )

    def _parse_search_results(
        self,
        html: str,
        url: str,
        query: str,
    ) -> List[Dict[str, Any]]:
        """解析搜索结果"""
        parser = Parser().parse(html, url)
        results = []

        # 常见搜索结果容器选择器
        result_selectors = [
            ".search-result",
            ".result",
            ".search-item",
            ".item",
            "article",
            ".post",
            ".docsum-content",
            ".gs_ri",
            "[data-layout='result']",
            ".media-item",
            ".repo-list-item",
        ]

        for selector in result_selectors:
            items = parser.soup.select(selector)
            if items:
                for item in items[:20]:
                    title_tag = item.find(["h1", "h2", "h3", "h4", "a"])
                    desc_tag = item.find(["p", ".description", ".snippet", ".abstract"])

                    if title_tag:
                        title = title_tag.get_text(strip=True)[:200]
                        link_tag = title_tag.find("a") or title_tag
                        link = link_tag.get("href", "") if link_tag else ""

                        results.append({
                            "title": title,
                            "url": link if link.startswith("http") else f"{url}{link}",
                            "description": desc_tag.get_text(strip=True)[:300] if desc_tag else "",
                        })

                if results:
                    break

        return results


async def auto_search(
    url: str,
    query: str,
    use_browser: bool = True,
) -> SearchFormResult:
    """
    自动检测并提交搜索

    Args:
        url: 网站 URL
        query: 搜索词
        use_browser: 是否使用浏览器

    Returns:
        搜索结果
    """
    filler = FormFiller()
    try:
        # 先尝试检测表单
        forms = await filler.detect_search_forms(url)
        if forms:
            # 找到搜索字段
            search_fields = {}
            for form in forms:
                for field in form.fields:
                    if filler._is_search_field(field):
                        search_fields[field.name] = query
                        break
                if search_fields:
                    return await filler.fill_and_submit(
                        url, search_fields, use_browser=use_browser
                    )

        # 如果没有检测到表单，尝试常见搜索路径
        return await filler.site_search(url, query, use_browser=use_browser)
    finally:
        await filler.close()

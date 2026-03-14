"""
表单填写和站内搜索模块

支持：
- 自动检测页面搜索框
- 填写表单并提交
- 站内搜索功能
- 处理搜索结果
"""
import asyncio
import json
import re
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any, Tuple
from datetime import datetime
from urllib.parse import quote_plus, urlparse, urljoin
import logging

try:
    from core.parser import Parser, ExtractedData
except ModuleNotFoundError as exc:  # pragma: no cover - optional runtime dependency
    Parser = None  # type: ignore[assignment]
    ExtractedData = Any  # type: ignore[misc,assignment]
    _PARSER_IMPORT_ERROR: Optional[Exception] = exc
else:
    _PARSER_IMPORT_ERROR = None

try:
    from core.crawler import Crawler, CrawlResult
except ModuleNotFoundError as exc:  # pragma: no cover - optional runtime dependency
    Crawler = None  # type: ignore[assignment]
    CrawlResult = Any  # type: ignore[misc,assignment]
    _CRAWLER_IMPORT_ERROR: Optional[Exception] = exc
else:
    _CRAWLER_IMPORT_ERROR = None

try:
    from core.browser import BrowserManager, BrowserResult
except ModuleNotFoundError as exc:  # pragma: no cover - optional runtime dependency
    BrowserManager = None  # type: ignore[assignment]
    BrowserResult = Any  # type: ignore[misc,assignment]
    _BROWSER_IMPORT_ERROR: Optional[Exception] = exc
else:
    _BROWSER_IMPORT_ERROR = None


def _build_parser():
    if Parser is None:
        raise RuntimeError(
            "HTML parser runtime is unavailable. Install optional dependencies from requirements.txt."
        ) from _PARSER_IMPORT_ERROR
    return Parser()

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
    KNOWN_SEARCH_URL_TEMPLATES: Dict[str, str] = {
        "github.com": "https://github.com/search?q={query}&type=repositories",
        "stackoverflow.com": "https://stackoverflow.com/search?q={query}",
        "zhihu.com": "https://www.zhihu.com/search?type=content&q={query}",
        "bilibili.com": "https://search.bilibili.com/all?keyword={query}",
        "tieba.baidu.com": "https://tieba.baidu.com/f/search/res?ie=utf-8&qw={query}",
        "taobao.com": "https://s.taobao.com/search?q={query}",
        "jd.com": "https://search.jd.com/Search?keyword={query}&enc=utf-8",
    }
    GITHUB_RESERVED_OWNER_PREFIXES = {
        "about", "apps", "blog", "codespaces", "collections", "contact", "customer-stories",
        "enterprise", "events", "explore", "features", "issues", "login", "marketplace",
        "new", "notifications", "orgs", "pricing", "readme", "resources", "search",
        "security", "settings", "site", "sponsors", "signup", "solutions", "topics", "users",
    }

    def __init__(self, browser: Optional[BrowserManager] = None):
        self._browser = browser
        if Crawler is None:
            raise RuntimeError(
                "Form search runtime is unavailable. Install optional dependencies from requirements.txt."
            ) from _CRAWLER_IMPORT_ERROR
        self._crawler = Crawler()

    async def _ensure_browser(self):
        """确保浏览器已初始化"""
        if self._browser is None:
            if BrowserManager is None:
                raise RuntimeError(
                    "Browser runtime is unavailable. Install optional dependencies from requirements.txt."
                ) from _BROWSER_IMPORT_ERROR
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

            # 尝试等待资源稳定（不阻塞主流程）
            try:
                await page.wait_for_load_state("networkidle", timeout=6000)
            except Exception:
                pass

            # 填写表单
            filled_selector = None
            for name, value in form_data.items():
                selectors = [
                    f"input[name='{name}']",
                    f"textarea[name='{name}']",
                    f"[name='{name}']",
                    f"input[id='{name}']",
                    f"[id='{name}']",
                    f"input[class*='{name}']",
                    f"[class*='{name}']",
                ]
                for selector in selectors:
                    try:
                        locator = page.locator(selector).first
                        if await locator.count() <= 0:
                            continue
                        await locator.fill(value, timeout=1500)
                        filled_selector = selector
                        break
                    except Exception:
                        continue
                if filled_selector:
                    break

            # 通用搜索框兜底
            if not filled_selector:
                fallback_selectors = [
                    "input[name='q']",
                    "input[id='query-builder-test']",
                    "input[name='query']",
                    "input[name='search']",
                    "input[type='search']",
                    "input[placeholder*='Search' i]",
                    "input[placeholder*='搜索']",
                    "input[aria-label*='Search' i]",
                    "input[aria-label*='搜索']",
                ]
                query_value = list(form_data.values())[0] if form_data else ""
                for selector in fallback_selectors:
                    try:
                        locator = page.locator(selector).first
                        if await locator.count() <= 0:
                            continue
                        await locator.fill(query_value, timeout=1500)
                        filled_selector = selector
                        break
                    except Exception:
                        continue

            # 提交表单
            query = list(form_data.values())[0] if form_data else ""

            # 尝试点击提交按钮
            submit_selectors = [
                "button[type='submit']",
                "input[type='submit']",
                "button[aria-label='Search' i]",
                "[class*='search-btn']",
                "[class*='submit']",
                "form button",
            ]
            submitted = False
            for selector in submit_selectors:
                try:
                    await page.click(selector, timeout=1000)
                    submitted = True
                    break
                except Exception:
                    continue

            # 如果没有找到提交按钮，模拟回车提交
            if not submitted:
                enter_targets = []
                if filled_selector:
                    enter_targets.append(filled_selector)
                enter_targets.extend([
                    "input[name='q']",
                    "input[name='query']",
                    "input[name='search']",
                    "input[type='search']",
                    "input",
                ])
                for target in enter_targets:
                    try:
                        await page.press(target, "Enter", timeout=1200)
                        submitted = True
                        break
                    except Exception:
                        continue

            # 最后兜底：构造搜索 URL 直达（对 GitHub 等站点更可靠）
            if not submitted:
                direct_url = self._build_known_site_search_url(page.url or url, query)
                if direct_url:
                    await page.goto(direct_url, wait_until="domcontentloaded")
                    submitted = True

            # 等待结果
            if wait_for:
                try:
                    await page.wait_for_selector(wait_for, timeout=5000)
                except Exception:
                    pass
            else:
                try:
                    await page.wait_for_load_state("networkidle", timeout=8000)
                except Exception:
                    pass

            # 获取结果
            result_html = await page.content()
            result_url = page.url

            # 解析结果
            extracted = self._parse_search_results(result_html, result_url, query)

            # 结果质量不足时，强制直达标准搜索 URL 再解析。
            if not self._is_acceptable_site_result(result_url or url, extracted):
                direct_url = self._build_known_site_search_url(result_url or url, query)
                if direct_url and direct_url != (result_url or url):
                    await page.goto(direct_url, wait_until="domcontentloaded")
                    try:
                        await page.wait_for_load_state("networkidle", timeout=6000)
                    except Exception:
                        pass
                    result_html = await page.content()
                    result_url = page.url
                    extracted = self._parse_search_results(result_html, result_url, query)

            # GitHub 专项兜底：挑战页导致解析不到仓库时切 API。
            if not self._is_acceptable_site_result(result_url or url, extracted) and self._is_github_host(result_url or url):
                api_result = await self._search_github_api(query)
                if api_result.success and api_result.result_count > 0:
                    await page.close()
                    return api_result

            await page.close()

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

        # 平台直达策略（GitHub/StackOverflow 等）
        direct_url = self._build_known_site_search_url(base_url, query)
        if direct_url:
            try:
                direct_result = await self._fetch_search_url(direct_url, query, use_browser=use_browser)
                if direct_result.success and self._is_acceptable_site_result(base_url, direct_result.extracted_results):
                    return direct_result
            except Exception as e:
                logger.warning(f"Direct site search at {direct_url} failed: {e}")

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
                if result.success and self._is_acceptable_site_result(base_url, result.extracted_results):
                    return result
            except Exception as e:
                logger.warning(f"Search at {search_url} failed: {e}")

        # 如果直接访问搜索路径失败，尝试先检测表单
        forms = await self.detect_search_forms(base_url)
        if forms:
            form_result = await self.fill_and_submit(
                base_url,
                {"q": query},
                use_browser=use_browser,
            )
            if form_result.success and self._is_acceptable_site_result(base_url, form_result.extracted_results):
                return form_result

        if self._is_github_host(base_url):
            api_result = await self._search_github_api(query)
            if api_result.success:
                return api_result

        return SearchFormResult(
            success=False, query=query, submitted_url=base_url,
            result_html="", extracted_results=[], result_count=0,
            error="Could not find search form"
        )

    async def _fetch_search_url(
        self,
        search_url: str,
        query: str,
        use_browser: bool = True,
    ) -> SearchFormResult:
        """直接打开搜索 URL 并解析结果。"""
        if use_browser:
            await self._ensure_browser()
            browser_result = await self._browser.fetch(search_url)
            if browser_result.error is None and browser_result.html:
                extracted = self._parse_search_results(browser_result.html, browser_result.url, query)
                return SearchFormResult(
                    success=True,
                    query=query,
                    submitted_url=browser_result.url,
                    result_html=browser_result.html[:10000],
                    extracted_results=extracted,
                    result_count=len(extracted),
                )
            return SearchFormResult(
                success=False,
                query=query,
                submitted_url=search_url,
                result_html="",
                extracted_results=[],
                result_count=0,
                error=browser_result.error or "browser_fetch_failed",
            )

        crawl_result = await self._crawler.fetch(search_url)
        if not crawl_result.success:
            return SearchFormResult(
                success=False,
                query=query,
                submitted_url=search_url,
                result_html="",
                extracted_results=[],
                result_count=0,
                error=crawl_result.error or f"http_{crawl_result.status_code}",
            )

        extracted = self._parse_search_results(crawl_result.html, crawl_result.url, query)
        return SearchFormResult(
            success=True,
            query=query,
            submitted_url=crawl_result.url,
            result_html=crawl_result.html[:10000],
            extracted_results=extracted,
            result_count=len(extracted),
        )

    def _build_known_site_search_url(self, base_url: str, query: str) -> Optional[str]:
        """根据站点域名构造标准搜索 URL。"""
        host = (urlparse(base_url).hostname or "").lower()
        if not host:
            return None

        for domain, template in self.KNOWN_SEARCH_URL_TEMPLATES.items():
            if host == domain or host.endswith("." + domain):
                return template.format(query=quote_plus(query))
        return None

    @staticmethod
    def _is_github_host(url_or_host: str) -> bool:
        host = (urlparse(url_or_host).hostname or url_or_host or "").lower()
        return host == "github.com" or host.endswith(".github.com")

    @staticmethod
    def _is_github_repo_url(url: str) -> bool:
        parsed = urlparse(url or "")
        host = (parsed.hostname or "").lower()
        if "github.com" not in host:
            return False
        match = re.match(r"^/([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+)/?$", parsed.path or "")
        if not match:
            return False
        owner = (match.group(1) or "").lower()
        return owner not in FormFiller.GITHUB_RESERVED_OWNER_PREFIXES

    def _is_acceptable_site_result(self, site_url: str, results: List[Dict[str, Any]]) -> bool:
        if not results:
            return False
        if self._is_github_host(site_url):
            return any(self._is_github_repo_url(item.get("url", "")) for item in results if isinstance(item, dict))
        return True

    async def _search_github_api(self, query: str) -> SearchFormResult:
        api_url = (
            "https://api.github.com/search/repositories"
            f"?q={quote_plus(query)}&sort=stars&order=desc&per_page=20"
        )
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        result = await self._crawler.fetch(api_url, headers=headers, use_cache=False)
        if not result.success:
            return SearchFormResult(
                success=False,
                query=query,
                submitted_url=api_url,
                result_html="",
                extracted_results=[],
                result_count=0,
                error=result.error or f"http_{result.status_code}",
            )

        try:
            payload = json.loads(result.html or "{}")
        except json.JSONDecodeError as exc:
            return SearchFormResult(
                success=False,
                query=query,
                submitted_url=api_url,
                result_html=(result.html or "")[:2000],
                extracted_results=[],
                result_count=0,
                error=f"github_api_json_decode_error: {exc}",
            )

        items = payload.get("items", []) if isinstance(payload, dict) else []
        extracted: List[Dict[str, Any]] = []
        for item in items[:20]:
            if not isinstance(item, dict):
                continue
            extracted.append({
                "title": item.get("full_name") or item.get("name") or "",
                "url": item.get("html_url") or "",
                "description": (item.get("description") or "")[:300],
            })

        return SearchFormResult(
            success=len(extracted) > 0,
            query=query,
            submitted_url=api_url,
            result_html=(result.html or "")[:10000],
            extracted_results=extracted,
            result_count=len(extracted),
            error=None if extracted else "github_api_no_results",
        )

    def _parse_forms(self, html: str, base_url: str) -> List[SearchForm]:
        """解析页面表单"""
        parser = _build_parser().parse(html, base_url)
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
        parser = _build_parser().parse(html, url)
        results = []
        parsed_current = urlparse(url or "")
        host = (parsed_current.hostname or "").lower()
        path = parsed_current.path or "/"

        # GitHub 搜索结果页专用解析：优先提取仓库链接，避免被星标数等次级链接干扰。
        if "github.com" in host and path.startswith("/search"):
            seen_repo_urls = set()
            for a_tag in parser.soup.select("a[href]"):
                href = (a_tag.get("href") or "").strip()
                if not href:
                    continue
                full_url = href
                if href.startswith("/"):
                    full_url = f"https://github.com{href}"
                elif href.startswith("http://") or href.startswith("https://"):
                    full_url = href
                else:
                    continue

                parsed_repo = urlparse(full_url)
                if "github.com" not in (parsed_repo.hostname or "").lower():
                    continue
                if not self._is_github_repo_url(full_url):
                    continue
                if full_url in seen_repo_urls:
                    continue
                seen_repo_urls.add(full_url)

                title = a_tag.get_text(" ", strip=True) or parsed_repo.path.strip("/")
                container = a_tag.find_parent(["li", "article", "div"])
                description = container.get_text(" ", strip=True)[:300] if container else ""
                results.append({
                    "title": title[:200],
                    "url": full_url,
                    "description": description,
                })
                if len(results) >= 20:
                    break

            if results:
                return results

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
            "[data-testid='results-list'] li",
            "[data-testid='result-list'] li",
            "div[data-hpc] li",
            "main ul li",
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
                            "url": link if link.startswith("http") else urljoin(url, link),
                            "description": desc_tag.get_text(strip=True)[:300] if desc_tag else "",
                        })

                if results:
                    break

        if results and "github.com" in host:
            repo_url_pattern = re.compile(r"^/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+/?$")
            filtered: List[Dict[str, Any]] = []
            for item in results:
                item_url = item.get("url", "")
                parsed_item = urlparse(item_url)
                if (parsed_item.hostname or "").lower().endswith("github.com") and repo_url_pattern.match(parsed_item.path or ""):
                    filtered.append(item)

            # 仅在非搜索页强制过滤，避免主页导航链接被误判为搜索结果。
            if not path.startswith("/search"):
                results = filtered

        # GitHub 仓库链接兜底提取
        if not results:
            seen = set()
            for a_tag in parser.soup.select("a[href]"):
                href = (a_tag.get("href") or "").strip()
                full_url = href
                if href.startswith("/"):
                    full_url = f"https://github.com{href}"
                elif href.startswith("http://") or href.startswith("https://"):
                    full_url = href
                else:
                    continue

                parsed = urlparse(full_url)
                host = (parsed.hostname or "").lower()
                if "github.com" not in host:
                    continue
                if not self._is_github_repo_url(full_url):
                    continue
                if full_url in seen:
                    continue
                seen.add(full_url)

                title = a_tag.get_text(strip=True) or parsed.path.strip("/")
                parent_text = a_tag.parent.get_text(" ", strip=True) if a_tag.parent else ""
                results.append({
                    "title": title[:200],
                    "url": full_url,
                    "description": parent_text[:300],
                })
                if len(results) >= 20:
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
        # 优先走站点策略（已内置平台直达、常见搜索路径、表单检测回退）。
        return await filler.site_search(url, query, use_browser=use_browser)
    finally:
        await filler.close()

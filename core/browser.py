"""
浏览器自动化 - 处理 JavaScript 渲染的页面
"""
import asyncio
from typing import Optional, Dict, Any, List
from dataclasses import dataclass
import logging

from playwright.async_api import async_playwright, Browser, Page, BrowserContext
from config import browser_config, BrowserConfig

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class BrowserResult:
    """浏览器渲染结果"""
    url: str
    html: str
    title: str
    screenshot: Optional[bytes] = None
    console_logs: List[str] = None
    error: Optional[str] = None

    def __post_init__(self):
        if self.console_logs is None:
            self.console_logs = []


class BrowserManager:
    """浏览器管理器 - 使用 Playwright"""

    def __init__(self, config: Optional[BrowserConfig] = None):
        self.config = config or browser_config
        self._playwright = None
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None

    async def start(self):
        """启动浏览器"""
        self._playwright = await async_playwright().start()

        # 启动浏览器（优先 Chromium）
        self._browser = await self._playwright.chromium.launch(
            headless=self.config.HEADLESS,
            args=[
                "--disable-gpu",
                "--disable-dev-shm-usage",
                "--no-sandbox",
            ]
        )

        # 创建上下文
        context_options = {
            "viewport": {"width": 1920, "height": 1080},
            "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        }

        if self.config.BLOCK_IMAGES:
            context_options["permissions"] = []

        self._context = await self._browser.new_context(**context_options)

        # 拦截资源以加快速度
        if self.config.BLOCK_IMAGES or self.config.BLOCK_FONTS:
            await self._context.route("**/*", self._route_handler)

        logger.info("Browser started")

    async def _route_handler(self, route):
        """资源拦截"""
        resource_type = route.request.resource_type
        if self.config.BLOCK_IMAGES and resource_type == "image":
            await route.abort()
        elif self.config.BLOCK_FONTS and resource_type == "font":
            await route.abort()
        else:
            await route.continue_()

    async def close(self):
        """关闭浏览器"""
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()
        logger.info("Browser closed")

    async def __aenter__(self) -> "BrowserManager":
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()

    async def fetch(
        self,
        url: str,
        wait_for: Optional[str] = None,
        wait_for_timeout: int = 5000,
        scroll: bool = False,
        take_screenshot: bool = False,
        javascript: Optional[str] = None,
    ) -> BrowserResult:
        """
        使用浏览器获取页面（支持 JavaScript）

        Args:
            url: 目标 URL
            wait_for: 等待的 CSS 选择器
            wait_for_timeout: 等待超时（毫秒）
            scroll: 是否滚动到底部
            take_screenshot: 是否截图
            javascript: 执行的 JavaScript 代码

        Returns:
            BrowserResult: 渲染后的结果
        """
        if not self._browser:
            await self.start()

        console_logs = []

        try:
            page = await self._context.new_page()

            # 收集控制台日志
            page.on("console", lambda msg: console_logs.append(msg.text))

            # 设置超时
            page.set_default_timeout(self.config.TIMEOUT)

            # 导航到页面
            await page.goto(url, wait_until="networkidle" if self.config.WAIT_FOR_NETWORK else "domcontentloaded")

            # 等待特定元素
            if wait_for:
                try:
                    await page.wait_for_selector(wait_for, timeout=wait_for_timeout)
                except asyncio.TimeoutError:
                    logger.warning(f"Timeout waiting for {wait_for}")

            # 执行自定义 JavaScript
            if javascript:
                await page.evaluate(javascript)

            # 滚动页面
            if scroll:
                await self._scroll_to_bottom(page)

            # 截图
            screenshot = None
            if take_screenshot:
                screenshot = await page.screenshot(full_page=True)

            # 获取内容
            html = await page.content()
            title = await page.title()

            await page.close()

            return BrowserResult(
                url=url,
                html=html,
                title=title,
                screenshot=screenshot,
                console_logs=console_logs,
            )

        except Exception as e:
            logger.exception(f"Error fetching {url}")
            return BrowserResult(
                url=url,
                html="",
                title="",
                error=str(e),
            )

    async def _scroll_to_bottom(self, page: Page):
        """滚动到页面底部"""
        await page.evaluate("""
            () => new Promise((resolve) => {
                let scrollHeight = document.body.scrollHeight;
                let totalHeight = 0;
                let distance = 500;
                let timer = setInterval(() => {
                    window.scrollBy(0, distance);
                    totalHeight += distance;
                    if (totalHeight >= scrollHeight) {
                        clearInterval(timer);
                        resolve();
                    }
                    if (document.body.scrollHeight - window.scrollY - window.innerHeight < 100) {
                        clearInterval(timer);
                        resolve();
                    }
                }, 100);
            })
        """)

    async def click_and_wait(
        self,
        url: str,
        selector: str,
        wait_for_selector: Optional[str] = None,
    ) -> BrowserResult:
        """点击元素并等待"""
        if not self._browser:
            await self.start()

        try:
            page = await self._context.new_page()
            page.set_default_timeout(self.config.TIMEOUT)

            await page.goto(url, wait_until="domcontentloaded")

            # 点击元素
            await page.click(selector)

            # 等待新内容
            if wait_for_selector:
                await page.wait_for_selector(wait_for_selector)
            else:
                await page.wait_for_load_state("networkidle")

            html = await page.content()
            title = await page.title()

            await page.close()

            return BrowserResult(
                url=page.url,
                html=html,
                title=title,
            )

        except Exception as e:
            logger.exception(f"Error in click_and_wait")
            return BrowserResult(
                url=url,
                html="",
                title="",
                error=str(e),
            )

    async def fill_and_submit(
        self,
        url: str,
        form_data: Dict[str, str],
        submit_selector: str = "button[type='submit']",
    ) -> BrowserResult:
        """填写表单并提交"""
        if not self._browser:
            await self.start()

        try:
            page = await self._context.new_page()
            page.set_default_timeout(self.config.TIMEOUT)

            await page.goto(url, wait_until="domcontentloaded")

            # 填写表单
            for selector, value in form_data.items():
                await page.fill(selector, value)

            # 提交
            await page.click(submit_selector)
            await page.wait_for_load_state("networkidle")

            html = await page.content()
            title = await page.title()

            await page.close()

            return BrowserResult(
                url=page.url,
                html=html,
                title=title,
            )

        except Exception as e:
            logger.exception(f"Error in fill_and_submit")
            return BrowserResult(
                url=url,
                html="",
                title="",
                error=str(e),
            )

    async def get_interactive(self, url: str) -> tuple[Page, BrowserResult]:
        """
        获取交互式页面（用于后续操作）
        返回 page 对象，使用完后需要手动关闭
        """
        if not self._browser:
            await self.start()

        page = await self._context.new_page()
        page.set_default_timeout(self.config.TIMEOUT)

        await page.goto(url, wait_until="networkidle")

        result = BrowserResult(
            url=page.url,
            html=await page.content(),
            title=await page.title(),
        )

        return page, result

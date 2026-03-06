"""
核心爬虫 - 处理网页抓取
"""
import asyncio
import aiohttp
import hashlib
from dataclasses import dataclass, field
from typing import Optional, Dict, List, Any
from datetime import datetime
import logging

from config import crawler_config, CrawlerConfig

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class CrawlResult:
    """爬取结果"""
    url: str
    status_code: int
    html: str
    headers: Dict[str, str] = field(default_factory=dict)
    cookies: Dict[str, str] = field(default_factory=dict)
    response_time: float = 0.0
    timestamp: datetime = field(default_factory=datetime.now)
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def success(self) -> bool:
        return self.status_code == 200 and self.error is None

    @property
    def content_hash(self) -> str:
        return hashlib.md5(self.html.encode()).hexdigest()


class Crawler:
    """异步网页爬虫"""

    def __init__(self, config: Optional[CrawlerConfig] = None):
        self.config = config or crawler_config
        self._session: Optional[aiohttp.ClientSession] = None
        self._request_delay = self.config.REQUEST_DELAY
        self._last_request_time = 0.0

    async def __aenter__(self):
        await self._init_session()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()

    async def _init_session(self):
        """初始化 HTTP 会话"""
        if self._session is None:
            timeout = aiohttp.ClientTimeout(total=self.config.TIMEOUT)
            self._session = aiohttp.ClientSession(
                headers={"User-Agent": self.config.USER_AGENT},
                timeout=timeout,
                cookie_jar=aiohttp.CookieJar()
            )

    async def close(self):
        """关闭会话"""
        if self._session:
            await self._session.close()
            self._session = None

    async def fetch(
        self,
        url: str,
        method: str = "GET",
        data: Optional[Dict] = None,
        headers: Optional[Dict[str, str]] = None,
        follow_redirects: bool = True,
    ) -> CrawlResult:
        """
        获取网页内容

        Args:
            url: 目标 URL
            method: HTTP 方法
            data: 请求数据
            headers: 额外请求头
            follow_redirects: 是否跟随重定向

        Returns:
            CrawlResult: 爬取结果
        """
        await self._init_session()

        # 限流控制
        await self._rate_limit()

        start_time = asyncio.get_event_loop().time()

        try:
            merged_headers = {**self._default_headers, **(headers or {})}

            async with self._session.request(
                method,
                url,
                data=data,
                headers=merged_headers,
                allow_redirects=follow_redirects,
            ) as response:
                html = await response.text(errors="ignore")
                response_time = asyncio.get_event_loop().time() - start_time

                result = CrawlResult(
                    url=str(response.url),
                    status_code=response.status,
                    html=html,
                    headers=dict(response.headers),
                    cookies={k: v.value for k, v in response.cookies.items()},
                    response_time=response_time,
                )

                logger.info(f"Fetched {url} - Status: {response.status}")
                return result

        except asyncio.TimeoutError:
            return CrawlResult(
                url=url,
                status_code=0,
                html="",
                error=f"Timeout after {self.config.TIMEOUT}s",
            )
        except aiohttp.ClientError as e:
            return CrawlResult(
                url=url,
                status_code=0,
                html="",
                error=str(e),
            )
        except Exception as e:
            logger.exception(f"Unexpected error fetching {url}")
            return CrawlResult(
                url=url,
                status_code=0,
                html="",
                error=str(e),
            )

    async def fetch_with_retry(
        self,
        url: str,
        retries: Optional[int] = None,
    ) -> CrawlResult:
        """带重试的 fetch"""
        retries = retries if retries is not None else self.config.MAX_RETRIES

        last_result = None
        for attempt in range(retries + 1):
            result = await self.fetch(url)

            if result.success:
                return result

            last_result = result
            if attempt < retries:
                wait_time = self.config.RETRY_DELAY * (2 ** attempt)
                logger.warning(f"Retry {attempt + 1}/{retries} for {url} after {wait_time}s")
                await asyncio.sleep(wait_time)

        return last_result

    async def _rate_limit(self):
        """请求限流"""
        now = asyncio.get_event_loop().time()
        elapsed = now - self._last_request_time
        if elapsed < self._request_delay:
            await asyncio.sleep(self._request_delay - elapsed)
        self._last_request_time = asyncio.get_event_loop().time()

    @property
    def _default_headers(self) -> Dict[str, str]:
        return {
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Accept-Encoding": "gzip, deflate",
            "Connection": "keep-alive",
        }

    async def fetch_multiple(
        self,
        urls: List[str],
        concurrent: Optional[int] = None,
    ) -> List[CrawlResult]:
        """并发抓取多个 URL"""
        concurrent = concurrent or self.config.MAX_CONCURRENT

        semaphore = asyncio.Semaphore(concurrent)

        async def bounded_fetch(url: str) -> CrawlResult:
            async with semaphore:
                return await self.fetch(url)

        tasks = [bounded_fetch(url) for url in urls]
        return await asyncio.gather(*tasks)

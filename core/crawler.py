"""
核心爬虫 - 处理网页抓取
增强版：添加代理轮换、缓存和连接池功能
"""
import asyncio
import aiohttp
import hashlib
import random
import time
from dataclasses import dataclass, field
from typing import Optional, Dict, List, Any
from datetime import datetime
import logging

from config import crawler_config, CrawlerConfig, ProxyConfig, ProxyRotationStrategy
from core.cache import RequestCache
from core.connection_pool import ConnectionPool, PooledSession

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


class ProxyRotator:
    """
    代理轮换器

    支持：
    - 循环轮换策略
    - 随机轮换策略
    - 基于成功率的轮换策略
    - 线程安全
    """

    def __init__(self, config: Optional[ProxyConfig] = None):
        self.config = config or ProxyConfig()
        self._proxies: List[Dict[str, str]] = []
        self._failed_proxies: set = set()
        self._proxy_stats: Dict[str, Dict[str, Any]] = {}
        self._current_index = 0
        self._lock = asyncio.Lock()
        self._reuse_count: Dict[str, int] = {}
        self._initialize_proxies()

    def _initialize_proxies(self):
        """初始化代理列表"""
        for proxy_url in self.config.PROXIES:
            proxy = self._parse_proxy(proxy_url)
            if proxy:
                self._proxies.append(proxy)
                self._proxy_stats[proxy_url] = {
                    "success": 0,
                    "failure": 0,
                    "last_used": None,
                }
                self._reuse_count[proxy_url] = 0
        logger.info(f"Initialized {len(self._proxies)} proxies")

    def _parse_proxy(self, proxy_str: str) -> Optional[Dict[str, str]]:
        """解析代理字符串"""
        try:
            if proxy_str.startswith("http://") or proxy_str.startswith("https://"):
                return {"http": proxy_str, "https": proxy_str}
            elif ":" in proxy_str:
                # 格式：host:port 或 user:pass@host:port
                return {"http": f"http://{proxy_str}", "https": f"http://{proxy_str}"}
            else:
                logger.warning(f"Invalid proxy format: {proxy_str}")
                return None
        except Exception as e:
            logger.error(f"Error parsing proxy {proxy_str}: {e}")
            return None

    async def get_proxy(self) -> Optional[Dict[str, str]]:
        """获取一个代理"""
        async with self._lock:
            if not self._proxies:
                return None

            strategy = self.config.ROTATION_STRATEGY

            if strategy == ProxyRotationStrategy.ROUND_ROBIN:
                proxy = self._get_round_robin()
            elif strategy == ProxyRotationStrategy.RANDOM:
                proxy = self._get_random()
            elif strategy == ProxyRotationStrategy.SUCCESS_BASED:
                proxy = self._get_success_based()
            else:
                proxy = self._get_round_robin()

            # 检查是否达到重用次数
            if proxy:
                proxy_key = self._get_proxy_key(proxy)
                if self._reuse_count.get(proxy_key, 0) >= self.config.MAX_REUSE:
                    logger.info(f"Proxy {proxy_key} reached max reuse, rotating")
                    self._failed_proxies.add(proxy_key)
                    return await self.get_proxy()  # 递归获取下一个

            return proxy

    def _get_round_robin(self) -> Optional[Dict[str, str]]:
        """循环轮换"""
        if not self._proxies:
            return None

        # 过滤失败的代理
        available = [p for p in self._proxies if self._get_proxy_key(p) not in self._failed_proxies]
        if not available:
            # 所有代理都失败，重置失败列表
            self._failed_proxies.clear()
            self._current_index = 0
            available = self._proxies

        proxy = available[self._current_index % len(available)]
        self._current_index += 1
        return proxy

    def _get_random(self) -> Optional[Dict[str, str]]:
        """随机选择"""
        available = [p for p in self._proxies if self._get_proxy_key(p) not in self._failed_proxies]
        if not available:
            self._failed_proxies.clear()
            available = self._proxies
        return random.choice(available) if available else None

    def _get_success_based(self) -> Optional[Dict[str, str]]:
        """基于成功率选择"""
        best_proxy = None
        best_score = -1

        for proxy in self._proxies:
            key = self._get_proxy_key(proxy)
            if key in self._failed_proxies:
                continue

            stats = self._proxy_stats.get(key, {"success": 0, "failure": 0})
            total = stats["success"] + stats["failure"]
            if total == 0:
                score = 0.5  # 新代理默认分数
            else:
                score = stats["success"] / total

            if score > best_score:
                best_score = score
                best_proxy = proxy

        return best_proxy

    def _get_proxy_key(self, proxy: Dict[str, str]) -> str:
        """获取代理标识"""
        return proxy.get("http", "") or proxy.get("https", "")

    async def record_success(self, proxy: Dict[str, str]):
        """记录成功"""
        key = self._get_proxy_key(proxy)
        if key in self._proxy_stats:
            self._proxy_stats[key]["success"] += 1
            self._proxy_stats[key]["last_used"] = datetime.now().isoformat()
        self._reuse_count[key] = self._reuse_count.get(key, 0) + 1

    async def record_failure(self, proxy: Dict[str, str]):
        """记录失败"""
        key = self._get_proxy_key(proxy)
        if key in self._proxy_stats:
            self._proxy_stats[key]["failure"] += 1

            # 检查是否达到失败阈值
            if self.config.AUTO_DETECT_FAILURE:
                failures = self._proxy_stats[key]["failure"]
                if failures >= self.config.FAILURE_THRESHOLD:
                    self._failed_proxies.add(key)
                    logger.warning(f"Proxy {key} marked as failed (failures: {failures})")

    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        return {
            "total_proxies": len(self._proxies),
            "failed_proxies": len(self._failed_proxies),
            "proxy_stats": self._proxy_stats,
        }

    def reset_failures(self):
        """重置失败记录"""
        self._failed_proxies.clear()
        logger.info("Reset all proxy failures")

    def add_proxy(self, proxy_str: str):
        """添加代理"""
        proxy = self._parse_proxy(proxy_str)
        if proxy:
            self._proxies.append(proxy)
            key = self._get_proxy_key(proxy)
            self._proxy_stats[key] = {"success": 0, "failure": 0, "last_used": None}
            self._reuse_count[key] = 0
            logger.info(f"Added proxy: {proxy_str}")


class Crawler:
    """异步网页爬虫（支持代理轮换、缓存和连接池）"""

    def __init__(
        self,
        config: Optional[CrawlerConfig] = None,
        proxy_config: Optional[ProxyConfig] = None,
        use_proxy_rotation: bool = False,
        use_cache: bool = True,
        use_connection_pool: bool = True,
        cache_ttl: Optional[int] = 3600,
        cache_db_path: Optional[str] = None,
    ):
        self.config = config or crawler_config
        self._session: Optional[aiohttp.ClientSession] = None
        self._request_delay = self.config.REQUEST_DELAY
        self._last_request_time = 0.0

        # 代理轮换器
        self._use_proxy_rotation = use_proxy_rotation
        self._proxy_rotator: Optional[ProxyRotator] = None
        if proxy_config or (use_proxy_rotation and proxy_config.PROXIES):
            self._proxy_rotator = ProxyRotator(proxy_config)

        # 请求缓存
        self._use_cache = use_cache
        self._cache: Optional[RequestCache] = None
        if use_cache:
            self._cache = RequestCache(
                use_memory=True,
                use_sqlite=True,
                db_path=cache_db_path,
                default_ttl=cache_ttl,
            )
            logger.info("Request cache enabled")

        # 连接池
        self._use_connection_pool = use_connection_pool
        self._connection_pool: Optional[ConnectionPool] = None
        if use_connection_pool:
            self._connection_pool = ConnectionPool(
                max_size=50,
                min_size=5,
            )
            logger.info("Connection pool enabled")

        # 性能统计
        self._cache_hits = 0
        self._cache_misses = 0
        self._pool_hits = 0
        self._pool_misses = 0

    async def __aenter__(self):
        await self._init_session()
        if self._connection_pool:
            await self._connection_pool.start()
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

        if self._connection_pool:
            await self._connection_pool.stop()

        if self._cache:
            self._cache.close()

        logger.info("Crawler closed")

    async def fetch(
        self,
        url: str,
        method: str = "GET",
        data: Optional[Dict] = None,
        headers: Optional[Dict[str, str]] = None,
        follow_redirects: bool = True,
        use_proxy: bool = True,
        use_cache: Optional[bool] = None,
    ) -> CrawlResult:
        """
        获取网页内容（支持代理、缓存和连接池）

        Args:
            url: 目标 URL
            method: HTTP 方法
            data: 请求数据
            headers: 额外请求头
            follow_redirects: 是否跟随重定向
            use_proxy: 是否使用代理
            use_cache: 是否使用缓存 (None 表示使用默认设置)

        Returns:
            CrawlResult: 爬取结果
        """
        # 检查缓存
        if use_cache is None:
            use_cache = self._use_cache

        if use_cache and self._cache:
            cached_entry = await self._cache.get(url, method)
            if cached_entry:
                self._cache_hits += 1
                logger.debug(f"Cache hit for {url}")
                return CrawlResult(
                    url=url,
                    status_code=cached_entry.status_code,
                    html=cached_entry.response_body.decode() if cached_entry.response_body else "",
                    headers=cached_entry.headers,
                    metadata={"from_cache": True, "cache_hit_count": cached_entry.hit_count},
                )
            self._cache_misses += 1

        await self._init_session()

        # 限流控制
        await self._rate_limit()

        # 获取代理
        proxy = None
        if use_proxy and self._proxy_rotator:
            proxy = await self._proxy_rotator.get_proxy()

        start_time = asyncio.get_event_loop().time()

        try:
            merged_headers = {**self._default_headers, **(headers or {})}

            # 构建请求参数
            request_kwargs = {
                "method": method,
                "url": url,
                "data": data,
                "headers": merged_headers,
                "allow_redirects": follow_redirects,
            }

            # 添加代理
            if proxy:
                request_kwargs["proxy"] = proxy

            # 使用连接池或默认 session
            if self._connection_pool and not proxy:
                async with PooledSession(self._connection_pool, url) as session:
                    async with session.request(**request_kwargs) as response:
                        result = await self._process_response(response, url, start_time)
                        self._pool_hits += 1
            else:
                async with self._session.request(**request_kwargs) as response:
                    result = await self._process_response(response, url, start_time)
                    self._pool_misses += 1

            # 缓存结果
            if use_cache and self._cache and result.success:
                await self._cache.set(
                    url=url,
                    response_body=result.html.encode() if result.html else b"",
                    status_code=result.status_code,
                    headers=result.headers,
                    method=method,
                )

            return result

        except asyncio.TimeoutError:
            # 记录代理失败
            if proxy and self._proxy_rotator:
                await self._proxy_rotator.record_failure(proxy)

            return CrawlResult(
                url=url,
                status_code=0,
                html="",
                error=f"Timeout after {self.config.TIMEOUT}s",
            )
        except aiohttp.ClientError as e:
            # 检查是否是代理错误
            error_str = str(e)
            is_proxy_error = any(
                keyword in error_str.lower()
                for keyword in ["proxy", "tunnel", "connect", "err_proxy"]
            )

            if is_proxy_error and proxy and self._proxy_rotator:
                await self._proxy_rotator.record_failure(proxy)
                logger.warning(f"Proxy error, rotating: {error_str}")

            return CrawlResult(
                url=url,
                status_code=0,
                html="",
                error=str(e),
            )
        except Exception as e:
            # 记录代理失败
            if proxy and self._proxy_rotator:
                await self._proxy_rotator.record_failure(proxy)

            logger.exception(f"Unexpected error fetching {url}")
            return CrawlResult(
                url=url,
                status_code=0,
                html="",
                error=str(e),
            )

    async def _process_response(
        self,
        response: aiohttp.ClientResponse,
        url: str,
        start_time: float,
    ) -> CrawlResult:
        """处理响应"""
        response_time = asyncio.get_event_loop().time() - start_time

        return CrawlResult(
            url=str(response.url),
            status_code=response.status,
            html=await response.text(errors="ignore"),
            headers=dict(response.headers),
            cookies={k: v.value for k, v in response.cookies.items()},
            response_time=response_time,
            metadata={"from_cache": False, "connection_pool_used": self._connection_pool is not None},
        )

    async def fetch_with_retry(
        self,
        url: str,
        retries: Optional[int] = None,
        use_proxy: bool = True,
    ) -> CrawlResult:
        """带重试的 fetch（支持代理轮换）"""
        retries = retries if retries is not None else self.config.MAX_RETRIES

        last_result = None
        for attempt in range(retries + 1):
            # 每次重试使用不同的代理
            result = await self.fetch(url, use_proxy=use_proxy)

            if result.success:
                return result

            last_result = result
            if attempt < retries:
                wait_time = self.config.RETRY_DELAY * (2 ** attempt)
                logger.warning(f"Retry {attempt + 1}/{retries} for {url} after {wait_time}s")
                await asyncio.sleep(wait_time)

                # 如果有代理轮换器，重置失败记录以尝试所有代理
                if self._proxy_rotator and attempt == retries - 1:
                    self._proxy_rotator.reset_failures()

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

    def get_performance_stats(self) -> Dict[str, Any]:
        """获取性能统计信息"""
        stats = {
            "cache_hits": self._cache_hits,
            "cache_misses": self._cache_misses,
            "cache_hit_rate": self._cache_hits / max(1, self._cache_hits + self._cache_misses),
            "pool_hits": self._pool_hits,
            "pool_misses": self._pool_misses,
            "pool_hit_rate": self._pool_hits / max(1, self._pool_hits + self._pool_misses),
        }

        if self._cache:
            stats["cache"] = self._cache.get_stats()

        if self._connection_pool:
            stats["connection_pool"] = self._connection_pool.get_stats()

        return stats

    async def clear_cache(self, url: Optional[str] = None):
        """
        清除缓存

        Args:
            url: 指定 URL 的缓存，None 表示清空所有
        """
        if not self._cache:
            return

        if url:
            await self._cache.delete(url)
            logger.info(f"Cleared cache for {url}")
        else:
            await self._cache.clear()
            logger.info("Cleared all cache")

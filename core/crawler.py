"""
核心爬虫 - 处理网页抓取
增强版：添加代理轮换、缓存和连接池功能
"""
import asyncio
import aiohttp
import hashlib
import ipaddress
import random
import time
from dataclasses import dataclass, field
from typing import Optional, Dict, List, Any
from datetime import datetime
import logging
from urllib.parse import urlparse

from config import crawler_config, CrawlerConfig, ProxyConfig, ProxyRotationStrategy
from core.cache import RequestCache
from core.connection_pool import ConnectionPool, PooledSession
from core.http_ssl import build_client_ssl_context

try:
    from curl_cffi import requests as curl_requests
except Exception:  # pragma: no cover
    curl_requests = None

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

    _USER_AGENT_POOL = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_5) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Safari/605.1.15",
    ]

    _ACCEPT_LANGUAGE_POOL = [
        "zh-CN,zh;q=0.9,en;q=0.8",
        "en-US,en;q=0.9,zh;q=0.7",
        "en-GB,en;q=0.9",
        "ja-JP,ja;q=0.9,en;q=0.7",
    ]

    _BLOCKED_STATUS = {401, 403, 406, 409, 418, 425, 426, 429, 451, 500, 502, 503, 504, 520, 521, 522, 523, 524, 525}
    _BLOCKED_KEYWORDS = [
        "cloudflare",
        "cf-challenge",
        "captcha",
        "access denied",
        "forbidden",
        "bot detection",
        "robot check",
        "please verify you are human",
    ]
    _TLS_IMPERSONATION_ENGINES = {"google.com", "duckduckgo.com", "bing.com"}
    _TLS_IMPERSONATION_BROWSERS = ("chrome", "edge", "safari")
    _TLS_IMPERSONATION_ATTEMPTS = 3

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
        self._base_user_agent = self.config.USER_AGENT

        # 代理轮换器
        self._use_proxy_rotation = use_proxy_rotation
        self._proxy_rotator: Optional[ProxyRotator] = None
        if proxy_config and proxy_config.PROXIES:
            self._proxy_rotator = ProxyRotator(proxy_config)
        elif use_proxy_rotation:
            logger.warning("Proxy rotation is enabled but no proxies are configured")

        # 请求缓存
        self._use_cache = use_cache
        self._cache: Optional[RequestCache] = None
        if use_cache:
            self._cache = RequestCache(
                use_memory=True,
                use_sqlite=True,
                db_path=cache_db_path,
                memory_max_size=self.config.CACHE_MEMORY_MAX_ENTRIES,
                memory_max_bytes=self.config.CACHE_MEMORY_MAX_BYTES,
                sqlite_max_size=self.config.CACHE_SQLITE_MAX_ENTRIES,
                default_ttl=cache_ttl,
                memory_max_body_bytes=self.config.CACHE_MEMORY_BODY_MAX_BYTES,
                sqlite_max_body_bytes=self.config.CACHE_SQLITE_BODY_MAX_BYTES,
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
            # 优先使用显式 CA/证书包，缺失时自动回退系统证书链。
            ssl_context = build_client_ssl_context()
            connector = aiohttp.TCPConnector(ssl=ssl_context)
            self._session = aiohttp.ClientSession(
                headers={"User-Agent": self._base_user_agent},
                timeout=timeout,
                cookie_jar=aiohttp.CookieJar(),
                connector=connector
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
        proxy_url = None
        if use_proxy and self._proxy_rotator:
            proxy = await self._proxy_rotator.get_proxy()
            proxy_url = self._select_proxy_url(proxy, url)

        start_time = asyncio.get_event_loop().time()
        merged_headers = self._build_request_headers(url, headers=headers)

        try:
            # 构建请求参数
            request_kwargs = {
                "method": method,
                "url": url,
                "data": data,
                "headers": merged_headers,
                "allow_redirects": follow_redirects,
            }

            # 添加代理
            if proxy_url:
                request_kwargs["proxy"] = proxy_url

            # 使用连接池或默认 session
            if self._connection_pool and not proxy_url:
                async with PooledSession(self._connection_pool, url) as session:
                    async with session.request(**request_kwargs) as response:
                        result = await self._process_response(response, url, start_time)
                        self._pool_hits += 1
            else:
                async with self._session.request(**request_kwargs) as response:
                    result = await self._process_response(response, url, start_time)
                    self._pool_misses += 1

            blocked = self._looks_like_blocked_response(result.status_code, result.html)
            if blocked:
                result.error = result.error or "Detected anti-bot challenge page"
                result.metadata["anti_bot_detected"] = True
                if self._should_try_tls_impersonation(url, result.error):
                    tls_result = await self._fetch_with_tls_impersonation(
                        url=url,
                        method=method,
                        data=data,
                        headers=merged_headers,
                        follow_redirects=follow_redirects,
                        proxy_url=proxy_url,
                    )
                    if tls_result and tls_result.success and not self._looks_like_blocked_response(
                        tls_result.status_code,
                        tls_result.html,
                    ):
                        result = tls_result

            if result.cookies:
                await self._store_cookie_map(result.url or url, result.cookies)

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

            if self._should_try_tls_impersonation(url, "timeout"):
                tls_result = await self._fetch_with_tls_impersonation(
                    url=url,
                    method=method,
                    data=data,
                    headers=merged_headers,
                    follow_redirects=follow_redirects,
                    proxy_url=proxy_url,
                )
                if tls_result:
                    return tls_result

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

            if self._should_try_tls_impersonation(url, error_str):
                tls_result = await self._fetch_with_tls_impersonation(
                    url=url,
                    method=method,
                    data=data,
                    headers=merged_headers,
                    follow_redirects=follow_redirects,
                    proxy_url=proxy_url,
                )
                if tls_result:
                    return tls_result

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

            logger.error("Unexpected error fetching %s: %s", url, e)
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
        body_limit = min(
            max(1, int(self.config.MAX_IN_MEMORY_RESPONSE_BYTES)),
            max(1, int(self.config.MAX_FILE_SIZE)),
        )
        body_bytes, truncated = await self._read_response_body(response, body_limit)
        charset = response.charset or "utf-8"
        html = body_bytes.decode(charset, errors="ignore")

        return CrawlResult(
            url=str(response.url),
            status_code=response.status,
            html=html,
            headers=dict(response.headers),
            cookies={k: v.value for k, v in response.cookies.items()},
            response_time=response_time,
            metadata={
                "from_cache": False,
                "connection_pool_used": self._connection_pool is not None,
                "body_bytes": len(body_bytes),
                "body_truncated": truncated,
                "body_limit_bytes": body_limit,
            },
        )

    async def _read_response_body(
        self,
        response: aiohttp.ClientResponse,
        limit_bytes: int,
    ) -> tuple[bytes, bool]:
        """
        Stream response content with a hard cap so a single oversized page does not
        blow up the Python process.
        """
        body = bytearray()
        truncated = False

        async for chunk in response.content.iter_chunked(64 * 1024):
            if not chunk:
                continue
            remaining = limit_bytes - len(body)
            if remaining <= 0:
                truncated = True
                break
            if len(chunk) > remaining:
                body.extend(chunk[:remaining])
                truncated = True
                break
            body.extend(chunk)

        if truncated:
            response.close()

        return bytes(body), truncated

    async def fetch_with_retry(
        self,
        url: str,
        retries: Optional[int] = None,
        use_proxy: bool = True,
    ) -> CrawlResult:
        """带重试的 fetch（支持代理轮换 + 反爬规避头轮换）。"""
        retries = retries if retries is not None else self.config.MAX_RETRIES

        last_result = None
        for attempt in range(retries + 1):
            # 每次重试轮换请求指纹；重试时默认绕过缓存，避免命中挑战页
            rotated_headers = self._build_request_headers(url, attempt=attempt)
            result = await self.fetch(
                url,
                use_proxy=use_proxy,
                use_cache=(attempt == 0),
                headers=rotated_headers,
            )

            blocked = self._looks_like_blocked_response(result.status_code, result.html)
            if blocked and not result.error:
                result.error = "Detected anti-bot challenge page"
                result.metadata["anti_bot_detected"] = True

            if result.success and not blocked:
                return result

            last_result = result
            if attempt < retries:
                wait_time = self.config.RETRY_DELAY * (2 ** attempt) + random.uniform(0, 0.35)
                fail_reason = result.error or f"status={result.status_code}"
                logger.warning(
                    "Retry %s/%s for %s after %.2fs (%s)",
                    attempt + 1,
                    retries,
                    url,
                    wait_time,
                    fail_reason,
                )
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
            "Accept-Language": random.choice(self._ACCEPT_LANGUAGE_POOL),
            "Accept-Encoding": "gzip, deflate",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
        }

    def _build_request_headers(
        self,
        url: str,
        headers: Optional[Dict[str, str]] = None,
        attempt: int = 0,
    ) -> Dict[str, str]:
        """
        构建更接近真实浏览器的请求头。
        参考 Scrapling 指纹思路：动态 UA、语言、Referer 与 Client Hints。
        """
        headers = headers or {}
        final_headers = dict(self._default_headers)

        user_agents = [self._base_user_agent] + self._USER_AGENT_POOL
        ua = user_agents[attempt % len(user_agents)]
        final_headers["User-Agent"] = ua
        final_headers["Accept-Language"] = self._ACCEPT_LANGUAGE_POOL[attempt % len(self._ACCEPT_LANGUAGE_POOL)]
        final_headers["Sec-Fetch-Site"] = "none" if attempt == 0 else "same-origin"
        final_headers["Sec-Fetch-Mode"] = "navigate"
        final_headers["Sec-Fetch-Dest"] = "document"
        final_headers["Sec-Fetch-User"] = "?1"

        # 近似浏览器的 client hints（非严格版本）
        if "Chrome" in ua:
            final_headers["sec-ch-ua"] = '"Chromium";v="126", "Google Chrome";v="126", "Not.A/Brand";v="24"'
            final_headers["sec-ch-ua-mobile"] = "?0"
            final_headers["sec-ch-ua-platform"] = '"Windows"' if "Windows" in ua else '"macOS"' if "Macintosh" in ua else '"Linux"'

        if "Referer" not in headers and "referer" not in headers:
            referer = self._build_convincing_referer(url)
            if referer:
                final_headers["Referer"] = referer

        # 外部 headers 最后覆盖，保留调用方优先级
        final_headers.update(headers)
        return final_headers

    def _build_convincing_referer(self, url: str) -> Optional[str]:
        """构建类似搜索引擎来源的 Referer。"""
        try:
            host = (urlparse(url).hostname or "").lower()
            if not host or host in {"localhost", "127.0.0.1"}:
                return None

            parts = [p for p in host.split(".") if p]
            if len(parts) >= 2:
                keyword = parts[-2]
            else:
                keyword = host
            if not keyword:
                return None
            return f"https://www.google.com/search?q={keyword}"
        except Exception:
            return None

    def _looks_like_blocked_response(self, status_code: int, body: str) -> bool:
        if status_code in self._BLOCKED_STATUS:
            return True

        lowered = (body or "").lower()
        if not lowered:
            return False
        return any(keyword in lowered for keyword in self._BLOCKED_KEYWORDS)

    def _should_try_tls_impersonation(self, url: str, error_text: str) -> bool:
        """
        是否启用 curl_cffi TLS 指纹兜底。
        参考 Scrapling 的 impersonate 思路，在 TLS/连接失败或挑战页时触发。
        """
        if curl_requests is None:
            return False

        parsed = urlparse(url)
        host = (parsed.hostname or "").lower()
        if not host or self._is_private_or_local_host(host):
            return False

        text = (error_text or "").lower()
        anti_bot_markers = [
            "anti-bot",
            "challenge",
            "captcha",
            "verify you are human",
            "cloudflare",
            "forbidden",
            "blocked",
            "access denied",
            "unusual traffic",
            "status=403",
            "status=429",
            "status=503",
        ]
        tls_markers = [
            "ssl",
            "eof",
            "handshake",
            "connect",
            "connection",
            "timeout",
            "reset",
            "specified network name is no longer available",
            "远程主机强迫关闭了一个现有的连接",
            "指定的网络名不再可用",
        ]
        if any(marker in text for marker in anti_bot_markers):
            return True
        if any(marker in text for marker in tls_markers):
            return True

        # 搜索引擎域名默认优先尝试一次指纹兜底
        return any(engine in host for engine in self._TLS_IMPERSONATION_ENGINES)

    @staticmethod
    def _is_private_or_local_host(host: str) -> bool:
        lowered = (host or "").strip().lower()
        if lowered in {"localhost", "::1"}:
            return True
        if lowered.endswith(".local"):
            return True

        try:
            ip = ipaddress.ip_address(lowered.strip("[]"))
            return (
                ip.is_loopback
                or ip.is_private
                or ip.is_link_local
                or ip.is_multicast
                or ip.is_reserved
            )
        except ValueError:
            return False

    async def _fetch_with_tls_impersonation(
        self,
        url: str,
        method: str,
        data: Optional[Dict],
        headers: Optional[Dict[str, str]],
        follow_redirects: bool,
        proxy_url: Optional[str] = None,
    ) -> Optional[CrawlResult]:
        """
        使用 curl_cffi 的浏览器指纹请求进行兜底抓取。
        """
        if curl_requests is None:
            return None

        method_upper = (method or "GET").upper()
        if method_upper not in {"GET", "POST"}:
            return None

        last_exception: Optional[Exception] = None
        blocked_result: Optional[CrawlResult] = None

        for attempt in range(self._TLS_IMPERSONATION_ATTEMPTS):
            start = asyncio.get_event_loop().time()
            impersonate = self._TLS_IMPERSONATION_BROWSERS[attempt % len(self._TLS_IMPERSONATION_BROWSERS)]
            request_headers = self._build_request_headers(url, headers=headers, attempt=attempt + 1)

            def _do_request():
                kwargs = {
                    "url": url,
                    "headers": request_headers,
                    "timeout": max(10, int(self.config.TIMEOUT)),
                    "allow_redirects": follow_redirects,
                    "impersonate": impersonate,
                }
                if proxy_url:
                    kwargs["proxy"] = proxy_url
                if method_upper == "POST" and data is not None:
                    kwargs["data"] = data
                return curl_requests.request(method_upper, **kwargs)

            try:
                response = await asyncio.to_thread(_do_request)
                elapsed = asyncio.get_event_loop().time() - start
                response_cookies: Dict[str, str] = {}
                raw_cookies = getattr(response, "cookies", None)
                if raw_cookies is not None:
                    try:
                        if hasattr(raw_cookies, "get_dict"):
                            response_cookies = {
                                str(k): str(v)
                                for k, v in raw_cookies.get_dict().items()
                                if k
                            }
                        else:
                            response_cookies = {
                                str(cookie.name): str(cookie.value)
                                for cookie in raw_cookies
                                if getattr(cookie, "name", None)
                            }
                    except Exception:
                        response_cookies = {}

                candidate = CrawlResult(
                    url=str(getattr(response, "url", url)),
                    status_code=int(getattr(response, "status_code", 0)),
                    html=getattr(response, "text", "") or "",
                    headers=dict(getattr(response, "headers", {}) or {}),
                    cookies=response_cookies,
                    response_time=elapsed,
                    metadata={
                        "from_cache": False,
                        "connection_pool_used": False,
                        "transport": "curl_cffi_impersonation",
                        "impersonate": impersonate,
                        "attempt": attempt + 1,
                    },
                )

                if self._looks_like_blocked_response(candidate.status_code, candidate.html):
                    candidate.error = "Detected anti-bot challenge page"
                    candidate.metadata["anti_bot_detected"] = True
                    blocked_result = candidate
                    if attempt < self._TLS_IMPERSONATION_ATTEMPTS - 1:
                        await asyncio.sleep(0.25 + attempt * 0.25 + random.uniform(0.05, 0.3))
                        continue

                return candidate
            except Exception as exc:
                last_exception = exc
                if attempt < self._TLS_IMPERSONATION_ATTEMPTS - 1:
                    await asyncio.sleep(0.25 + attempt * 0.25 + random.uniform(0.05, 0.3))

        if blocked_result:
            return blocked_result
        if last_exception:
            logger.debug("curl_cffi TLS 指纹兜底失败 %s: %s", url, last_exception)
        return None

    def _select_proxy_url(self, proxy: Optional[Dict[str, str]], url: str) -> Optional[str]:
        # aiohttp expects proxy as a URL string, not a dict.
        if not proxy:
            return None
        if url.startswith('https://') and proxy.get('https'):
            return proxy['https']
        return proxy.get('http') or proxy.get('https')

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

    async def _store_cookie_map(self, url: str, cookies: Dict[str, str]) -> None:
        """将 cookie 字典写入 aiohttp 会话，用于后续请求复用。"""
        if not cookies:
            return
        await self._init_session()
        if self._session is None:
            return

        cleaned = {
            str(k).strip(): str(v)
            for k, v in (cookies or {}).items()
            if str(k).strip()
        }
        if not cleaned:
            return

        try:
            from yarl import URL

            self._session.cookie_jar.update_cookies(cleaned, response_url=URL(url))
        except Exception as exc:
            logger.debug("写入 cookie 失败（忽略） %s: %s", url, exc)

    async def seed_cookies(self, url: str, cookies: Dict[str, str]) -> int:
        """
        主动注入 cookies（例如浏览器通过挑战页后回灌到 HTTP 抓取链路）。
        返回实际注入数量。
        """
        if not cookies:
            return 0
        cleaned = {
            str(k).strip(): str(v)
            for k, v in cookies.items()
            if str(k).strip()
        }
        if not cleaned:
            return 0
        await self._store_cookie_map(url, cleaned)
        return len(cleaned)

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

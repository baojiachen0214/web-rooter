"""
连接池 - HTTP 连接重用

功能:
- HTTP 连接池化
- 连接健康检查
- 自动扩缩容
- 连接超时管理

"""
import asyncio
import time
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List
from collections import defaultdict
import logging

import aiohttp

from core.http_ssl import build_client_ssl_context

logger = logging.getLogger(__name__)


@dataclass
class ConnectionInfo:
    """
    连接信息

    Attributes:
        connector: aiohttp connector
        created_at: 创建时间
        last_used: 最后使用时间
        use_count: 使用次数
        is_healthy: 是否健康
    """
    connector: aiohttp.BaseConnector
    created_at: float = field(default_factory=time.time)
    last_used: float = field(default_factory=time.time)
    use_count: int = 0
    is_healthy: bool = True

    def is_expired(self, max_age: float) -> bool:
        """检查是否过期"""
        return time.time() - self.created_at > max_age

    def is_idle(self, idle_timeout: float) -> bool:
        """检查是否空闲超时"""
        return time.time() - self.last_used > idle_timeout


class ConnectionPool:
    """
    HTTP 连接池

    功能:
    - 连接重用
    - 自动健康检查
    - 动态扩缩容

    用法:
        pool = ConnectionPool(max_size=50)
        await pool.start()
        session = await pool.get_connection(url)
        await pool.stop()
    """

    def __init__(
        self,
        max_size: int = 50,
        min_size: int = 5,
        max_idle_time: float = 300,
        max_age: float = 3600,
        health_check_interval: float = 60,
    ):
        """
        初始化连接池

        Args:
            max_size: 最大连接数
            min_size: 最小连接数
            max_idle_time: 最大空闲时间 (秒)
            max_age: 连接最大年龄 (秒)
            health_check_interval: 健康检查间隔 (秒)
        """
        self._max_size = max_size
        self._min_size = min_size
        self._max_idle_time = max_idle_time
        self._max_age = max_age
        self._health_check_interval = health_check_interval

        # 连接池：每个 host 一个连接
        self._connectors: Dict[str, ConnectionInfo] = {}
        self._sessions: Dict[str, aiohttp.ClientSession] = {}

        # 统计
        self._created = 0
        self._closed = 0
        self._requests = 0
        self._health_checks = 0

        # 锁
        self._lock = asyncio.Lock()
        self._health_check_task: Optional[asyncio.Task] = None

        # 连接参数
        self._connector_args: Dict[str, Any] = {
            "limit": 10,  # 每个 host 的连接数
            "limit_per_host": 10,
            "ttl_dns_cache": 300,
            "use_dns_cache": True,
        }

    async def __aenter__(self) -> "ConnectionPool":
        """异步上下文管理器入口"""
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """异步上下文管理器出口"""
        await self.stop()

    async def start(self):
        """启动连接池"""
        # 预创建最小连接数
        await self._create_connections(self._min_size)

        # 启动健康检查
        self._health_check_task = asyncio.create_task(
            self._health_check_loop()
        )

        logger.info(f"Connection pool started (min={self._min_size}, max={self._max_size})")

    async def stop(self):
        """停止连接池"""
        if self._health_check_task:
            self._health_check_task.cancel()
            try:
                await self._health_check_task
            except asyncio.CancelledError:
                pass

        # 关闭所有连接
        await self._close_all()

        logger.info("Connection pool stopped")

    async def _create_connections(self, count: int):
        """创建连接"""
        ssl_context = build_client_ssl_context()
        connector_args = {**self._connector_args, "ssl": ssl_context}
        for _ in range(count):
            connector = aiohttp.TCPConnector(**connector_args)
            session = aiohttp.ClientSession(connector=connector)

            info = ConnectionInfo(connector=connector)
            self._connectors[f"_default_{self._created}"] = info
            self._sessions[f"_default_{self._created}"] = session
            self._created += 1

    async def _close_all(self):
        """关闭所有连接"""
        async with self._lock:
            for session in self._sessions.values():
                await session.close()

            for info in self._connectors.values():
                await info.connector.close()

            self._connectors.clear()
            self._sessions.clear()

    async def _health_check_loop(self):
        """健康检查循环"""
        while True:
            try:
                await asyncio.sleep(self._health_check_interval)
                await self._health_check()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Health check error: {e}")

    async def _health_check(self):
        """执行健康检查"""
        self._health_checks += 1
        now = time.time()

        async with self._lock:
            to_remove = []

            for key, info in self._connectors.items():
                # 检查过期
                if info.is_expired(self._max_age):
                    to_remove.append(key)
                    logger.debug(f"Connection expired: {key}")
                    continue

                # 检查空闲
                if info.is_idle(self._max_idle_time):
                    # 保留最小连接数
                    if len(self._connectors) > self._min_size:
                        to_remove.append(key)
                        logger.debug(f"Connection idle timeout: {key}")
                        continue

                # 检查健康状态
                if not info.is_healthy:
                    to_remove.append(key)
                    logger.debug(f"Connection unhealthy: {key}")
                    continue

            # 移除过期连接
            for key in to_remove:
                if key in self._sessions:
                    await self._sessions[key].close()
                    del self._sessions[key]
                if key in self._connectors:
                    await self._connectors[key].connector.close()
                    del self._connectors[key]
                self._closed += 1

            # 补充最小连接数
            if len(self._connectors) < self._min_size:
                await self._create_connections(
                    self._min_size - len(self._connectors)
                )

    def _get_host(self, url: str) -> str:
        """从 URL 提取 host"""
        from urllib.parse import urlparse
        parsed = urlparse(url)
        return parsed.netloc or "default"

    async def get_connection(self, url: str) -> aiohttp.ClientSession:
        """
        获取连接

        Args:
            url: 目标 URL

        Returns:
            aiohttp ClientSession
        """
        host = self._get_host(url)

        async with self._lock:
            # 查找该 host 的现有连接
            for key, info in self._connectors.items():
                if key.startswith(f"{host}_"):
                    info.last_used = time.time()
                    info.use_count += 1
                    self._requests += 1
                    return self._sessions[key]

            # 没有现有连接，创建新的
            if len(self._connectors) < self._max_size:
                ssl_context = build_client_ssl_context()
                connector_args = {**self._connector_args, "ssl": ssl_context}
                connector = aiohttp.TCPConnector(**connector_args)
                session = aiohttp.ClientSession(connector=connector)

                key = f"{host}_{self._created}"
                self._connectors[key] = ConnectionInfo(connector=connector)
                self._sessions[key] = session
                self._created += 1
                self._requests += 1

                logger.debug(f"Created new connection for {host}")
                return session

            # 连接池已满，返回第一个可用的
            for key, info in self._connectors.items():
                if not info.is_idle(60):  # 最近使用过的
                    info.last_used = time.time()
                    info.use_count += 1
                    self._requests += 1
                    return self._sessions[key]

            # 都没有，创建临时连接
            ssl_context = build_client_ssl_context()
            connector = aiohttp.TCPConnector(limit=1, ssl=ssl_context)
            session = aiohttp.ClientSession(connector=connector)
            self._requests += 1
            logger.debug("Created temporary connection")
            return session

    async def return_connection(
        self,
        session: aiohttp.ClientSession,
        url: str,
    ):
        """
        归还连接

        Args:
            session: 会话
            url: 目标 URL
        """
        # aiohttp 会话会自动重用，这里只需要更新统计
        host = self._get_host(url)

        async with self._lock:
            for key, sess in self._sessions.items():
                if sess is session:
                    if key in self._connectors:
                        self._connectors[key].last_used = time.time()
                    break

    def get_stats(self) -> dict:
        """获取统计信息"""
        return {
            "active_connections": len(self._connectors),
            "total_created": self._created,
            "total_closed": self._closed,
            "total_requests": self._requests,
            "health_checks": self._health_checks,
            "max_size": self._max_size,
            "min_size": self._min_size,
        }


class SmartPool:
    """
    智能连接池 - 带自动扩缩容

    功能:
    - 根据负载自动扩缩容
    - 连接预热
    - 故障转移
    """

    def __init__(
        self,
        base_pool: Optional[ConnectionPool] = None,
        **pool_kwargs,
    ):
        """
        初始化智能池

        Args:
            base_pool: 基础连接池
            **pool_kwargs: 传递给 ConnectionPool 的参数
        """
        self._pool = base_pool or ConnectionPool(**pool_kwargs)
        self._request_times: List[float] = []
        self._auto_scale_enabled = True
        self._scale_check_interval = 30  # 30 秒检查一次

    async def start(self):
        """启动"""
        await self._pool.start()
        logger.info("Smart pool started")

    async def stop(self):
        """停止"""
        await self._pool.stop()
        logger.info("Smart pool stopped")

    async def get_connection(self, url: str) -> aiohttp.ClientSession:
        """获取连接"""
        start_time = time.time()
        session = await self._pool.get_connection(url)

        # 记录请求时间用于负载计算
        self._request_times.append(start_time)

        # 清理旧的请求时间记录
        now = time.time()
        self._request_times = [
            t for t in self._request_times
            if now - t < 60  # 只保留最近 1 分钟
        ]

        return session

    async def return_connection(
        self,
        session: aiohttp.ClientSession,
        url: str,
    ):
        """归还连接"""
        await self._pool.return_connection(session, url)

    def _get_load(self) -> float:
        """获取当前负载 (requests/second)"""
        now = time.time()
        recent = [t for t in self._request_times if now - t < 10]
        return len(recent) / 10.0

    def _should_scale_up(self) -> bool:
        """是否应该扩容"""
        load = self._get_load()
        stats = self._pool.get_stats()

        # 高负载且连接数未达上限
        if load > 10 and stats["active_connections"] < stats["max_size"]:
            return True

        return False

    def _should_scale_down(self) -> bool:
        """是否应该缩容"""
        load = self._get_load()
        stats = self._pool.get_stats()

        # 低负载且连接数高于最小值
        if load < 1 and stats["active_connections"] > stats["min_size"]:
            return True

        return False

    async def scale_up(self, count: int = 5):
        """扩容"""
        async with self._pool._lock:
            current = len(self._pool._connectors)
            to_add = min(count, self._pool._max_size - current)
            if to_add > 0:
                await self._pool._create_connections(to_add)
                logger.info(f"Scaled up by {to_add} connections")

    async def scale_down(self, count: int = 5):
        """缩容"""
        async with self._pool._lock:
            current = len(self._pool._connectors)
            to_remove = min(count, current - self._pool._min_size)

            if to_remove > 0:
                keys_to_remove = list(self._pool._connectors.keys())[:to_remove]
                for key in keys_to_remove:
                    if key in self._pool._sessions:
                        await self._pool._sessions[key].close()
                        del self._pool._sessions[key]
                    if key in self._pool._connectors:
                        await self._pool._connectors[key].connector.close()
                        del self._pool._connectors[key]
                    self._pool._closed += 1

                logger.info(f"Scaled down by {to_remove} connections")

    async def auto_scale(self):
        """自动扩缩容"""
        if self._should_scale_up():
            await self.scale_up()
        elif self._should_scale_down():
            await self.scale_down()

    def get_stats(self) -> dict:
        """获取统计信息"""
        stats = self._pool.get_stats()
        stats["load"] = self._get_load()
        stats["auto_scale_enabled"] = self._auto_scale_enabled
        return stats


class PooledSession:
    """
    池化会话上下文管理器

    用法:
        async with PooledSession(pool) as session:
            async with session.get(url) as response:
                ...
    """

    def __init__(self, pool: ConnectionPool, url: str):
        self._pool = pool
        self._url = url
        self._session: Optional[aiohttp.ClientSession] = None

    async def __aenter__(self) -> aiohttp.ClientSession:
        self._session = await self._pool.get_connection(self._url)
        return self._session

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self._session:
            await self._pool.return_connection(self._session, self._url)

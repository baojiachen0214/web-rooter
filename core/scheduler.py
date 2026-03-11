"""
Scheduler - 请求调度器

功能：
- 优先级队列管理
- URL 指纹去重
- 快照和恢复
- 并发控制
"""
import asyncio
import pickle
import hashlib
import json
from pathlib import Path
from typing import Optional, Dict, Any, List, Set, Tuple
from dataclasses import dataclass, field
from datetime import datetime
import logging
from collections import defaultdict

from .request import Request
from .response import Response

logger = logging.getLogger(__name__)


@dataclass
class SchedulerStats:
    """调度器统计信息"""
    pending: int = 0
    queued: int = 0
    visited: int = 0
    filtered: int = 0
    errors: int = 0

    def to_dict(self) -> Dict[str, int]:
        return {
            "pending": self.pending,
            "queued": self.queued,
            "visited": self.visited,
            "filtered": self.filtered,
            "errors": self.errors,
        }


class DupeFilter:
    """
    去重过滤器 - 基于 URL 指纹
    支持内存和持久化两种模式
    """

    def __init__(self, persist: bool = False, data_dir: Optional[str] = None):
        self.persist = persist
        self.data_dir = Path(data_dir) if data_dir else None
        self._fingerprints: Set[str] = set()
        self._domain_count: Dict[str, int] = defaultdict(int)

        if self.persist and self.data_dir:
            self._load_fingerprints()

    def _get_fingerprint_file(self) -> Path:
        """获取指纹文件路径"""
        if not self.data_dir:
            raise ValueError("Data directory not set")
        self.data_dir.mkdir(parents=True, exist_ok=True)
        return self.data_dir / "request_fingerprints.pkl"

    def _load_fingerprints(self):
        """加载指纹"""
        fingerprint_file = self._get_fingerprint_file()
        if fingerprint_file.exists():
            try:
                with open(fingerprint_file, "rb") as f:
                    data = pickle.load(f)
                self._fingerprints = data.get("fingerprints", set())
                self._domain_count = defaultdict(int, data.get("domain_count", {}))
                logger.info(f"Loaded {len(self._fingerprints)} fingerprints from {fingerprint_file}")
            except Exception as e:
                logger.warning(f"Failed to load fingerprints: {e}")

    def _save_fingerprints(self):
        """保存指纹"""
        if not self.data_dir:
            return

        fingerprint_file = self._get_fingerprint_file()
        try:
            with open(fingerprint_file, "wb") as f:
                pickle.dump({
                    "fingerprints": self._fingerprints,
                    "domain_count": dict(self._domain_count),
                }, f)
            logger.info(f"Saved {len(self._fingerprints)} fingerprints to {fingerprint_file}")
        except Exception as e:
            logger.error(f"Failed to save fingerprints: {e}")

    def request_seen(self, request: Request) -> bool:
        """
        检查请求是否已存在

        Args:
            request: Request 对象

        Returns:
            True 如果请求已存在（应被过滤）
        """
        if request.dont_filter:
            return False

        fingerprint = request.fingerprint
        if fingerprint in self._fingerprints:
            return True

        # 添加指纹
        self._fingerprints.add(fingerprint)

        # 更新域名计数
        from urllib.parse import urlparse
        domain = urlparse(request.url).netloc
        self._domain_count[domain] += 1

        # 定期保存
        if self.persist and len(self._fingerprints) % 1000 == 0:
            self._save_fingerprints()

        return False

    def get_domain_count(self, domain: str) -> int:
        """获取域名已请求数量"""
        return self._domain_count.get(domain, 0)

    def clear(self):
        """清空指纹"""
        self._fingerprints.clear()
        self._domain_count.clear()
        if self.persist and self.data_dir:
            self._save_fingerprints()

    def __len__(self) -> int:
        return len(self._fingerprints)


class PriorityQueues:
    """
    优先级队列 - 管理不同优先级的请求
    使用 asyncio.PriorityQueue 实现
    """

    def __init__(self, max_size: int = 0):
        self.max_size = max_size
        self._queues: Dict[int, asyncio.Queue] = defaultdict(asyncio.Queue)
        self._counter = 0  # 用于保持插入顺序

    async def put(self, request: Request) -> bool:
        """
        添加请求到队列

        Args:
            request: Request 对象

        Returns:
            True 如果成功添加
        """
        priority = request.priority

        # 检查最大大小
        if self.max_size > 0:
            total_size = sum(q.qsize() for q in self._queues.values())
            if total_size >= self.max_size:
                return False

        # 添加到对应优先级队列
        # 使用 counter 确保同优先级按 FIFO 顺序
        item = (priority, self._counter, request)
        self._counter += 1

        await self._queues[priority].put(item)
        return True

    async def get(self) -> Optional[Request]:
        """
        获取最高优先级的请求

        Returns:
            Request 对象或 None
        """
        # 找到非空的最低优先级队列（数字越小优先级越高）
        for priority in sorted(self._queues.keys()):
            queue = self._queues[priority]
            if not queue.empty():
                _, _, request = await queue.get()
                return request

        return None

    def get_nowait(self) -> Optional[Request]:
        """
        非阻塞获取请求

        Returns:
            Request 对象或 None
        """
        for priority in sorted(self._queues.keys()):
            queue = self._queues[priority]
            if not queue.empty():
                try:
                    _, _, request = queue.get_nowait()
                    return request
                except asyncio.QueueEmpty:
                    continue
        return None

    @property
    def size(self) -> int:
        """获取队列总大小"""
        return sum(q.qsize() for q in self._queues.values())

    def is_empty(self) -> bool:
        """队列是否为空"""
        return self.size == 0

    def clear(self):
        """清空所有队列"""
        self._queues.clear()

    def get_stats(self) -> Dict[str, int]:
        """获取各优先级队列统计"""
        return {
            f"priority_{p}": q.qsize()
            for p, q in self._queues.items()
            if q.qsize() > 0
        }


@dataclass
class SchedulerConfig:
    """调度器配置"""
    # 队列最大大小
    max_queue_size: int = 0  # 0 表示无限制

    # 域名请求限制
    max_requests_per_domain: int = 0  # 0 表示无限制

    # 延迟配置
    download_delay: float = 0.0  # 请求间隔（秒）
    randomize_delay: bool = True  # 随机化延迟
    delay_range: Tuple[float, float] = (0.5, 2.0)  # 随机延迟范围

    # 并发配置
    concurrent_requests: int = 16  # 并发请求数

    # 持久化配置
    persist: bool = True
    data_dir: Optional[str] = None
    snapshot_interval: int = 100  # 每 N 个请求保存一次快照

    # 优先级配置
    default_priority: int = 0
    priority_levels: int = 10  # 优先级级别数量


class Scheduler:
    """
    Scheduler - 请求调度器

    功能：
    - 优先级队列管理
    - URL 去重
    - 域名限流
    - 快照和恢复
    - 并发控制

    用法:
        scheduler = Scheduler()
        await scheduler.open()
        await scheduler.enqueue_request(Request("https://example.com"))

        async for request in scheduler:
            response = await fetch(request)
            await scheduler.handle_response(response, callback)

        await scheduler.close()
    """

    def __init__(self, config: Optional[SchedulerConfig] = None):
        self.config = config or SchedulerConfig()

        # 核心组件
        self._dupefilter = DupeFilter(
            persist=self.config.persist,
            data_dir=self.config.data_dir,
        )
        self._queues = PriorityQueues(max_size=self.config.max_queue_size)

        # 状态管理
        self._opened = False
        self._closed = False
        self._active_requests: Set[str] = set()  # 正在处理的请求指纹

        # 统计信息
        self._stats = SchedulerStats()

        # 域名计数
        self._domain_count: Dict[str, int] = defaultdict(int)

        # 信号量用于并发控制
        self._semaphore: Optional[asyncio.Semaphore] = None

        # 快照计数
        self._snapshot_count = 0

    async def open(self):
        """打开调度器"""
        if self._opened:
            return

        self._semaphore = asyncio.Semaphore(self.config.concurrent_requests)
        self._opened = True
        self._closed = False

        logger.info(f"Scheduler opened with {self.config.concurrent_requests} concurrent requests")

    async def close(self):
        """关闭调度器"""
        if self._closed:
            return

        self._closed = True
        self._opened = False

        # 保存最终快照
        if self.config.persist:
            await self._save_snapshot()

        logger.info("Scheduler closed")

    async def __aenter__(self) -> "Scheduler":
        await self.open()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()

    async def enqueue_request(
        self,
        request: Request,
        force: bool = False,
    ) -> bool:
        """
        添加请求到队列

        Args:
            request: Request 对象
            force: 强制添加（跳过过滤和限制）

        Returns:
            True 如果成功添加
        """
        if not force:
            # 检查去重
            if self._dupefilter.request_seen(request):
                self._stats.filtered += 1
                logger.debug(f"Filtered duplicate request: {request.url}")
                return False

            # 检查域名限制
            if self.config.max_requests_per_domain > 0:
                from urllib.parse import urlparse
                domain = urlparse(request.url).netloc
                if self._domain_count.get(domain, 0) >= self.config.max_requests_per_domain:
                    logger.debug(f"Domain limit reached for {domain}")
                    return False

        # 添加到队列
        success = await self._queues.put(request)
        if success:
            self._stats.queued += 1
            if not force:
                self._domain_count[request.url.split("/")[2]] += 1

            # 定期保存快照
            if self.config.persist and self._stats.queued % self.config.snapshot_interval == 0:
                await self._save_snapshot()

        return success

    async def enqueue_requests(
        self,
        requests: List[Request],
        force: bool = False,
    ) -> int:
        """
        批量添加请求

        Args:
            requests: Request 列表
            force: 强制添加

        Returns:
            成功添加的数量
        """
        count = 0
        for request in requests:
            if await self.enqueue_request(request, force):
                count += 1
        return count

    async def next_request(self) -> Optional[Request]:
        """
        获取下一个请求

        Returns:
            Request 对象或 None
        """
        if self._queues.is_empty():
            return None

        request = self._queues.get_nowait()
        if request:
            self._active_requests.add(request.fingerprint)
            self._stats.pending += 1
        return request

    async def handle_response(
        self,
        response: Response,
        callback: Optional[str] = None,
    ) -> List[Request]:
        """
        处理响应并返回新的请求

        Args:
            response: Response 对象
            callback: 回调函数名

        Returns:
            新生成的请求列表
        """
        # 移除活动请求
        if response.request:
            self._active_requests.discard(response.request.fingerprint)

        new_requests = []

        if response.success and callback:
            # 从响应中提取链接并创建新请求
            links = response.get_links(internal_only=True)
            for link in links:
                request = Request(
                    url=link["href"],
                    callback=callback,
                    priority=response.request.priority + 1 if response.request else 0,
                    meta={
                        "referer": response.url,
                        "depth": (response.request.meta.get("depth", 0) + 1) if response.request else 0,
                    },
                )

                if await self.enqueue_request(request):
                    new_requests.append(request)

        return new_requests

    def get_next_snapshot(self) -> Dict[str, Any]:
        """
        获取下一个快照数据

        Returns:
            快照数据字典
        """
        return {
            "queue_size": self._queues.size,
            "active_requests": len(self._active_requests),
            "stats": self._stats.to_dict(),
            "domain_count": dict(self._domain_count),
            "timestamp": datetime.now().isoformat(),
        }

    async def _save_snapshot(self):
        """保存快照"""
        if not self.config.data_dir:
            return

        data_dir = Path(self.config.data_dir)
        data_dir.mkdir(parents=True, exist_ok=True)

        snapshot_file = data_dir / f"scheduler_snapshot_{self._snapshot_count}.pkl"
        self._snapshot_count += 1

        try:
            # 序列化队列数据
            queue_data = []
            while not self._queues.is_empty():
                request = self._queues.get_nowait()
                if request:
                    queue_data.append(request.to_dict())

            # 重新填充队列
            for item in sorted(queue_data, key=lambda x: x.get("priority", 0)):
                request = Request.from_dict(item)
                await self._queues.put(request)

            # 保存快照
            snapshot = {
                "queue": queue_data,
                "stats": self._stats.to_dict(),
                "domain_count": dict(self._domain_count),
                "timestamp": datetime.now().isoformat(),
            }

            with open(snapshot_file, "wb") as f:
                pickle.dump(snapshot, f)

            logger.info(f"Saved scheduler snapshot to {snapshot_file}")

        except Exception as e:
            logger.error(f"Failed to save snapshot: {e}")

    async def load_snapshot(self, snapshot_file: str) -> bool:
        """
        加载快照

        Args:
            snapshot_file: 快照文件路径

        Returns:
            True 如果加载成功
        """
        try:
            with open(snapshot_file, "rb") as f:
                snapshot = pickle.load(f)

            # 恢复队列
            queue_data = snapshot.get("queue", [])
            for item in sorted(queue_data, key=lambda x: x.get("priority", 0)):
                request = Request.from_dict(item)
                await self.enqueue_request(request, force=True)

            # 恢复统计
            stats_data = snapshot.get("stats", {})
            self._stats.pending = stats_data.get("pending", 0)
            self._stats.queued = stats_data.get("queued", 0)
            self._stats.visited = stats_data.get("visited", 0)
            self._stats.filtered = stats_data.get("filtered", 0)
            self._stats.errors = stats_data.get("errors", 0)

            # 恢复域名计数
            domain_data = snapshot.get("domain_count", {})
            self._domain_count.update(domain_data)

            logger.info(f"Loaded snapshot from {snapshot_file} with {len(queue_data)} requests")
            return True

        except Exception as e:
            logger.error(f"Failed to load snapshot: {e}")
            return False

    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        return {
            **self._stats.to_dict(),
            "queue_size": self._queues.size,
            "active_requests": len(self._active_requests),
            "domains": len(self._domain_count),
            "dupefilter_size": len(self._dupefilter),
        }

    def has_pending_requests(self) -> bool:
        """是否还有待处理的请求"""
        return not self._queues.is_empty() or len(self._active_requests) > 0

    async def __aiter__(self):
        """异步迭代器"""
        while not self._closed:
            request = await self.next_request()
            if request:
                yield request
            else:
                # 队列空了，等待一段时间
                await asyncio.sleep(0.1)

    def __len__(self) -> int:
        """获取队列中的请求数量"""
        return self._queues.size


async def create_scheduler(
    concurrent_requests: int = 16,
    max_queue_size: int = 0,
    max_per_domain: int = 0,
    download_delay: float = 0.0,
    persist: bool = False,
    data_dir: Optional[str] = None,
) -> Scheduler:
    """
    便捷函数：创建并打开调度器

    Args:
        concurrent_requests: 并发请求数
        max_queue_size: 队列最大大小
        max_per_domain: 每域名最大请求数
        download_delay: 下载延迟
        persist: 是否持久化
        data_dir: 数据目录

    Returns:
        Scheduler 对象
    """
    config = SchedulerConfig(
        concurrent_requests=concurrent_requests,
        max_queue_size=max_queue_size,
        max_requests_per_domain=max_per_domain,
        download_delay=download_delay,
        persist=persist,
        data_dir=data_dir,
    )
    scheduler = Scheduler(config)
    await scheduler.open()
    return scheduler


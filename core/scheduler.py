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
import os
from pathlib import Path
from typing import Optional, Dict, Any, List, Set, Tuple
from dataclasses import dataclass
from datetime import datetime
import logging
from collections import defaultdict, deque

from .request import Request
from .response import Response

logger = logging.getLogger(__name__)

DEFAULT_SCHEDULER_MAX_QUEUE_SIZE = max(
    1,
    int(os.getenv("WEB_ROOTER_SCHEDULER_MAX_QUEUE_SIZE", "2048") or 2048),
)
DEFAULT_DUPEFILTER_MAX_ENTRIES = max(
    1,
    int(os.getenv("WEB_ROOTER_SCHEDULER_DUPEFILTER_MAX_ENTRIES", "120000") or 120000),
)
DEFAULT_SCHEDULER_MIN_QUEUE_SIZE = max(
    1,
    int(os.getenv("WEB_ROOTER_SCHEDULER_MIN_QUEUE_SIZE", "32") or 32),
)
DEFAULT_SCHEDULER_MIN_DUPEFILTER_ENTRIES = max(
    1,
    int(os.getenv("WEB_ROOTER_SCHEDULER_MIN_DUPEFILTER_ENTRIES", "4096") or 4096),
)


@dataclass
class SchedulerStats:
    """调度器统计信息"""
    pending: int = 0
    queued: int = 0
    visited: int = 0
    filtered: int = 0
    dropped_queue_full: int = 0
    pressure_adjustments: int = 0
    pressure_queue_trimmed: int = 0
    errors: int = 0

    def to_dict(self) -> Dict[str, int]:
        return {
            "pending": self.pending,
            "queued": self.queued,
            "visited": self.visited,
            "filtered": self.filtered,
            "dropped_queue_full": self.dropped_queue_full,
            "pressure_adjustments": self.pressure_adjustments,
            "pressure_queue_trimmed": self.pressure_queue_trimmed,
            "errors": self.errors,
        }


class DupeFilter:
    """
    去重过滤器 - 有界内存的 URL 指纹去重。

    设计原则：
    - 指纹集合严格受 max_entries 限制，防止长时间运行内存持续增长。
    - 存储压缩后的 64-bit 摘要，而不是完整 SHA256 字符串，降低内存占用。
    - 达到上限后逐出最旧指纹（近似 LRU 的 FIFO 窗口语义）。
    """

    _FINGERPRINT_MASK = (1 << 64) - 1

    def __init__(
        self,
        persist: bool = False,
        data_dir: Optional[str] = None,
        max_entries: int = DEFAULT_DUPEFILTER_MAX_ENTRIES,
        track_domain_count: bool = False,
    ):
        self.persist = persist
        self.data_dir = Path(data_dir) if data_dir else None
        self._max_entries = max(1, int(max_entries))
        self._track_domain_count = bool(track_domain_count)
        self._fingerprints: Set[int] = set()
        self._fingerprint_order = deque()
        self._domain_count: Dict[str, int] = defaultdict(int)
        self._total_checks = 0
        self._total_hits = 0
        self._evicted_fingerprints = 0

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
                loaded = data.get("fingerprints", [])
                loaded_count = 0
                for item in self._iter_loaded_fingerprints(loaded):
                    key = self._normalize_loaded_fingerprint(item)
                    if key is None:
                        continue
                    self._remember_fingerprint(key, track_eviction=False)
                    loaded_count += 1
                if self._track_domain_count:
                    self._domain_count = defaultdict(int, data.get("domain_count", {}))
                meta = data.get("meta", {}) if isinstance(data, dict) else {}
                self._evicted_fingerprints = int(meta.get("evicted_fingerprints", 0) or 0)
                logger.info(
                    "Loaded %s/%s fingerprints from %s",
                    len(self._fingerprints),
                    loaded_count,
                    fingerprint_file,
                )
            except Exception as e:
                logger.warning(f"Failed to load fingerprints: {e}")

    def _save_fingerprints(self):
        """保存指纹"""
        if not self.data_dir:
            return

        fingerprint_file = self._get_fingerprint_file()
        try:
            with open(fingerprint_file, "wb") as f:
                pickle.dump(
                    {
                        "fingerprints": list(self._fingerprint_order),
                        "domain_count": dict(self._domain_count) if self._track_domain_count else {},
                        "meta": {
                            "max_entries": self._max_entries,
                            "evicted_fingerprints": self._evicted_fingerprints,
                        },
                    },
                    f,
                )
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

        self._total_checks += 1
        fingerprint = self._compress_fingerprint(request.fingerprint)
        if fingerprint in self._fingerprints:
            self._total_hits += 1
            return True

        self._remember_fingerprint(fingerprint)

        # 更新域名计数
        if self._track_domain_count:
            from urllib.parse import urlparse

            domain = urlparse(request.url).netloc
            self._domain_count[domain] += 1

        # 定期保存
        if self.persist and self._total_checks % 1000 == 0:
            self._save_fingerprints()

        return False

    def get_domain_count(self, domain: str) -> int:
        """获取域名已请求数量"""
        if not self._track_domain_count:
            return 0
        return self._domain_count.get(domain, 0)

    def clear(self):
        """清空指纹"""
        self._fingerprints.clear()
        self._fingerprint_order.clear()
        if self._track_domain_count:
            self._domain_count.clear()
        self._total_checks = 0
        self._total_hits = 0
        self._evicted_fingerprints = 0
        if self.persist and self.data_dir:
            self._save_fingerprints()

    def get_stats(self) -> Dict[str, Any]:
        utilization = len(self._fingerprints) / max(1, self._max_entries)
        return {
            "size": len(self._fingerprints),
            "max_entries": self._max_entries,
            "utilization": round(utilization, 4),
            "checks": self._total_checks,
            "hits": self._total_hits,
            "hit_rate": round(self._total_hits / max(1, self._total_checks), 4),
            "evicted_fingerprints": self._evicted_fingerprints,
        }

    @property
    def max_entries(self) -> int:
        return self._max_entries

    def set_max_entries(self, max_entries: int) -> Dict[str, int]:
        normalized = max(1, int(max_entries))
        previous = self._max_entries
        previous_evicted = self._evicted_fingerprints
        self._max_entries = normalized
        self._evict_to_budget(track_eviction=True)
        trimmed = max(0, self._evicted_fingerprints - previous_evicted)
        return {
            "old_max_entries": previous,
            "new_max_entries": normalized,
            "size": len(self._fingerprints),
            "trimmed": trimmed,
        }

    def _remember_fingerprint(self, key: int, track_eviction: bool = True) -> None:
        if key in self._fingerprints:
            return
        self._fingerprints.add(key)
        self._fingerprint_order.append(key)
        self._evict_to_budget(track_eviction=track_eviction)

    def _evict_to_budget(self, track_eviction: bool = True) -> None:
        while len(self._fingerprints) > self._max_entries and self._fingerprint_order:
            oldest = self._fingerprint_order.popleft()
            if oldest in self._fingerprints:
                self._fingerprints.remove(oldest)
                if track_eviction:
                    self._evicted_fingerprints += 1

    def _compress_fingerprint(self, fingerprint: str) -> int:
        value = str(fingerprint or "")
        digest = hashlib.blake2b(value.encode("utf-8", errors="ignore"), digest_size=8).digest()
        return int.from_bytes(digest, byteorder="big", signed=False)

    def _normalize_loaded_fingerprint(self, value: Any) -> Optional[int]:
        if isinstance(value, int):
            return value & self._FINGERPRINT_MASK
        if isinstance(value, str):
            try:
                return int(value, 16) & self._FINGERPRINT_MASK
            except ValueError:
                return self._compress_fingerprint(value)
        return None

    def _iter_loaded_fingerprints(self, loaded: Any) -> List[Any]:
        if isinstance(loaded, dict):
            return list(loaded.keys())
        if isinstance(loaded, set):
            return list(loaded)
        if isinstance(loaded, list):
            return loaded
        if isinstance(loaded, tuple):
            return list(loaded)
        return []

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
        self._size = 0

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
        if self.max_size > 0 and self._size >= self.max_size:
            return False

        # 添加到对应优先级队列
        # 使用 counter 确保同优先级按 FIFO 顺序
        item = (priority, self._counter, request)
        self._counter += 1

        await self._queues[priority].put(item)
        self._size += 1
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
                self._size = max(0, self._size - 1)
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
                    self._size = max(0, self._size - 1)
                    return request
                except asyncio.QueueEmpty:
                    continue
        return None

    @property
    def size(self) -> int:
        """获取队列总大小"""
        return self._size

    def is_empty(self) -> bool:
        """队列是否为空"""
        return self.size == 0

    def clear(self):
        """清空所有队列"""
        self._queues.clear()
        self._size = 0

    def set_max_size(self, max_size: int, trim: bool = False) -> Dict[str, int]:
        """
        动态更新队列容量。

        Args:
            max_size: 新容量，<=0 表示无限制（兼容旧行为）
            trim: 容量下降时是否立即裁剪已排队请求
        """
        normalized = int(max_size)
        previous = self.max_size
        before_size = self._size
        self.max_size = normalized
        trimmed = 0

        if trim and self.max_size > 0 and self._size > self.max_size:
            trimmed = self._trim_to_size(self.max_size)

        return {
            "old_max_size": previous,
            "new_max_size": self.max_size,
            "before_size": before_size,
            "after_size": self._size,
            "trimmed": trimmed,
        }

    def _trim_to_size(self, keep_size: int) -> int:
        keep = max(0, int(keep_size))
        if self._size <= keep:
            return 0

        all_items = self._drain_all_items()
        if not all_items:
            self._size = 0
            return 0

        all_items.sort(key=lambda item: (int(item[0]), int(item[1])))
        kept_items = all_items[:keep]
        dropped = max(0, len(all_items) - len(kept_items))
        self._restore_items(kept_items)
        return dropped

    def _drain_all_items(self) -> List[Tuple[int, int, Request]]:
        drained: List[Tuple[int, int, Request]] = []
        for priority in sorted(self._queues.keys()):
            queue = self._queues[priority]
            while not queue.empty():
                try:
                    item = queue.get_nowait()
                except asyncio.QueueEmpty:
                    break
                drained.append(item)
        self._queues.clear()
        self._size = 0
        return drained

    def _restore_items(self, items: List[Tuple[int, int, Request]]) -> None:
        self._queues.clear()
        self._size = 0
        max_counter = self._counter
        for priority, order, request in items:
            self._queues[int(priority)].put_nowait((int(priority), int(order), request))
            self._size += 1
            if int(order) >= max_counter:
                max_counter = int(order) + 1
        self._counter = max_counter

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
    max_queue_size: int = DEFAULT_SCHEDULER_MAX_QUEUE_SIZE

    # 域名请求限制
    max_requests_per_domain: int = 0  # 0 表示无限制
    max_dupefilter_entries: int = DEFAULT_DUPEFILTER_MAX_ENTRIES

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
        self.config.max_queue_size = self._normalize_bounded_budget(
            self.config.max_queue_size,
            fallback=DEFAULT_SCHEDULER_MAX_QUEUE_SIZE,
            name="max_queue_size",
        )
        self.config.max_dupefilter_entries = self._normalize_bounded_budget(
            self.config.max_dupefilter_entries,
            fallback=DEFAULT_DUPEFILTER_MAX_ENTRIES,
            name="max_dupefilter_entries",
        )
        self._base_max_queue_size = self.config.max_queue_size
        self._base_max_dupefilter_entries = self.config.max_dupefilter_entries

        # 核心组件
        self._dupefilter = DupeFilter(
            persist=self.config.persist,
            data_dir=self.config.data_dir,
            max_entries=self.config.max_dupefilter_entries,
            track_domain_count=self.config.max_requests_per_domain > 0,
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
        self._track_domain_counts = self.config.max_requests_per_domain > 0

        # 信号量用于并发控制
        self._semaphore: Optional[asyncio.Semaphore] = None

        # 快照计数
        self._snapshot_count = 0
        self._pressure_level = "normal"

    @staticmethod
    def _normalize_bounded_budget(value: Any, *, fallback: int, name: str) -> int:
        try:
            normalized = int(value)
        except Exception:
            normalized = int(fallback)
        if normalized <= 0:
            logger.warning(
                "Scheduler %s was non-positive (%s), fallback to bounded default=%s",
                name,
                value,
                fallback,
            )
            return int(fallback)
        return normalized

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
            if not force and self._track_domain_counts:
                from urllib.parse import urlparse

                domain = urlparse(request.url).netloc
                if domain:
                    self._domain_count[domain] += 1
        else:
            self._stats.dropped_queue_full += 1

        # 定期保存快照
        if (
            success
            and self.config.persist
            and self._stats.queued % self.config.snapshot_interval == 0
        ):
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

    def apply_pressure_profile(
        self,
        pressure_level: Optional[str],
        pressure_limits: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        根据运行时压力动态调节队列与去重预算。

        该方法是无阻塞的，可在主循环中周期性调用。
        """
        normalized_level = self._normalize_pressure_level(pressure_level)
        ratio_by_level = {
            "normal": 1.0,
            "elevated": 0.85,
            "high": 0.65,
            "critical": 0.45,
        }
        ratio = ratio_by_level.get(normalized_level, 1.0)
        limits = pressure_limits if isinstance(pressure_limits, dict) else {}

        queue_floor = max(
            1,
            min(
                DEFAULT_SCHEDULER_MIN_QUEUE_SIZE,
                max(1, self._base_max_queue_size // 4),
            ),
        )
        dupe_floor = max(
            1,
            min(
                DEFAULT_SCHEDULER_MIN_DUPEFILTER_ENTRIES,
                max(1, self._base_max_dupefilter_entries // 4),
            ),
        )
        target_queue = max(
            queue_floor,
            int(self._base_max_queue_size * ratio),
        )
        target_dupe = max(
            dupe_floor,
            int(self._base_max_dupefilter_entries * ratio),
        )

        links_limit = self._safe_int(limits.get("links_max"), default=0)
        if links_limit > 0:
            target_queue = min(target_queue, max(queue_floor, links_limit * 16))

        queue_update = self._queues.set_max_size(target_queue, trim=True)
        dupe_update = self._dupefilter.set_max_entries(target_dupe)

        changed = (
            queue_update["old_max_size"] != queue_update["new_max_size"]
            or dupe_update["old_max_entries"] != dupe_update["new_max_entries"]
            or normalized_level != self._pressure_level
        )
        trimmed_requests = queue_update.get("trimmed", 0)
        if changed:
            self._stats.pressure_adjustments += 1
        if trimmed_requests > 0:
            self._stats.pressure_queue_trimmed += int(trimmed_requests)
        self._pressure_level = normalized_level

        return {
            "level": normalized_level,
            "changed": changed,
            "trimmed_requests": int(trimmed_requests),
            "queue": queue_update,
            "dupefilter": dupe_update,
            "limits": {
                "queue_max_size": queue_update["new_max_size"],
                "dupefilter_max_entries": dupe_update["new_max_entries"],
            },
        }

    def _normalize_pressure_level(self, level: Optional[str]) -> str:
        normalized = str(level or "").strip().lower()
        if normalized in {"elevated", "high", "critical"}:
            return normalized
        return "normal"

    def _safe_int(self, value: Any, default: int = 0) -> int:
        try:
            return int(value)
        except Exception:
            return int(default)

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
            "dupefilter": self._dupefilter.get_stats(),
            "pressure_level": self._pressure_level,
            "base_queue_max_size": self._base_max_queue_size,
            "base_dupefilter_max_entries": self._base_max_dupefilter_entries,
            "queue_max_size": self._queues.max_size,
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
                "queue_max_size": self._queues.max_size,
                "dupefilter_max_entries": self._dupefilter.max_entries,
                "pressure_level": self._pressure_level,
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
            self._stats.dropped_queue_full = stats_data.get("dropped_queue_full", 0)
            self._stats.pressure_adjustments = stats_data.get("pressure_adjustments", 0)
            self._stats.pressure_queue_trimmed = stats_data.get("pressure_queue_trimmed", 0)
            self._stats.errors = stats_data.get("errors", 0)

            # 恢复域名计数
            domain_data = snapshot.get("domain_count", {})
            if self._track_domain_counts:
                self._domain_count.update(domain_data)
            self._pressure_level = self._normalize_pressure_level(snapshot.get("pressure_level"))
            restored_queue_max = self._safe_int(snapshot.get("queue_max_size"), default=self._queues.max_size)
            restored_dupe_max = self._safe_int(
                snapshot.get("dupefilter_max_entries"),
                default=self._dupefilter.max_entries,
            )
            self._queues.set_max_size(restored_queue_max, trim=True)
            self._dupefilter.set_max_entries(restored_dupe_max)

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
            "queue_max_size": self._queues.max_size,
            "base_queue_max_size": self._base_max_queue_size,
            "active_requests": len(self._active_requests),
            "domains": len(self._domain_count),
            "pressure_level": self._pressure_level,
            "dupefilter_size": len(self._dupefilter),
            "base_dupefilter_max_entries": self._base_max_dupefilter_entries,
            "dupefilter": self._dupefilter.get_stats(),
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
    max_queue_size: Optional[int] = None,
    max_per_domain: int = 0,
    max_dupefilter_entries: Optional[int] = None,
    download_delay: float = 0.0,
    persist: bool = False,
    data_dir: Optional[str] = None,
) -> Scheduler:
    """
    便捷函数：创建并打开调度器

    Args:
        concurrent_requests: 并发请求数
        max_queue_size: 队列最大大小，None 时使用默认有界预算
        max_per_domain: 每域名最大请求数
        max_dupefilter_entries: 去重指纹最大容量，None 时使用默认有界预算
        download_delay: 下载延迟
        persist: 是否持久化
        data_dir: 数据目录

    Returns:
        Scheduler 对象
    """
    config = SchedulerConfig(
        concurrent_requests=concurrent_requests,
        max_queue_size=DEFAULT_SCHEDULER_MAX_QUEUE_SIZE if max_queue_size is None else max_queue_size,
        max_requests_per_domain=max_per_domain,
        max_dupefilter_entries=(
            DEFAULT_DUPEFILTER_MAX_ENTRIES
            if max_dupefilter_entries is None
            else max_dupefilter_entries
        ),
        download_delay=download_delay,
        persist=persist,
        data_dir=data_dir,
    )
    scheduler = Scheduler(config)
    await scheduler.open()
    return scheduler

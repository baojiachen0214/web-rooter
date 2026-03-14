"""
结果队列 - 支持流式输出的异步队列

功能:
- 使用 asyncio.Queue 存储爬取结果
- 支持背压控制 (backpressure)
- 支持超时和取消
- 支持多个消费者同时读取
"""
import asyncio
from typing import Any, Optional, AsyncGenerator, Set
from dataclasses import dataclass, field
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


@dataclass
class StreamItem:
    """
    流式输出项

    Attributes:
        data: 实际数据
        item_type: 项类型 ('item', 'request', 'error', 'complete')
        timestamp: 时间戳
        metadata: 额外元数据
    """
    data: Any
    item_type: str = "item"
    timestamp: datetime = field(default_factory=datetime.now)
    metadata: dict = field(default_factory=dict)

    @property
    def is_item(self) -> bool:
        return self.item_type == "item"

    @property
    def is_request(self) -> bool:
        return self.item_type == "request"

    @property
    def is_error(self) -> bool:
        return self.item_type == "error"

    @property
    def is_complete(self) -> bool:
        return self.item_type == "complete"


class ResultQueue:
    """
    结果队列 - 用于流式输出的异步队列

    功能:
    - 异步 put/get
    - 背压控制 (通过 maxsize)
    - 支持多个消费者
    - 支持优雅关闭

    用法:
        queue = ResultQueue(maxsize=100)

        # 生产者
        await queue.put(item)

        # 消费者
        async for item in queue:
            print(item)
    """

    def __init__(self, maxsize: int = 100, overflow_strategy: str = "block"):
        """
        初始化结果队列

        Args:
            maxsize: 队列最大大小 (用于背压控制), 0 表示无限制
            overflow_strategy: 队列满时策略，支持 block/drop_oldest/drop_new
        """
        self._queue: asyncio.Queue = asyncio.Queue(maxsize=maxsize)
        self._closed = False
        self._consumers: Set[asyncio.Task] = set()
        self._items_put = 0
        self._items_got = 0
        self._items_dropped = 0
        self._maxsize = maxsize
        normalized_strategy = str(overflow_strategy or "block").strip().lower()
        if normalized_strategy not in {"block", "drop_oldest", "drop_new"}:
            normalized_strategy = "block"
        self._overflow_strategy = normalized_strategy

    async def put(
        self,
        item: Any,
        item_type: str = "item",
        timeout: Optional[float] = None,
    ) -> bool:
        """
        放入结果项

        Args:
            item: 数据项
            item_type: 项类型
            timeout: 超时 (秒), None 表示无限等待

        Returns:
            True 表示成功，False 表示超时或队列已关闭
        """
        if self._closed:
            logger.warning("Cannot put to closed queue")
            return False

        stream_item = StreamItem(data=item, item_type=item_type)

        try:
            if not self._prepare_put():
                return False
            if timeout is not None:
                await asyncio.wait_for(
                    self._queue.put(stream_item),
                    timeout=timeout
                )
            else:
                await self._queue.put(stream_item)

            self._items_put += 1
            return True

        except asyncio.TimeoutError:
            logger.warning(f"Timeout putting item to queue (size: {self._queue.qsize()})")
            return False
        except asyncio.QueueShutDown:
            logger.warning("Queue shutdown, cannot put items")
            return False

    async def get(
        self,
        timeout: Optional[float] = None,
    ) -> Optional[StreamItem]:
        """
        获取结果项

        Args:
            timeout: 超时 (秒), None 表示无限等待

        Returns:
            StreamItem 或 None (超时或队列关闭)
        """
        try:
            if timeout is not None:
                item = await asyncio.wait_for(
                    self._queue.get(),
                    timeout=timeout
                )
            else:
                item = await self._queue.get()

            self._items_got += 1
            self._queue.task_done()
            return item

        except asyncio.TimeoutError:
            return None
        except asyncio.QueueShutDown:
            return None

    async def get_nowait(self) -> Optional[StreamItem]:
        """非阻塞获取"""
        try:
            item = self._queue.get_nowait()
            self._items_got += 1
            self._queue.task_done()
            return item
        except asyncio.QueueEmpty:
            return None

    def put_nowait(
        self,
        item: Any,
        item_type: str = "item",
    ) -> bool:
        """非阻塞放入"""
        if self._closed:
            return False

        try:
            stream_item = StreamItem(data=item, item_type=item_type)
            if not self._prepare_put():
                return False
            self._queue.put_nowait(stream_item)
            self._items_put += 1
            return True
        except asyncio.QueueFull:
            return False

    async def join(self):
        """等待所有项处理完成"""
        await self._queue.join()

    def close(self):
        """关闭队列 (不再接受新项)"""
        self._closed = True
        logger.info(f"Queue closed. Put: {self._items_put}, Got: {self._items_got}")

    def mark_complete(self):
        """标记所有数据已完成 (发送结束信号)"""
        self.close()

    async def __aiter__(self) -> AsyncGenerator[StreamItem, None]:
        """异步迭代器"""
        while not self._closed or not self._queue.empty():
            item = await self.get(timeout=0.1)
            if item is not None:
                yield item
            elif self._closed and self._queue.empty():
                break

    def is_full(self) -> bool:
        """队列是否已满"""
        if self._maxsize == 0:
            return False
        return self._queue.qsize() >= self._maxsize

    def is_empty(self) -> bool:
        """队列是否为空"""
        return self._queue.empty()

    def qsize(self) -> int:
        """当前队列大小"""
        return self._queue.qsize()

    @property
    def maxsize(self) -> int:
        """最大队列大小"""
        return self._maxsize

    @property
    def closed(self) -> bool:
        """是否已关闭"""
        return self._closed

    def _prepare_put(self) -> bool:
        if self._maxsize <= 0 or not self._queue.full():
            return True

        if self._overflow_strategy == "drop_new":
            self._items_dropped += 1
            return False

        if self._overflow_strategy == "drop_oldest":
            try:
                self._queue.get_nowait()
                self._queue.task_done()
                self._items_dropped += 1
            except asyncio.QueueEmpty:
                return True
        return True

    def get_stats(self) -> dict:
        """获取统计信息"""
        return {
            "items_put": self._items_put,
            "items_got": self._items_got,
            "items_dropped": self._items_dropped,
            "current_size": self._queue.qsize(),
            "maxsize": self._maxsize,
            "is_full": self.is_full(),
            "is_empty": self.is_empty(),
            "closed": self._closed,
            "overflow_strategy": self._overflow_strategy,
        }


class StreamConsumer:
    """
    流式消费者 - 管理多个消费者协程

    用法:
        consumer = StreamConsumer(queue)

        # 添加多个消费者
        consumer.add_consumer(process_item, name="worker-1")
        consumer.add_consumer(process_item, name="worker-2")

        # 等待所有消费者完成
        await consumer.wait()
    """

    def __init__(self, queue: ResultQueue):
        self._queue = queue
        self._tasks: Set[asyncio.Task] = set()
        self._running = False

    def add_consumer(
        self,
        callback,
        name: str = "consumer",
    ):
        """
        添加消费者协程

        Args:
            callback: 异步回调函数 async def callback(item)
            name: 消费者名称
        """
        async def wrapper():
            try:
                async for item in self._queue:
                    try:
                        if callable(callback):
                            if asyncio.iscoroutinefunction(callback):
                                await callback(item)
                            else:
                                callback(item)
                    except Exception as e:
                        logger.exception(f"Consumer {name} error processing item: {e}")
            except asyncio.CancelledError:
                logger.info(f"Consumer {name} cancelled")
                raise

        task = asyncio.create_task(wrapper())
        task.set_name(name)
        self._tasks.add(task)
        self._running = True
        return task

    async def wait(self):
        """等待所有消费者完成"""
        if not self._tasks:
            return

        self._running = False
        await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()

    def cancel(self):
        """取消所有消费者"""
        for task in self._tasks:
            task.cancel()
        self._running = False

    @property
    def is_running(self) -> bool:
        return self._running

    def get_stats(self) -> dict:
        return {
            "consumer_count": len(self._tasks),
            "is_running": self._running,
        }

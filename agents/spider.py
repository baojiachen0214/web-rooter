"""
Spider - 爬虫基类
灵感来自 Scrapy 和 Scrapling 的 Spider 类

功能：
- 抽象基类定义爬虫的基本结构和接口
- 配置属性：name, start_urls, allowed_domains
- 并发控制
- 日志配置
"""
import asyncio
import signal
from abc import ABC, abstractmethod
from typing import Optional, List, Dict, Any, Set, AsyncGenerator
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
import logging

from core.request import Request, make_request
from core.response import Response
from core.scheduler import (
    DEFAULT_DUPEFILTER_MAX_ENTRIES,
    DEFAULT_SCHEDULER_MAX_QUEUE_SIZE,
    Scheduler,
    SchedulerConfig,
)
from core.checkpoint import CheckpointManager
from core.session_manager import SessionManager, SessionType
from core.crawler import Crawler
from core.runtime_pressure import RuntimePressureController
from core.result_queue import ResultQueue, StreamItem

logger = logging.getLogger(__name__)


@dataclass
class SpiderConfig:
    """爬虫配置"""
    # 基本信息
    name: str = "spider"
    allowed_domains: List[str] = field(default_factory=list)
    start_urls: List[str] = field(default_factory=list)

    # 并发控制
    concurrent_requests: int = 16
    download_delay: float = 0.0
    randomize_delay: bool = True
    delay_range: tuple = (0.5, 2.0)

    # 域限制
    max_requests_per_domain: int = 0  # 0 表示无限制

    # 队列配置
    max_queue_size: int = DEFAULT_SCHEDULER_MAX_QUEUE_SIZE
    max_dupefilter_entries: int = DEFAULT_DUPEFILTER_MAX_ENTRIES
    adaptive_budget_enabled: bool = True
    pressure_check_interval: int = 25

    # 重试配置
    max_retries: int = 3

    # 持久化配置
    persist: bool = True
    checkpoint_dir: Optional[str] = None
    auto_checkpoint: bool = True
    checkpoint_interval: int = 100  # 每 N 个请求保存一次

    # Session 配置
    use_sessions: bool = False
    session_type: SessionType = SessionType.HTTP

    # 其他配置
    custom_settings: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SpiderStats:
    """爬虫统计"""
    start_time: datetime = field(default_factory=datetime.now)
    end_time: Optional[datetime] = None

    requests_scheduled: int = 0
    requests_downloaded: int = 0
    requests_succeeded: int = 0
    requests_failed: int = 0
    requests_filtered: int = 0
    items_scraped: int = 0

    bytes_downloaded: int = 0

    errors: Dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        duration = (self.end_time or datetime.now()) - self.start_time
        return {
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "duration_seconds": duration.total_seconds(),
            "requests_scheduled": self.requests_scheduled,
            "requests_downloaded": self.requests_downloaded,
            "requests_succeeded": self.requests_succeeded,
            "requests_failed": self.requests_failed,
            "requests_filtered": self.requests_filtered,
            "items_scraped": self.items_scraped,
            "bytes_downloaded": self.bytes_downloaded,
            "success_rate": self.requests_succeeded / max(1, self.requests_downloaded),
            "errors": dict(self.errors),
        }


class Spider(ABC):
    """
    Spider - 爬虫抽象基类

    用法:
        class MySpider(Spider):
            name = "myspider"
            start_urls = ["https://example.com"]

            async def parse(self, response):
                # 提取数据
                data = extract_data(response)
                yield data

                # 跟随链接
                for link in response.get_links():
                    yield response.follow(link["href"], callback="parse")

        # 运行爬虫
        spider = MySpider()
        await spider.run()
    """

    # 类级别的配置
    name: str = "spider"
    allowed_domains: List[str] = []
    start_urls: List[str] = []
    custom_settings: Dict[str, Any] = {}

    def __init__(self, config: Optional[SpiderConfig] = None):
        """
        初始化 Spider

        Args:
            config: 爬虫配置
        """
        # 合并配置
        self.config = config or SpiderConfig(
            name=self.name,
            allowed_domains=self.allowed_domains,
            start_urls=self.start_urls,
            custom_settings=self.custom_settings,
        )

        # 合并自定义设置
        if self.custom_settings:
            for key, value in self.custom_settings.items():
                setattr(self.config, key, value)

        # 核心组件
        self._scheduler: Optional[Scheduler] = None
        self._crawler: Optional[Crawler] = None
        self._session_manager: Optional[SessionManager] = None
        self._checkpoint_manager: Optional[CheckpointManager] = None

        # 状态管理
        self._running = False
        self._paused = False
        self._shutdown_requested = False

        # 统计信息
        self._stats = SpiderStats()

        # 任务管理
        self._tasks: Set[asyncio.Task] = set()
        self._active_requests: Dict[str, asyncio.Task] = {}
        self._pressure = RuntimePressureController()
        self._last_pressure_snapshot: Dict[str, Any] = self._pressure.snapshot()
        self._last_pressure_check_downloaded: int = -1

        # 流式输出
        self._result_queue: Optional[ResultQueue] = None
        self._stream_mode = False

        # 信号处理
        self._setup_signal_handlers()

        # 日志配置
        self._setup_logging()

    def _setup_logging(self):
        """配置日志"""
        self.logger = logging.getLogger(f"spider.{self.name}")

    def _setup_signal_handlers(self):
        """设置信号处理器"""
        def signal_handler(signum, frame):
            self.logger.info(f"收到信号 {signum}，请求关闭...")
            self._shutdown_requested = True

        try:
            signal.signal(signal.SIGINT, signal_handler)
            signal.signal(signal.SIGTERM, signal_handler)
        except ValueError:
            # 非主线程
            pass

    async def _init_components(self):
        """初始化组件"""
        queue_size = int(self.config.max_queue_size or 0)
        if queue_size <= 0:
            queue_size = DEFAULT_SCHEDULER_MAX_QUEUE_SIZE
            self.logger.warning(
                "Spider max_queue_size was non-positive, fallback to bounded default=%s",
                queue_size,
            )

        dupefilter_size = int(self.config.max_dupefilter_entries or 0)
        if dupefilter_size <= 0:
            dupefilter_size = DEFAULT_DUPEFILTER_MAX_ENTRIES
            self.logger.warning(
                "Spider max_dupefilter_entries was non-positive, fallback to bounded default=%s",
                dupefilter_size,
            )

        # 初始化调度器
        scheduler_config = SchedulerConfig(
            concurrent_requests=self.config.concurrent_requests,
            max_queue_size=queue_size,
            max_requests_per_domain=self.config.max_requests_per_domain,
            max_dupefilter_entries=dupefilter_size,
            download_delay=self.config.download_delay,
            randomize_delay=self.config.randomize_delay,
            delay_range=self.config.delay_range,
            persist=self.config.persist,
            data_dir=self.config.checkpoint_dir,
            snapshot_interval=self.config.checkpoint_interval,
        )
        self._scheduler = Scheduler(scheduler_config)
        await self._scheduler.open()

        # 初始化爬虫
        self._crawler = Crawler()

        # 初始化会话管理器（如果需要）
        if self.config.use_sessions:
            self._session_manager = SessionManager()
            await self._session_manager.start()

        # 初始化检查点管理器（如果需要）
        if self.config.persist and self.config.checkpoint_dir:
            self._checkpoint_manager = CheckpointManager(
                spider_name=self.name,
                checkpoint_dir=self.config.checkpoint_dir,
                auto_save_interval=60,
            )
            self._checkpoint_manager.register_signal_handler()

    async def _close_components(self):
        """关闭组件"""
        # 取消所有任务
        for task in self._tasks:
            task.cancel()

        # 等待任务完成
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)

        # 关闭组件
        if self._scheduler:
            await self._scheduler.close()

        if self._crawler:
            await self._crawler.close()

        if self._session_manager:
            await self._session_manager.stop()

        self.logger.info("所有组件已关闭")

    async def open(self):
        """打开爬虫（初始化）"""
        await self._init_components()
        self._running = True
        self.logger.info(f"Spider '{self.name}' opened")

    async def close(self):
        """关闭爬虫"""
        await self._close_components()
        self._running = False
        self._stats.end_time = datetime.now()
        self.logger.info(f"Spider '{self.name}' closed")

    async def __aenter__(self) -> "Spider":
        await self.open()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()

    @abstractmethod
    async def parse(self, response: Response) -> AsyncGenerator[Any, None]:
        """
        抽象方法：解析响应

        子类必须实现此方法来处理响应

        Args:
            response: Response 对象

        Yields:
            Item 数据或 Request 对象
        """
        pass

    async def start_requests(self) -> AsyncGenerator[Request, None]:
        """
        生成初始请求

        可以被子类重写以自定义初始请求

        Yields:
            Request 对象
        """
        for url in self.start_urls:
            yield make_request(url, callback="parse")

    def _is_allowed_domain(self, url: str) -> bool:
        """检查 URL 是否在允许的域中"""
        if not self.allowed_domains:
            return True

        from urllib.parse import urlparse
        parsed = urlparse(url)
        netloc = parsed.netloc.lower()

        # 移除端口
        if ":" in netloc:
            netloc = netloc.split(":")[0]

        for domain in self.allowed_domains:
            if netloc == domain.lower() or netloc.endswith("." + domain.lower()):
                return True

        return False

    async def _process_response(
        self,
        response: Response,
        request: Request,
    ) -> AsyncGenerator[Any, None]:
        """
        处理响应

        Args:
            response: Response 对象
            request: 对应的 Request
        """
        self._stats.requests_downloaded += 1

        if response.success:
            self._stats.requests_succeeded += 1
            self._stats.bytes_downloaded += len(response.text)

            # 调用回调方法
            callback_name = request.callback
            callback = getattr(self, callback_name, self.parse)

            if callback:
                async for item in callback(response):
                    if isinstance(item, Request):
                        # 新请求
                        await self._scheduler.enqueue_request(item)
                        self._stats.requests_scheduled += 1
                    elif item is not None:
                        # 数据项
                        self._stats.items_scraped += 1
                        # 发射到流式队列
                        await self._emit_item(item, item_type="item")
                        yield item
        else:
            self._stats.requests_failed += 1

            # 重试逻辑
            if request.retry_times < request.max_retries:
                retry_request = request.replace(
                    retry_times=request.retry_times + 1,
                    priority=request.priority + 1,
                )
                await self._scheduler.enqueue_request(retry_request)
                self.logger.warning(
                    f"重试请求 ({request.retry_times + 1}/{request.max_retries}): {request.url}"
                )
            else:
                self.logger.error(f"请求失败：{request.url}")
                error_key = f"status_{response.status}"
                self._stats.errors[error_key] = self._stats.errors.get(error_key, 0) + 1
                # 发射错误到流式队列
                await self._emit_item(
                    {"error": f"Request failed: {request.url}", "status": response.status},
                    item_type="error",
                )

    async def _fetch_request(self, request: Request) -> Optional[Response]:
        """
        获取请求

        Args:
            request: Request 对象

        Returns:
            Response 对象或 None
        """
        try:
            # 检查域限制
            if not self._is_allowed_domain(request.url):
                self._stats.requests_filtered += 1
                self.logger.debug(f"过滤不允许的域：{request.url}")
                return None

            # 获取会话（如果使用）
            session = None
            if self._session_manager and self.config.use_sessions:
                session = await self._session_manager.get_session(request)

            # 执行请求 - Crawler 返回 CrawlResult
            crawl_result = await self._crawler.fetch(
                request.url,
                headers=request.headers or None,
                method=request.method,
            )

            # 转换为 Response 对象
            from core.response import create_response
            response = create_response(
                url=crawl_result.url or request.url,
                body=crawl_result.html.encode() if crawl_result.html else b"",
                status=crawl_result.status_code or 200,
                elapsed=int(crawl_result.response_time * 1000) if crawl_result.response_time else 0,
            )

            # 设置请求引用
            response.request = request

            # 更新会话状态
            if session:
                await session.use(success=crawl_result.success, bytes_transferred=len(crawl_result.html) if crawl_result.html else 0)

            return response

        except Exception as e:
            self.logger.exception(f"获取请求失败 {request.url}: {e}")
            self._stats.errors[type(e).__name__] = self._stats.errors.get(type(e).__name__, 0) + 1
            return None

    def _record_request_outcome(self, success: bool) -> None:
        try:
            self._pressure.record_outcome(success=bool(success))
        except Exception:
            pass

    def _should_check_pressure(self, force: bool = False) -> bool:
        if force:
            return True
        if not self.config.adaptive_budget_enabled:
            return False
        interval = max(1, int(self.config.pressure_check_interval or 25))
        downloaded = int(self._stats.requests_downloaded or 0)
        if downloaded <= 0:
            return False
        if downloaded == self._last_pressure_check_downloaded:
            return False
        return downloaded % interval == 0

    def _apply_runtime_pressure_budget(self, force: bool = False) -> None:
        if self._scheduler is None:
            return
        if not self._should_check_pressure(force=force):
            return
        try:
            snapshot = self._pressure.evaluate()
            self._last_pressure_snapshot = snapshot
            self._last_pressure_check_downloaded = int(self._stats.requests_downloaded or 0)
            level = snapshot.get("level")
            limits = snapshot.get("limits", {}) if isinstance(snapshot, dict) else {}
            adjustment = self._scheduler.apply_pressure_profile(level, limits)
            if adjustment.get("changed") or adjustment.get("trimmed_requests", 0) > 0:
                self.logger.info(
                    "Adaptive scheduler budget: level=%s queue=%s dupe=%s trimmed=%s",
                    adjustment.get("level"),
                    adjustment.get("limits", {}).get("queue_max_size"),
                    adjustment.get("limits", {}).get("dupefilter_max_entries"),
                    adjustment.get("trimmed_requests"),
                )
        except Exception as exc:
            self.logger.debug("Adaptive scheduler budget update failed: %s", exc)

    async def _worker(self, worker_id: int):
        """
        工作协程

        Args:
            worker_id: 工作器 ID
        """
        self.logger.debug(f"Worker {worker_id} started")

        while self._running and not self._shutdown_requested:
            if self._paused:
                await asyncio.sleep(0.1)
                continue

            # 获取下一个请求
            request = await self._scheduler.next_request()

            if not request:
                # 队列为空，等待
                await asyncio.sleep(0.1)
                continue

            # 创建任务
            task = asyncio.create_task(self._fetch_and_process(request))
            self._tasks.add(task)
            task.add_done_callback(self._tasks.discard)

            # 应用延迟
            if self.config.download_delay > 0:
                delay = self.config.download_delay
                if self.config.randomize_delay:
                    import random
                    delay = random.uniform(*self.config.delay_range)
                await asyncio.sleep(delay)

        self.logger.debug(f"Worker {worker_id} stopped")

    async def _fetch_and_process(self, request: Request):
        """获取并处理请求"""
        try:
            response = await self._fetch_request(request)
            if response:
                self._record_request_outcome(response.success)
                async for item in self._process_response(response, request):
                    pass  # 处理 yield 的数据
            else:
                self._record_request_outcome(False)
            self._apply_runtime_pressure_budget(force=False)
        except Exception as e:
            self.logger.exception(f"处理请求失败 {request.url}: {e}")
            self._record_request_outcome(False)

    async def run(
        self,
        start_urls: Optional[List[str]] = None,
        resume: bool = True,
    ) -> SpiderStats:
        """
        运行爬虫

        Args:
            start_urls: 起始 URL 列表
            resume: 是否从检查点恢复

        Returns:
            SpiderStats 统计信息
        """
        await self.open()

        # 恢复检查点
        if resume and self._checkpoint_manager and self._checkpoint_manager.has_checkpoint():
            checkpoint = self._checkpoint_manager.load_checkpoint()
            if checkpoint:
                self.logger.info(f"从检查点恢复：{checkpoint.timestamp}")
                # TODO: 恢复调度器状态

        # 添加起始 URL
        urls = start_urls or self.start_urls
        for url in urls:
            request = make_request(url, callback="parse")
            await self._scheduler.enqueue_request(request)
            self._stats.requests_scheduled += 1

        self.logger.info(f"启动 {self.config.concurrent_requests} 个工作器")

        # 启动工作器
        workers = [
            asyncio.create_task(self._worker(i))
            for i in range(self.config.concurrent_requests)
        ]
        self._apply_runtime_pressure_budget(force=True)

        # 等待队列完成
        try:
            while self._scheduler.has_pending_requests() and not self._shutdown_requested:
                await asyncio.sleep(0.1)
                self._apply_runtime_pressure_budget(force=False)

                # 定期保存检查点
                if self._checkpoint_manager and self.config.auto_checkpoint:
                    if self._stats.requests_downloaded % self.config.checkpoint_interval == 0:
                        self._save_checkpoint()

        except KeyboardInterrupt:
            self.logger.info("用户中断")
            self._shutdown_requested = True

        finally:
            # 取消工作器
            for worker in workers:
                worker.cancel()

            # 等待工作器完成
            await asyncio.gather(*workers, return_exceptions=True)

            # 保存最终检查点
            if self._checkpoint_manager:
                self._save_checkpoint()

        await self.close()

        self.logger.info(f"爬虫完成：{self._stats.to_dict()}")

        # 发射完成信号到流式队列
        if self._stream_mode and self._result_queue:
            await self._emit_item(
                {"stats": self._stats.to_dict()},
                item_type="complete",
            )

        return self._stats

    def _save_checkpoint(self):
        """保存检查点"""
        if not self._checkpoint_manager:
            return

        try:
            scheduler_state = self._scheduler.get_next_snapshot()
            spider_state = {
                "name": self.name,
                "config": self.config.__dict__,
            }

            self._checkpoint_manager.save_checkpoint(
                scheduler_state=scheduler_state,
                spider_state=spider_state,
                stats=self._stats.to_dict(),
            )

            self.logger.debug("检查点已保存")

        except Exception as e:
            self.logger.error(f"保存检查点失败：{e}")

    def pause(self):
        """暂停爬虫"""
        self._paused = True
        self.logger.info("爬虫已暂停")

    def resume(self):
        """恢复爬虫"""
        self._paused = False
        self.logger.info("爬虫已恢复")

    def stop(self):
        """停止爬虫"""
        self._shutdown_requested = True
        self.logger.info("爬虫停止请求")

    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        payload = self._stats.to_dict()
        payload["runtime_pressure"] = self._last_pressure_snapshot
        if self._scheduler:
            scheduler_stats = self._scheduler.get_stats()
            payload["scheduler_budget"] = {
                "queue_size": scheduler_stats.get("queue_size"),
                "queue_max_size": scheduler_stats.get("queue_max_size"),
                "dupefilter_size": scheduler_stats.get("dupefilter_size"),
                "dupefilter_max_entries": (
                    (scheduler_stats.get("dupefilter") or {}).get("max_entries")
                    if isinstance(scheduler_stats.get("dupefilter"), dict)
                    else None
                ),
                "pressure_level": scheduler_stats.get("pressure_level"),
                "dropped_queue_full": scheduler_stats.get("dropped_queue_full"),
                "pressure_queue_trimmed": scheduler_stats.get("pressure_queue_trimmed"),
            }
        return payload

    def log_stats(self):
        """记录统计信息"""
        stats = self._stats.to_dict()
        self.logger.info(f"统计信息：{stats}")

    # ==================== 流式输出 API ====================

    def stream(
        self,
        max_queue_size: int = 100,
        timeout: Optional[float] = None,
    ) -> "SpiderStream":
        """
        创建流式输出上下文

        Args:
            max_queue_size: 结果队列最大大小 (用于背压控制)
            timeout: 超时时间 (秒)

        Returns:
            SpiderStream 上下文管理器

        用法:
            async with spider.stream() as stream:
                async for item in stream:
                    print(f"实时结果：{item}")
        """
        return SpiderStream(
            spider=self,
            max_queue_size=max_queue_size,
            timeout=timeout,
        )

    async def _emit_item(self, item: Any, item_type: str = "item"):
        """
        发射结果项到流式队列

        Args:
            item: 数据项
            item_type: 项类型
        """
        if self._result_queue and self._stream_mode:
            await self._result_queue.put(item, item_type=item_type)

    async def _start_stream_mode(self, max_queue_size: int = 100):
        """启动流式模式"""
        self._stream_mode = True
        self._result_queue = ResultQueue(maxsize=max_queue_size)
        self.logger.info(f"Stream mode started with queue size {max_queue_size}")

    async def _stop_stream_mode(self):
        """停止流式模式"""
        self._stream_mode = False
        if self._result_queue:
            self._result_queue.mark_complete()
            self._result_queue = None
        self.logger.info("Stream mode stopped")


# 便捷函数
async def run_spider(
    spider: Spider,
    start_urls: Optional[List[str]] = None,
    resume: bool = True,
) -> SpiderStats:
    """
    便捷函数：运行爬虫

    Args:
        spider: Spider 实例
        start_urls: 起始 URL
        resume: 是否恢复

    Returns:
        SpiderStats 统计信息
    """
    return await spider.run(start_urls=start_urls, resume=resume)


def create_spider_class(
    name: str,
    start_urls: List[str],
    allowed_domains: Optional[List[str]] = None,
    parse_callback: Optional[callable] = None,
    **settings,
) -> type:
    """
    便捷函数：动态创建 Spider 类

    Args:
        name: 爬虫名称
        start_urls: 起始 URL
        allowed_domains: 允许的域
        parse_callback: 解析回调函数
        **settings: 其他设置

    Returns:
        Spider 子类
    """
    attrs = {
        "name": name,
        "start_urls": start_urls,
        "allowed_domains": allowed_domains or [],
    }

    if parse_callback:
        attrs["parse"] = parse_callback

    attrs.update(settings)

    return type(f"{name.capitalize()}Spider", (Spider,), attrs)


class SpiderStream:
    """
    Spider 流式输出上下文管理器

    用法:
        async with spider.stream() as stream:
            async for item in stream:
                print(f"实时结果：{item}")

        # 或者带超时
        async with spider.stream(timeout=60) as stream:
            async for item in stream:
                if item.is_error:
                    logger.error(f"错误：{item.data}")
                else:
                    yield item.data
    """

    def __init__(
        self,
        spider: Spider,
        max_queue_size: int = 100,
        timeout: Optional[float] = None,
    ):
        self.spider = spider
        self.max_queue_size = max_queue_size
        self.timeout = timeout
        self._stream_task: Optional[asyncio.Task] = None

    async def __aenter__(self) -> "SpiderStream":
        """进入流式模式"""
        await self.spider._start_stream_mode(self.max_queue_size)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """退出流式模式"""
        await self.spider._stop_stream_mode()
        if self._stream_task:
            self._stream_task.cancel()
            try:
                await self._stream_task
            except asyncio.CancelledError:
                pass

    def __aiter__(self) -> AsyncGenerator[StreamItem, None]:
        """异步迭代器"""
        return self._iterate()

    async def _iterate(self) -> AsyncGenerator[StreamItem, None]:
        """迭代结果队列"""
        if not self.spider._result_queue:
            return

        queue = self.spider._result_queue

        while self.spider._stream_mode or not queue.is_empty():
            try:
                item = await queue.get(timeout=0.1)
                if item:
                    yield item
                    if item.is_complete:
                        break
            except asyncio.TimeoutError:
                if not self.spider._running:
                    break
                continue
            except asyncio.QueueShutDown:
                break

        # 确保队列已关闭
        if queue.closed:
            return

    async def run(self, start_urls: Optional[List[str]] = None) -> SpiderStats:
        """
        运行爬虫并流式输出结果

        Args:
            start_urls: 起始 URL 列表

        Returns:
            SpiderStats 统计信息
        """
        # 启动爬虫任务
        self._stream_task = asyncio.create_task(
            self.spider.run(start_urls=start_urls)
        )

        # 等待爬虫完成
        try:
            stats = await self._stream_task
        except asyncio.CancelledError:
            self.spider.stop()
            stats = self.spider.get_stats()

        return stats

    def get_queue_stats(self) -> dict:
        """获取队列统计信息"""
        if self.spider._result_queue:
            return self.spider._result_queue.get_stats()
        return {}

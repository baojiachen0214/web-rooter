"""
Checkpoint Manager - 检查点管理器

功能：
- 定期保存爬虫状态
- 支持 Ctrl+C 优雅退出
- 断点续爬
- pickle 序列化
"""
import asyncio
import pickle
import signal
import os
from pathlib import Path
from typing import Optional, Dict, Any, List, Callable
from dataclasses import dataclass, field
from datetime import datetime
import logging
import threading
import time

logger = logging.getLogger(__name__)


@dataclass
class CheckpointData:
    """检查点数据"""
    spider_name: str
    timestamp: datetime
    scheduler_state: Dict[str, Any]
    spider_state: Dict[str, Any]
    stats: Dict[str, Any]
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "spider_name": self.spider_name,
            "timestamp": self.timestamp.isoformat(),
            "scheduler_state": self.scheduler_state,
            "spider_state": self.spider_state,
            "stats": self.stats,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CheckpointData":
        return cls(
            spider_name=data.get("spider_name", ""),
            timestamp=datetime.fromisoformat(data.get("timestamp", datetime.now().isoformat())),
            scheduler_state=data.get("scheduler_state", {}),
            spider_state=data.get("spider_state", {}),
            stats=data.get("stats", {}),
            metadata=data.get("metadata", {}),
        )


class CheckpointManager:
    """
    CheckpointManager - 检查点管理器

    功能：
    - 定期保存爬虫状态
    - 支持 Ctrl+C 优雅退出
    - 断点续爬
    - 多检查点轮换

    用法:
        checkpoint_mgr = CheckpointManager("my_spider", "./checkpoints")

        # 注册信号处理
        checkpoint_mgr.register_signal_handler()

        # 开始爬取前检查是否有检查点
        if checkpoint_mgr.has_checkpoint():
            checkpoint = checkpoint_mgr.load_checkpoint()
            # 恢复状态...

        # 定期保存
        await checkpoint_mgr.save_checkpoint(scheduler, spider, stats)
    """

    def __init__(
        self,
        spider_name: str,
        checkpoint_dir: Optional[str] = None,
        max_checkpoints: int = 5,
        auto_save_interval: int = 60,  # 秒
    ):
        """
        初始化检查点管理器

        Args:
            spider_name: 爬虫名称
            checkpoint_dir: 检查点目录
            max_checkpoints: 最大检查点数量
            auto_save_interval: 自动保存间隔（秒）
        """
        self.spider_name = spider_name
        self.checkpoint_dir = Path(checkpoint_dir) if checkpoint_dir else Path("./checkpoints")
        self.max_checkpoints = max_checkpoints
        self.auto_save_interval = auto_save_interval

        # 确保目录存在
        self.checkpoint_dir.mkdir(parents=True, exist_ok=True)

        # 状态管理
        self._checkpoint_count = 0
        self._last_save_time: Optional[datetime] = None
        self._running = False
        self._auto_save_task: Optional[asyncio.Task] = None

        # 信号处理
        self._shutdown_requested = False
        self._shutdown_event: Optional[asyncio.Event] = None  # Lazy init

        # 回调函数
        self._save_callbacks: List[Callable] = []
        self._restore_callbacks: List[Callable] = []

        # 线程锁
        self._lock = threading.Lock()

    def _get_checkpoint_file(self, index: Optional[int] = None) -> Path:
        """获取检查点文件路径"""
        if index is not None:
            return self.checkpoint_dir / f"checkpoint_{self.spider_name}_{index:04d}.pkl"

        # 获取最新的检查点文件
        checkpoints = self.list_checkpoints()
        if checkpoints:
            return checkpoints[-1]

        return self.checkpoint_dir / f"checkpoint_{self.spider_name}_latest.pkl"

    def list_checkpoints(self) -> List[Path]:
        """列出所有检查点文件"""
        pattern = f"checkpoint_{self.spider_name}_*.pkl"
        checkpoints = list(self.checkpoint_dir.glob(pattern))
        return sorted(checkpoints)

    def has_checkpoint(self) -> bool:
        """检查是否有检查点"""
        return len(self.list_checkpoints()) > 0

    def get_latest_checkpoint(self) -> Optional[Path]:
        """获取最新的检查点文件"""
        checkpoints = self.list_checkpoints()
        return checkpoints[-1] if checkpoints else None

    def register_signal_handler(self):
        """注册信号处理器（用于 Ctrl+C 优雅退出）"""
        def signal_handler(signum, frame):
            logger.info(f"收到信号 {signum}，请求关闭...")
            self._shutdown_requested = True
            self._shutdown_event.set()

        # 注册 SIGINT (Ctrl+C) 和 SIGTERM
        try:
            signal.signal(signal.SIGINT, signal_handler)
            signal.signal(signal.SIGTERM, signal_handler)
            logger.info("信号处理器已注册")
        except ValueError:
            # 在非主线程中无法注册信号处理
            logger.warning("无法在主线程中注册信号处理器")

    def register_save_callback(self, callback: Callable):
        """
        注册保存回调

        Args:
            callback: 回调函数，接收 CheckpointData 参数
        """
        self._save_callbacks.append(callback)

    def register_restore_callback(self, callback: Callable):
        """
        注册恢复回调

        Args:
            callback: 回调函数，接收 CheckpointData 参数
        """
        self._restore_callbacks.append(callback)

    async def start_auto_save(self):
        """启动自动保存"""
        if self._running:
            return

        self._running = True
        self._auto_save_task = asyncio.create_task(self._auto_save_loop())
        logger.info(f"自动保存已启动，间隔 {self.auto_save_interval} 秒")

    async def stop_auto_save(self):
        """停止自动保存"""
        self._running = False
        if self._auto_save_task:
            self._auto_save_task.cancel()
            try:
                await self._auto_save_task
            except asyncio.CancelledError:
                pass
        logger.info("自动保存已停止")

    async def _auto_save_loop(self):
        """自动保存循环"""
        while self._running:
            try:
                await asyncio.sleep(self.auto_save_interval)
                # 自动保存会在外部调用 save_checkpoint
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"自动保存循环错误：{e}")

    def create_checkpoint_data(
        self,
        scheduler_state: Dict[str, Any],
        spider_state: Dict[str, Any],
        stats: Dict[str, Any],
        metadata: Optional[Dict[str, Any]] = None,
    ) -> CheckpointData:
        """创建检查点数据"""
        return CheckpointData(
            spider_name=self.spider_name,
            timestamp=datetime.now(),
            scheduler_state=scheduler_state,
            spider_state=spider_state,
            stats=stats,
            metadata=metadata or {},
        )

    def save_checkpoint_data(self, checkpoint: CheckpointData) -> bool:
        """
        保存检查点数据

        Args:
            checkpoint: CheckpointData 对象

        Returns:
            True 如果保存成功
        """
        try:
            with self._lock:
                # 获取下一个索引
                checkpoint_file = self._get_checkpoint_file(self._checkpoint_count)
                self._checkpoint_count += 1

                # 序列化并保存
                with open(checkpoint_file, "wb") as f:
                    pickle.dump(checkpoint.to_dict(), f, protocol=pickle.HIGHEST_PROTOCOL)

                # 更新 latest 链接
                latest_file = self.checkpoint_dir / f"checkpoint_{self.spider_name}_latest.pkl"
                with open(latest_file, "wb") as f:
                    pickle.dump(checkpoint.to_dict(), f, protocol=pickle.HIGHEST_PROTOCOL)

                self._last_save_time = datetime.now()

                # 清理旧检查点
                self._cleanup_old_checkpoints()

                logger.info(f"检查点已保存到 {checkpoint_file}")

                # 调用回调
                for callback in self._save_callbacks:
                    try:
                        callback(checkpoint)
                    except Exception as e:
                        logger.warning(f"保存回调错误：{e}")

                return True

        except Exception as e:
            logger.error(f"保存检查点失败：{e}")
            return False

    def save_checkpoint(
        self,
        scheduler_state: Dict[str, Any],
        spider_state: Dict[str, Any],
        stats: Dict[str, Any],
        metadata: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """
        保存检查点

        Args:
            scheduler_state: 调度器状态
            spider_state: 爬虫状态
            stats: 统计信息
            metadata: 额外元数据

        Returns:
            True 如果保存成功
        """
        checkpoint = self.create_checkpoint_data(
            scheduler_state, spider_state, stats, metadata
        )
        return self.save_checkpoint_data(checkpoint)

    def load_checkpoint(self, checkpoint_file: Optional[str] = None) -> Optional[CheckpointData]:
        """
        加载检查点

        Args:
            checkpoint_file: 检查点文件路径，None 则加载最新的

        Returns:
            CheckpointData 对象或 None
        """
        try:
            if checkpoint_file:
                file_path = Path(checkpoint_file)
            else:
                file_path = self.get_latest_checkpoint()

            if not file_path or not file_path.exists():
                logger.warning("没有可用的检查点")
                return None

            with open(file_path, "rb") as f:
                data = pickle.load(f)

            checkpoint = CheckpointData.from_dict(data)

            logger.info(f"检查点已加载：{file_path}")
            logger.info(f"  - 爬虫：{checkpoint.spider_name}")
            logger.info(f"  - 时间：{checkpoint.timestamp}")
            logger.info(f"  - 队列大小：{checkpoint.scheduler_state.get('queue_size', 0)}")

            # 调用恢复回调
            for callback in self._restore_callbacks:
                try:
                    callback(checkpoint)
                except Exception as e:
                    logger.warning(f"恢复回调错误：{e}")

            return checkpoint

        except Exception as e:
            logger.error(f"加载检查点失败：{e}")
            return None

    def _cleanup_old_checkpoints(self):
        """清理旧检查点"""
        checkpoints = self.list_checkpoints()

        if len(checkpoints) > self.max_checkpoints:
            # 保留最新的 max_checkpoints 个
            to_delete = checkpoints[:-self.max_checkpoints]

            for file_path in to_delete:
                try:
                    file_path.unlink()
                    logger.debug(f"删除旧检查点：{file_path}")
                except Exception as e:
                    logger.warning(f"删除检查点失败 {file_path}: {e}")

    def delete_checkpoint(self, checkpoint_file: str) -> bool:
        """删除指定检查点"""
        try:
            file_path = Path(checkpoint_file)
            if file_path.exists():
                file_path.unlink()
                logger.info(f"检查点已删除：{file_path}")
                return True
            return False
        except Exception as e:
            logger.error(f"删除检查点失败：{e}")
            return False

    def clear_checkpoints(self) -> int:
        """清空所有检查点"""
        checkpoints = self.list_checkpoints()
        count = 0

        for file_path in checkpoints:
            try:
                file_path.unlink()
                count += 1
            except Exception as e:
                logger.warning(f"删除检查点失败 {file_path}: {e}")

        logger.info(f"清空了 {count} 个检查点")
        return count

    def get_checkpoint_info(self, checkpoint_file: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """获取检查点信息"""
        try:
            if checkpoint_file:
                file_path = Path(checkpoint_file)
            else:
                file_path = self.get_latest_checkpoint()

            if not file_path or not file_path.exists():
                return None

            with open(file_path, "rb") as f:
                data = pickle.load(f)

            return {
                "file": str(file_path),
                "size": file_path.stat().st_size,
                "spider_name": data.get("spider_name", ""),
                "timestamp": data.get("timestamp", ""),
                "stats": data.get("stats", {}),
            }

        except Exception as e:
            logger.error(f"获取检查点信息失败：{e}")
            return None

    @property
    def shutdown_requested(self) -> bool:
        """是否请求关闭"""
        return self._shutdown_requested

    def _get_shutdown_event(self) -> asyncio.Event:
        """懒加载获取 shutdown event"""
        if self._shutdown_event is None:
            self._shutdown_event = asyncio.Event()
        return self._shutdown_event

    async def wait_for_shutdown(self, timeout: Optional[float] = None):
        """等待关闭请求"""
        try:
            await asyncio.wait_for(self._get_shutdown_event().wait(), timeout=timeout)
        except asyncio.TimeoutError:
            pass
        except asyncio.CancelledError:
            pass

    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        checkpoints = self.list_checkpoints()
        return {
            "checkpoint_count": len(checkpoints),
            "max_checkpoints": self.max_checkpoints,
            "last_save_time": self._last_save_time.isoformat() if self._last_save_time else None,
            "auto_save_interval": self.auto_save_interval,
            "checkpoint_dir": str(self.checkpoint_dir),
            "total_size_bytes": sum(f.stat().st_size for f in checkpoints),
        }


def save_checkpoint_sync(
    checkpoint_mgr: CheckpointManager,
    scheduler_state: Dict[str, Any],
    spider_state: Dict[str, Any],
    stats: Dict[str, Any],
    metadata: Optional[Dict[str, Any]] = None,
) -> bool:
    """
    同步保存检查点（用于信号处理器）

    Args:
        checkpoint_mgr: CheckpointManager 对象
        scheduler_state: 调度器状态
        spider_state: 爬虫状态
        stats: 统计信息
        metadata: 额外元数据

    Returns:
        True 如果保存成功
    """
    return checkpoint_mgr.save_checkpoint(
        scheduler_state, spider_state, stats, metadata
    )


"""
内存优化和缓存清理模块

功能:
- 自动清理搜索过程中的临时缓存
- 只保留最终结果
- 内存使用监控
- 定期垃圾回收
"""
import asyncio
import gc
import logging
import os
from typing import Optional, Set, Dict, Any
from datetime import datetime

logger = logging.getLogger(__name__)

try:
    import psutil
except ModuleNotFoundError:  # pragma: no cover - optional runtime dependency
    psutil = None  # type: ignore[assignment]


class MemoryOptimizer:
    """
    内存优化器

    功能:
    - 跟踪临时缓存
    - 自动清理中间结果
    - 内存使用监控
    - 垃圾回收触发
    """

    def __init__(self, auto_cleanup: bool = True, memory_threshold_mb: int = 500):
        """
        初始化内存优化器

        Args:
            auto_cleanup: 是否自动清理
            memory_threshold_mb: 内存阈值 (MB), 超过时触发清理
        """
        self.auto_cleanup = auto_cleanup
        self.memory_threshold_mb = memory_threshold_mb
        self._tracked_caches: Set[str] = set()
        self._temp_results: Dict[str, Any] = {}
        self._cleanup_count = 0
        self._last_cleanup_time: Optional[datetime] = None

    def register_cache(self, cache_id: str):
        """注册需要跟踪的缓存"""
        self._tracked_caches.add(cache_id)
        logger.debug(f"Registered cache: {cache_id}")

    def unregister_cache(self, cache_id: str):
        """注销缓存"""
        self._tracked_caches.discard(cache_id)
        logger.debug(f"Unregistered cache: {cache_id}")

    def store_temp_result(self, key: str, value: Any, ttl_seconds: int = 300):
        """
        存储临时结果

        Args:
            key: 结果键
            value: 结果值
            ttl_seconds: 生存时间 (秒)
        """
        self._temp_results[key] = {
            "value": value,
            "created_at": datetime.now(),
            "ttl": ttl_seconds
        }
        logger.debug(f"Stored temp result: {key}")

    def get_temp_result(self, key: str) -> Optional[Any]:
        """获取临时结果"""
        if key in self._temp_results:
            item = self._temp_results[key]
            # 检查是否过期
            age = (datetime.now() - item["created_at"]).total_seconds()
            if age < item["ttl"]:
                return item["value"]
            else:
                # 过期删除
                del self._temp_results[key]
        return None

    def clear_temp_results(self, keep_keys: Optional[Set[str]] = None):
        """
        清理临时结果

        Args:
            keep_keys: 要保留的键
        """
        if keep_keys:
            to_delete = [k for k in self._temp_results.keys() if k not in keep_keys]
            for key in to_delete:
                del self._temp_results[key]
            logger.info(f"Cleared {len(to_delete)} temp results, kept {len(keep_keys)}")
        else:
            count = len(self._temp_results)
            self._temp_results.clear()
            logger.info(f"Cleared all {count} temp results")

    def check_memory_usage(self) -> Dict[str, Any]:
        """检查当前内存使用情况"""
        if psutil is None:
            return {
                "rss_mb": 0.0,
                "vms_mb": 0.0,
                "percent": 0.0,
                "tracked_caches": len(self._tracked_caches),
                "temp_results": len(self._temp_results),
                "psutil_available": False,
            }

        process = psutil.Process(os.getpid())
        memory_info = process.memory_info()

        return {
            "rss_mb": memory_info.rss / 1024 / 1024,  #  Resident Set Size
            "vms_mb": memory_info.vms / 1024 / 1024,  # Virtual Memory Size
            "percent": process.memory_percent(),
            "tracked_caches": len(self._tracked_caches),
            "temp_results": len(self._temp_results),
            "psutil_available": True,
        }

    def should_cleanup(self) -> bool:
        """是否应该触发清理"""
        memory_usage = self.check_memory_usage()
        return memory_usage["rss_mb"] > self.memory_threshold_mb

    async def cleanup(self, force: bool = False):
        """
        执行清理

        Args:
            force: 是否强制清理
        """
        if not self.auto_cleanup and not force:
            return

        if not self.should_cleanup() and not force:
            return

        logger.info(f"Starting memory cleanup...")

        # 清理过期的临时结果
        now = datetime.now()
        expired_keys = []
        for key, item in self._temp_results.items():
            age = (now - item["created_at"]).total_seconds()
            if age > item["ttl"]:
                expired_keys.append(key)

        for key in expired_keys:
            del self._temp_results[key]

        # 触发垃圾回收
        gc.collect()

        self._cleanup_count += 1
        self._last_cleanup_time = now

        memory_usage = self.check_memory_usage()
        logger.info(
            f"Memory cleanup completed. "
            f"Cleared {len(expired_keys)} expired results. "
            f"Current memory: {memory_usage['rss_mb']:.1f}MB ({memory_usage['percent']:.1f}%)"
        )

    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        return {
            "cleanup_count": self._cleanup_count,
            "last_cleanup": self._last_cleanup_time.isoformat() if self._last_cleanup_time else None,
            "tracked_caches": len(self._tracked_caches),
            "temp_results": len(self._temp_results),
            "memory_usage": self.check_memory_usage(),
        }


class SearchSessionCleaner:
    """
    搜索会话清理器

    用于在搜索完成后清理中间缓存和临时结果
    """

    def __init__(self, memory_optimizer: Optional[MemoryOptimizer] = None):
        self.memory_optimizer = memory_optimizer or MemoryOptimizer()
        self._session_cache_keys: Set[str] = set()
        self._final_result_keys: Set[str] = set()

    def mark_as_final(self, key: str):
        """标记为最终结果（不删除）"""
        self._final_result_keys.add(key)
        logger.debug(f"Marked as final: {key}")

    def add_session_cache(self, key: str):
        """添加会话缓存键"""
        self._session_cache_keys.add(key)
        self.memory_optimizer.register_cache(key)

    async def cleanup_session(self, keep_final: bool = True):
        """
        清理搜索会话

        Args:
            keep_final: 是否保留最终结果
        """
        # 清理临时缓存
        if keep_final:
            to_clean = self._session_cache_keys - self._final_result_keys
        else:
            to_clean = self._session_cache_keys

        logger.info(f"Cleaning up {len(to_clean)} session caches...")

        for key in to_clean:
            self.memory_optimizer.unregister_cache(key)

        self._session_cache_keys.clear()

        # 清理临时结果
        if keep_final:
            self.memory_optimizer.clear_temp_results(keep_keys=self._final_result_keys)
        else:
            self.memory_optimizer.clear_temp_results()
            self._final_result_keys.clear()

        # 触发内存清理
        await self.memory_optimizer.cleanup()

    def get_session_stats(self) -> Dict[str, Any]:
        """获取会话统计"""
        return {
            "session_caches": len(self._session_cache_keys),
            "final_results": len(self._final_result_keys),
            "memory_optimizer": self.memory_optimizer.get_stats(),
        }


# 全局单例
_global_optimizer: Optional[MemoryOptimizer] = None
_session_cleaner: Optional[SearchSessionCleaner] = None


def get_memory_optimizer() -> MemoryOptimizer:
    """获取全局内存优化器"""
    global _global_optimizer
    if _global_optimizer is None:
        _global_optimizer = MemoryOptimizer()
    return _global_optimizer


def get_session_cleaner() -> SearchSessionCleaner:
    """获取全局会话清理器"""
    global _session_cleaner
    if _session_cleaner is None:
        _session_cleaner = SearchSessionCleaner()
    return _session_cleaner


async def cleanup_search_session(keep_final_results: bool = True):
    """
    清理搜索会话

    Args:
        keep_final_results: 是否保留最终结果
    """
    cleaner = get_session_cleaner()
    await cleaner.cleanup_session(keep_final=keep_final_results)
    logger.info("Search session cleanup completed")


def mark_result_as_final(cache_key: str):
    """标记结果为最终结果（不删除）"""
    cleaner = get_session_cleaner()
    cleaner.mark_as_final(cache_key)


async def check_and_cleanup_memory():
    """检查内存并清理"""
    optimizer = get_memory_optimizer()
    if optimizer.should_cleanup():
        await optimizer.cleanup(force=True)

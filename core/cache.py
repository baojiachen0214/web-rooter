"""
请求缓存系统 - 避免重复请求相同 URL

功能:
- 缓存已请求的 URL 响应
- 支持 TTL 过期
- 支持内存和 SQLite 存储
- 支持缓存命中率统计

"""
import asyncio
import hashlib
import json
import os
import time
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta
from pathlib import Path
import logging
import sqlite3

logger = logging.getLogger(__name__)


def _resolve_default_sqlite_cache_path() -> str:
    """Resolve a writable sqlite cache path with safe fallbacks."""
    env_path = str(os.getenv("WEB_ROOTER_CACHE_DB_PATH", "")).strip()
    if env_path:
        return str(Path(env_path).expanduser())

    candidates = [
        Path.cwd() / ".web-rooter" / "cache.db",
        Path.home() / ".web-rooter" / "cache.db",
        Path("/tmp") / "web-rooter-cache.db",
    ]
    for candidate in candidates:
        try:
            candidate.parent.mkdir(parents=True, exist_ok=True)
            return str(candidate)
        except Exception:
            continue

    # Last resort: keep a relative path so runtime can still proceed.
    return "cache.db"


@dataclass
class CacheEntry:
    """
    缓存条目

    Attributes:
        url: 请求 URL
        response_body: 响应体
        status_code: 状态码
        headers: 响应头
        created_at: 创建时间
        expires_at: 过期时间
        hit_count: 命中次数
    """
    url: str
    response_body: bytes
    status_code: int
    headers: Dict[str, str]
    created_at: float = field(default_factory=time.time)
    expires_at: Optional[float] = None
    hit_count: int = 0

    def is_expired(self) -> bool:
        """检查是否过期"""
        if self.expires_at is None:
            return False
        return time.time() > self.expires_at

    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            "url": self.url,
            "response_body": self.response_body.hex(),
            "status_code": self.status_code,
            "headers": json.dumps(self.headers),
            "created_at": self.created_at,
            "expires_at": self.expires_at,
            "hit_count": self.hit_count,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "CacheEntry":
        """从字典创建"""
        return cls(
            url=data["url"],
            response_body=bytes.fromhex(data["response_body"]),
            status_code=data["status_code"],
            headers=json.loads(data["headers"]),
            created_at=data.get("created_at", time.time()),
            expires_at=data.get("expires_at"),
            hit_count=data.get("hit_count", 0),
        )


class MemoryCache:
    """
    内存缓存 - 使用 LRU 策略

    功能:
    - 快速访问
    - LRU 淘汰
    - TTL 支持
    """

    def __init__(self, max_size: int = 1000, max_bytes: int = 64 * 1024 * 1024):
        """
        初始化内存缓存

        Args:
            max_size: 最大缓存条目数
        """
        self._cache: Dict[str, CacheEntry] = {}
        self._access_order: List[str] = []
        self._max_size = max_size
        self._max_bytes = max_bytes
        self._current_bytes = 0
        self._hits = 0
        self._misses = 0
        self._lock = asyncio.Lock()

    async def get(self, key: str) -> Optional[CacheEntry]:
        """获取缓存"""
        async with self._lock:
            entry = self._cache.get(key)
            if entry is None:
                self._misses += 1
                return None

            if entry.is_expired():
                self._remove_entry(key)
                self._misses += 1
                return None

            # 更新访问顺序 (LRU)
            if key in self._access_order:
                self._access_order.remove(key)
            self._access_order.append(key)

            entry.hit_count += 1
            self._hits += 1
            return entry

    async def set(
        self,
        key: str,
        entry: CacheEntry,
    ):
        """设置缓存"""
        async with self._lock:
            # 如果已存在，先删除
            if key in self._cache:
                self._remove_entry(key)

            entry_size = len(entry.response_body or b"")
            if entry_size > self._max_bytes:
                return

            # 检查是否需要淘汰
            while self._cache and (
                len(self._cache) >= self._max_size
                or self._current_bytes + entry_size > self._max_bytes
            ):
                # 淘汰最久未访问的
                oldest_key = self._access_order.pop(0)
                self._remove_entry(oldest_key)

            self._cache[key] = entry
            self._access_order.append(key)
            self._current_bytes += entry_size

    async def delete(self, key: str):
        """删除缓存"""
        async with self._lock:
            self._remove_entry(key)

    async def clear(self):
        """清空缓存"""
        async with self._lock:
            self._cache.clear()
            self._access_order.clear()
            self._current_bytes = 0

    def _remove_entry(self, key: str) -> None:
        entry = self._cache.pop(key, None)
        if key in self._access_order:
            self._access_order.remove(key)
        if entry is not None:
            self._current_bytes = max(0, self._current_bytes - len(entry.response_body or b""))

    def get_stats(self) -> dict:
        """获取统计信息"""
        total = self._hits + self._misses
        hit_rate = self._hits / total if total > 0 else 0
        return {
            "size": len(self._cache),
            "max_size": self._max_size,
            "current_bytes": self._current_bytes,
            "max_bytes": self._max_bytes,
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": hit_rate,
        }


class SQLiteCache:
    """
    SQLite 缓存 - 持久化存储

    功能:
    - 跨会话缓存
    - 大容量存储
    - TTL 自动清理
    """

    def __init__(self, db_path: str, max_size: int = 10000):
        """
        初始化 SQLite 缓存

        Args:
            db_path: 数据库路径
            max_size: 最大缓存条目数
        """
        self._db_path = db_path
        self._max_size = max_size
        self._conn: Optional[sqlite3.Connection] = None
        self._lock = asyncio.Lock()
        self._hits = 0
        self._misses = 0
        self._connect_error: Optional[str] = None

    def _connect(self):
        """连接数据库"""
        if self._conn is None:
            db_file = Path(self._db_path).expanduser()
            db_file.parent.mkdir(parents=True, exist_ok=True)
            self._conn = sqlite3.connect(str(db_file), check_same_thread=False)
            self._create_table()
            self._cleanup_expired()
            self._connect_error = None

    def _create_table(self):
        """创建表"""
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS cache (
                key TEXT PRIMARY KEY,
                url TEXT,
                response_body BLOB,
                status_code INTEGER,
                headers TEXT,
                created_at REAL,
                expires_at REAL,
                hit_count INTEGER DEFAULT 0
            )
        """)
        self._conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_expires ON cache(expires_at)
        """)
        self._conn.commit()

    def _cleanup_expired(self):
        """清理过期缓存"""
        now = time.time()
        self._conn.execute(
            "DELETE FROM cache WHERE expires_at IS NOT NULL AND expires_at < ?",
            (now,)
        )
        self._conn.commit()

    async def get(self, key: str) -> Optional[CacheEntry]:
        """获取缓存"""
        async with self._lock:
            try:
                await asyncio.get_event_loop().run_in_executor(
                    None, self._connect
                )
            except Exception as exc:
                self._connect_error = str(exc)
                self._misses += 1
                return None

            cursor = self._conn.execute(
                "SELECT * FROM cache WHERE key = ?",
                (key,)
            )
            row = cursor.fetchone()

            if row is None:
                self._misses += 1
                return None

            # 检查过期
            expires_at = row[6]
            if expires_at is not None and time.time() > expires_at:
                await self.delete(key)
                self._misses += 1
                return None

            # 更新命中次数
            self._conn.execute(
                "UPDATE cache SET hit_count = hit_count + 1 WHERE key = ?",
                (key,)
            )
            self._conn.commit()

            entry = CacheEntry(
                url=row[1],
                response_body=row[2],
                status_code=row[3],
                headers=json.loads(row[4]),
                created_at=row[5],
                expires_at=expires_at,
                hit_count=row[7] + 1,
            )
            self._hits += 1
            return entry

    async def set(self, key: str, entry: CacheEntry):
        """设置缓存"""
        async with self._lock:
            try:
                await asyncio.get_event_loop().run_in_executor(
                    None, self._connect
                )
            except Exception as exc:
                self._connect_error = str(exc)
                return

            # 检查是否需要淘汰
            cursor = self._conn.execute("SELECT COUNT(*) FROM cache")
            count = cursor.fetchone()[0]

            if count >= self._max_size:
                # 淘汰最旧的
                self._conn.execute(
                    "DELETE FROM cache WHERE key IN ("
                    "SELECT key FROM cache ORDER BY created_at LIMIT 100)"
                )

            # 插入或替换
            self._conn.execute("""
                INSERT OR REPLACE INTO cache
                (key, url, response_body, status_code, headers, created_at, expires_at, hit_count)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                key,
                entry.url,
                entry.response_body,
                entry.status_code,
                json.dumps(entry.headers),
                entry.created_at,
                entry.expires_at,
                entry.hit_count,
            ))
            self._conn.commit()

    async def delete(self, key: str):
        """删除缓存"""
        async with self._lock:
            try:
                await asyncio.get_event_loop().run_in_executor(
                    None, self._connect
                )
            except Exception as exc:
                self._connect_error = str(exc)
                return
            self._conn.execute("DELETE FROM cache WHERE key = ?", (key,))
            self._conn.commit()

    async def clear(self):
        """清空缓存"""
        async with self._lock:
            try:
                await asyncio.get_event_loop().run_in_executor(
                    None, self._connect
                )
            except Exception as exc:
                self._connect_error = str(exc)
                return
            self._conn.execute("DELETE FROM cache")
            self._conn.commit()

    def get_stats(self) -> dict:
        """获取统计信息"""
        if self._conn is None:
            return {
                "size": 0,
                "max_size": self._max_size,
                "connect_error": self._connect_error,
                "db_path": self._db_path,
            }

        cursor = self._conn.execute("SELECT COUNT(*) FROM cache")
        size = cursor.fetchone()[0]

        total = self._hits + self._misses
        hit_rate = self._hits / total if total > 0 else 0

        return {
            "size": size,
            "max_size": self._max_size,
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": hit_rate,
            "connect_error": self._connect_error,
            "db_path": self._db_path,
        }

    def close(self):
        """关闭连接"""
        if self._conn:
            self._conn.close()
            self._conn = None


class RequestCache:
    """
    请求缓存 - 统一管理内存和 SQLite 缓存

    用法:
        cache = RequestCache(use_memory=True, use_sqlite=True, db_path="cache.db")

        # 获取缓存
        entry = await cache.get(url)
        if entry:
            return entry.response_body

        # 设置缓存 (TTL 1 小时)
        await cache.set(url, response_body, status_code, headers, ttl=3600)
    """

    def __init__(
        self,
        use_memory: bool = True,
        use_sqlite: bool = False,
        db_path: Optional[str] = None,
        memory_max_size: int = 1000,
        memory_max_bytes: int = 64 * 1024 * 1024,
        sqlite_max_size: int = 10000,
        default_ttl: Optional[int] = None,
        memory_max_body_bytes: Optional[int] = None,
        sqlite_max_body_bytes: Optional[int] = None,
    ):
        """
        初始化请求缓存

        Args:
            use_memory: 是否使用内存缓存
            use_sqlite: 是否使用 SQLite 缓存
            db_path: SQLite 数据库路径
            memory_max_size: 内存缓存最大大小
            sqlite_max_size: SQLite 缓存最大大小
            default_ttl: 默认 TTL (秒)
        """
        self._memory_cache = MemoryCache(memory_max_size, memory_max_bytes) if use_memory else None
        self._sqlite_cache = None

        if use_sqlite:
            if db_path is None:
                db_path = _resolve_default_sqlite_cache_path()
            self._sqlite_cache = SQLiteCache(db_path, sqlite_max_size)

        self._default_ttl = default_ttl
        self._memory_max_body_bytes = memory_max_body_bytes
        self._sqlite_max_body_bytes = sqlite_max_body_bytes
        self._requests_cached = 0
        self._requests_served = 0
        self._skipped_too_large = 0

    def _generate_key(self, url: str, method: str = "GET") -> str:
        """生成缓存键"""
        key_str = f"{method.upper()}:{url}"
        return hashlib.md5(key_str.encode()).hexdigest()

    async def get(
        self,
        url: str,
        method: str = "GET",
    ) -> Optional[CacheEntry]:
        """
        获取缓存

        Args:
            url: 请求 URL
            method: HTTP 方法

        Returns:
            CacheEntry 或 None
        """
        key = self._generate_key(url, method)

        # 先尝试内存缓存
        if self._memory_cache:
            entry = await self._memory_cache.get(key)
            if entry:
                self._requests_served += 1
                return entry

        # 尝试 SQLite 缓存
        if self._sqlite_cache:
            try:
                entry = await self._sqlite_cache.get(key)
            except Exception as exc:
                logger.debug("SQLite cache get failed: %s", exc)
                entry = None
            if entry:
                # 回填到内存缓存
                if (
                    self._memory_cache
                    and (
                        self._memory_max_body_bytes is None
                        or len(entry.response_body or b"") <= self._memory_max_body_bytes
                    )
                ):
                    await self._memory_cache.set(key, entry)
                self._requests_served += 1
                return entry

        return None

    async def set(
        self,
        url: str,
        response_body: bytes,
        status_code: int,
        headers: Dict[str, str],
        method: str = "GET",
        ttl: Optional[int] = None,
    ):
        """
        设置缓存

        Args:
            url: 请求 URL
            response_body: 响应体
            status_code: 状态码
            headers: 响应头
            method: HTTP 方法
            ttl: TTL (秒), None 表示使用默认值
        """
        key = self._generate_key(url, method)

        # 计算过期时间
        if ttl is None:
            ttl = self._default_ttl

        expires_at = None
        if ttl is not None:
            expires_at = time.time() + ttl

        entry = CacheEntry(
            url=url,
            response_body=response_body,
            status_code=status_code,
            headers=headers,
            expires_at=expires_at,
        )

        # 写入内存缓存
        stored = False

        if (
            self._memory_cache
            and (
                self._memory_max_body_bytes is None
                or len(response_body) <= self._memory_max_body_bytes
            )
        ):
            await self._memory_cache.set(key, entry)
            stored = True

        # 写入 SQLite 缓存
        if (
            self._sqlite_cache
            and (
                self._sqlite_max_body_bytes is None
                or len(response_body) <= self._sqlite_max_body_bytes
            )
        ):
            try:
                await self._sqlite_cache.set(key, entry)
                stored = True
            except Exception as exc:
                logger.debug("SQLite cache set failed: %s", exc)

        if stored:
            self._requests_cached += 1
        else:
            self._skipped_too_large += 1

    async def delete(self, url: str, method: str = "GET"):
        """删除缓存"""
        key = self._generate_key(url, method)

        tasks = []
        if self._memory_cache:
            tasks.append(self._memory_cache.delete(key))
        if self._sqlite_cache:
            tasks.append(self._sqlite_cache.delete(key))

        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def clear(self):
        """清空缓存"""
        tasks = []
        if self._memory_cache:
            tasks.append(self._memory_cache.clear())
        if self._sqlite_cache:
            tasks.append(self._sqlite_cache.clear())

        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

        self._requests_cached = 0
        self._requests_served = 0

    def get_stats(self) -> dict:
        """获取统计信息"""
        stats = {
            "requests_cached": self._requests_cached,
            "requests_served": self._requests_served,
            "skipped_too_large": self._skipped_too_large,
            "cache_efficiency": self._requests_served / max(1, self._requests_cached + self._requests_served),
        }

        if self._memory_cache:
            stats["memory_cache"] = self._memory_cache.get_stats()

        if self._sqlite_cache:
            stats["sqlite_cache"] = self._sqlite_cache.get_stats()

        return stats

    def close(self):
        """关闭缓存"""
        if self._sqlite_cache:
            self._sqlite_cache.close()

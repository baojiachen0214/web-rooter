"""
Session Manager - 会话管理器

功能：
- 多 Session 支持
- 按请求路由到不同 Session
- 懒加载支持
- Session 状态管理
"""
import asyncio
import random
from typing import Optional, Dict, Any, List, Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
import logging
from collections import defaultdict

from .request import Request
from .response import Response

logger = logging.getLogger(__name__)


class SessionType(Enum):
    """会话类型"""
    HTTP = "http"  # 普通 HTTP 会话
    STEALTH = "stealth"  # 隐身浏览器会话
    DYNAMIC = "dynamic"  # 动态渲染会话
    CUSTOM = "custom"  # 自定义会话


@dataclass
class SessionConfig:
    """会话配置"""
    session_id: str
    session_type: SessionType
    proxy: Optional[str] = None
    user_agent: Optional[str] = None
    headers: Dict[str, str] = field(default_factory=dict)
    cookies: Dict[str, str] = field(default_factory=dict)
    max_requests: int = 100  # 最大请求数
    max_lifetime: int = 3600  # 最大生命周期（秒）
    max_concurrent: int = 5  # 最大并发请求数


@dataclass
class SessionStats:
    """会话统计"""
    requests: int = 0
    successes: int = 0
    failures: int = 0
    bytes_transferred: int = 0
    created_at: datetime = field(default_factory=datetime.now)
    last_used: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "requests": self.requests,
            "successes": self.successes,
            "failures": self.failures,
            "bytes_transferred": self.bytes_transferred,
            "created_at": self.created_at.isoformat(),
            "last_used": self.last_used.isoformat(),
            "success_rate": self.successes / (self.successes + self.failures) if (self.successes + self.failures) > 0 else 0,
        }


class Session:
    """
    Session - 会话对象

    封装单个会话的状态和配置
    """

    def __init__(self, config: SessionConfig):
        self.config = config
        self.session_id = config.session_id
        self.session_type = config.session_type

        # 状态管理
        self.active = True
        self._request_count = 0
        self._created_at = datetime.now()
        self._last_used = datetime.now()
        self._lock = asyncio.Lock()

        # 统计信息
        self._stats = SessionStats()

        # 资源引用（如浏览器上下文）
        self._resource: Any = None
        self._initialized = False

        # 请求头
        self._headers = dict(config.headers)
        if config.user_agent:
            self._headers["User-Agent"] = config.user_agent

        # Cookies
        self._cookies = dict(config.cookies)

    @property
    def is_expired(self) -> bool:
        """会话是否过期"""
        # 检查生命周期
        lifetime = (datetime.now() - self._created_at).total_seconds()
        if lifetime > self.config.max_lifetime:
            return True

        # 检查请求数限制
        if self._request_count >= self.config.max_requests:
            return True

        return False

    @property
    def is_available(self) -> bool:
        """会话是否可用"""
        return self.active and not self.is_expired

    @property
    def age(self) -> float:
        """会话年龄（秒）"""
        return (datetime.now() - self._created_at).total_seconds()

    @property
    def idle_time(self) -> float:
        """空闲时间（秒）"""
        return (datetime.now() - self._last_used).total_seconds()

    async def acquire(self) -> bool:
        """获取会话锁"""
        if not self.is_available:
            return False

        await self._lock.acquire()
        return True

    def release(self):
        """释放会话锁"""
        try:
            self._lock.release()
        except RuntimeError:
            pass

    async def use(self, success: bool = True, bytes_transferred: int = 0):
        """
        使用会话

        Args:
            success: 请求是否成功
            bytes_transferred: 传输字节数
        """
        self._request_count += 1
        self._last_used = datetime.now()

        self._stats.requests += 1
        if success:
            self._stats.successes += 1
        else:
            self._stats.failures += 1
        self._stats.bytes_transferred += bytes_transferred

    def mark_inactive(self):
        """标记会话为不活跃"""
        self.active = False

    def get_stats(self) -> Dict[str, Any]:
        """获取会话统计"""
        return {
            "session_id": self.session_id,
            "session_type": self.session_type.value,
            "active": self.active,
            "request_count": self._request_count,
            "age_seconds": self.age,
            "idle_seconds": self.idle_time,
            **self._stats.to_dict(),
        }

    def set_resource(self, resource: Any):
        """设置关联资源（如浏览器上下文）"""
        self._resource = resource
        self._initialized = True

    def get_resource(self) -> Any:
        """获取关联资源"""
        return self._resource

    def __repr__(self) -> str:
        return f"<Session {self.session_id} ({self.session_type.value})>"


class RoutingStrategy(Enum):
    """路由策略"""
    ROUND_ROBIN = "round_robin"  # 循环轮换
    RANDOM = "random"  # 随机选择
    LEAST_LOADED = "least_loaded"  # 最少负载
    SUCCESS_BASED = "success_based"  # 基于成功率
    TYPE_BASED = "type_based"  # 基于请求类型


class SessionManager:
    """
    SessionManager - 会话管理器

    功能：
    - 多 Session 注册和管理
    - 请求路由到不同 Session
    - 懒加载支持
    - 自动清理过期会话

    用法:
        session_mgr = SessionManager()

        # 注册会话
        await session_mgr.register_session(
            SessionConfig("http_1", SessionType.HTTP, proxy="...")
        )

        # 获取会话
        session = await session_mgr.get_session(request)

        # 使用会话
        async with session:
            response = await fetch_with_session(session, request)
            await session.use(success=response.success)
    """

    def __init__(
        self,
        routing_strategy: RoutingStrategy = RoutingStrategy.ROUND_ROBIN,
        auto_cleanup: bool = True,
        cleanup_interval: int = 60,
    ):
        """
        初始化会话管理器

        Args:
            routing_strategy: 路由策略
            auto_cleanup: 是否自动清理过期会话
            cleanup_interval: 清理间隔（秒）
        """
        self.routing_strategy = routing_strategy
        self.auto_cleanup = auto_cleanup
        self.cleanup_interval = cleanup_interval

        # Session 存储
        self._sessions: Dict[str, Session] = {}
        self._sessions_by_type: Dict[SessionType, List[str]] = defaultdict(list)

        # 路由状态
        self._round_robin_index = 0
        self._lock = asyncio.Lock()

        # 懒加载
        self._lazy_factories: Dict[str, Callable] = {}

        # 统计
        self._total_routed = 0
        self._total_failures = 0

        # 自动清理任务
        self._cleanup_task: Optional[asyncio.Task] = None
        self._running = False

        # 转换路由策略为枚举
        if isinstance(routing_strategy, str):
            strategy_map = {
                "round_robin": RoutingStrategy.ROUND_ROBIN,
                "random": RoutingStrategy.RANDOM,
                "least_loaded": RoutingStrategy.LEAST_LOADED,
                "success_based": RoutingStrategy.SUCCESS_BASED,
                "type_based": RoutingStrategy.TYPE_BASED,
            }
            self.routing_strategy = strategy_map.get(routing_strategy, RoutingStrategy.ROUND_ROBIN)
        else:
            self.routing_strategy = routing_strategy

    async def start(self):
        """启动会话管理器"""
        if self._running:
            return

        self._running = True

        if self.auto_cleanup:
            self._cleanup_task = asyncio.create_task(self._auto_cleanup_loop())
            logger.info(f"自动清理已启动，间隔 {self.cleanup_interval} 秒")

    async def stop(self):
        """停止会话管理器"""
        self._running = False

        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass

        # 关闭所有会话
        for session in list(self._sessions.values()):
            session.mark_inactive()

        logger.info("会话管理器已停止")

    async def __aenter__(self) -> "SessionManager":
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.stop()

    async def register_session(self, config: SessionConfig) -> Session:
        """
        注册会话

        Args:
            config: 会话配置

        Returns:
            Session 对象
        """
        async with self._lock:
            session = Session(config)
            self._sessions[config.session_id] = session
            self._sessions_by_type[config.session_type].append(config.session_id)

            logger.info(f"注册会话：{config.session_id} ({config.session_type.value})")
            return session

    async def unregister_session(self, session_id: str) -> bool:
        """
        注销会话

        Args:
            session_id: 会话 ID

        Returns:
            True 如果成功注销
        """
        async with self._lock:
            if session_id not in self._sessions:
                return False

            session = self._sessions[session_id]
            session.mark_inactive()

            del self._sessions[session_id]

            # 从类型列表中移除
            session_type = session.session_type
            if session_id in self._sessions_by_type[session_type]:
                self._sessions_by_type[session_type].remove(session_id)

            logger.info(f"注销会话：{session_id}")
            return True

    def register_lazy_factory(self, session_id: str, factory: Callable):
        """
        注册懒加载工厂

        Args:
            session_id: 会话 ID
            factory: 工厂函数，返回 SessionConfig
        """
        self._lazy_factories[session_id] = factory

    async def _lazy_create_session(self, session_id: str) -> Optional[Session]:
        """懒加载创建会话"""
        factory = self._lazy_factories.get(session_id)
        if not factory:
            return None

        try:
            config = factory()
            if config:
                return await self.register_session(config)
        except Exception as e:
            logger.error(f"懒加载会话失败 {session_id}: {e}")

        return None

    async def get_session(
        self,
        request: Optional[Request] = None,
        session_type: Optional[SessionType] = None,
        session_id: Optional[str] = None,
    ) -> Optional[Session]:
        """
        获取会话

        Args:
            request: 请求对象（用于路由）
            session_type: 指定会话类型
            session_id: 指定会话 ID

        Returns:
            Session 对象或 None
        """
        # 指定 ID
        if session_id:
            session = self._sessions.get(session_id)
            if not session:
                # 尝试懒加载
                session = await self._lazy_create_session(session_id)
            return session if session and session.is_available else None

        # 指定类型
        if session_type:
            return await self._get_session_by_type(session_type)

        # 根据路由策略
        return await self._route_session(request)

    async def _get_session_by_type(self, session_type: SessionType) -> Optional[Session]:
        """按类型获取会话"""
        session_ids = self._sessions_by_type.get(session_type, [])

        if not session_ids:
            # 尝试懒加载
            for lazy_id, factory in self._lazy_factories.items():
                try:
                    config = factory()
                    if config and config.session_type == session_type:
                        return await self.register_session(config)
                except Exception as e:
                    logger.error(f"懒加载会话失败 {lazy_id}: {e}")
            return None

        # 选择可用的会话
        available = [
            self._sessions[sid] for sid in session_ids
            if self._sessions[sid].is_available
        ]

        if not available:
            return None

        # 根据策略选择
        if self.routing_strategy == RoutingStrategy.RANDOM:
            return random.choice(available)
        elif self.routing_strategy == RoutingStrategy.LEAST_LOADED:
            return min(available, key=lambda s: s._request_count)
        elif self.routing_strategy == RoutingStrategy.SUCCESS_BASED:
            # 选择成功率最高的
            def success_rate(s):
                total = s._stats.successes + s._stats.failures
                return s._stats.successes / total if total > 0 else 0
            return max(available, key=success_rate)
        else:
            return available[0]

    async def _route_session(self, request: Optional[Request]) -> Optional[Session]:
        """路由会话"""
        available_sessions = [
            s for s in self._sessions.values()
            if s.is_available
        ]

        if not available_sessions:
            # 尝试懒加载
            for lazy_id, factory in list(self._lazy_factories.items()):
                try:
                    config = factory()
                    if config:
                        session = await self.register_session(config)
                        if session:
                            available_sessions.append(session)
                except Exception as e:
                    logger.error(f"懒加载会话失败 {lazy_id}: {e}")

        if not available_sessions:
            return None

        # 根据策略路由
        if self.routing_strategy == RoutingStrategy.ROUND_ROBIN:
            session = self._round_robin_select(available_sessions)
        elif self.routing_strategy == RoutingStrategy.RANDOM:
            session = random.choice(available_sessions)
        elif self.routing_strategy == RoutingStrategy.LEAST_LOADED:
            session = min(available_sessions, key=lambda s: s._request_count)
        elif self.routing_strategy == RoutingStrategy.SUCCESS_BASED:
            def success_rate(s):
                total = s._stats.successes + s._stats.failures
                return s._stats.successes / total if total > 0 else 0
            session = max(available_sessions, key=success_rate)
        else:
            session = available_sessions[0]

        self._total_routed += 1
        return session

    def _round_robin_select(self, sessions: List[Session]) -> Session:
        """循环轮换选择"""
        if not sessions:
            raise ValueError("No sessions available")

        # 确保索引有效
        self._round_robin_index = self._round_robin_index % len(sessions)
        session = sessions[self._round_robin_index]
        self._round_robin_index = (self._round_robin_index + 1) % len(sessions)
        return session

    async def get_all_sessions(self) -> List[Session]:
        """获取所有会话"""
        return list(self._sessions.values())

    async def get_available_sessions(self) -> List[Session]:
        """获取所有可用会话"""
        return [s for s in self._sessions.values() if s.is_available]

    async def cleanup_expired(self) -> int:
        """清理过期会话"""
        expired = [
            session for session in self._sessions.values()
            if session.is_expired
        ]

        count = 0
        for session in expired:
            await self.unregister_session(session.session_id)
            count += 1

        if count > 0:
            logger.info(f"清理了 {count} 个过期会话")

        return count

    async def _auto_cleanup_loop(self):
        """自动清理循环"""
        while self._running:
            try:
                await asyncio.sleep(self.cleanup_interval)
                await self.cleanup_expired()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"自动清理循环错误：{e}")

    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        sessions_stats = [s.get_stats() for s in self._sessions.values()]

        return {
            "total_sessions": len(self._sessions),
            "available_sessions": len([s for s in self._sessions.values() if s.is_available]),
            "total_routed": self._total_routed,
            "total_failures": self._total_failures,
            "routing_strategy": self.routing_strategy.value if hasattr(self.routing_strategy, 'value') else str(self.routing_strategy),
            "sessions": sessions_stats,
        }

    def get_session_count(self, session_type: Optional[SessionType] = None) -> int:
        """获取会话数量"""
        if session_type:
            return len(self._sessions_by_type.get(session_type, []))
        return len(self._sessions)


async def create_session_manager(
    routing_strategy: str = "round_robin",
    auto_cleanup: bool = True,
    cleanup_interval: int = 60,
    initial_sessions: Optional[List[SessionConfig]] = None,
) -> SessionManager:
    """
    便捷函数：创建并初始化会话管理器

    Args:
        routing_strategy: 路由策略
        auto_cleanup: 是否自动清理
        cleanup_interval: 清理间隔
        initial_sessions: 初始会话列表

    Returns:
        SessionManager 对象
    """
    strategy_map = {
        "round_robin": RoutingStrategy.ROUND_ROBIN,
        "random": RoutingStrategy.RANDOM,
        "least_loaded": RoutingStrategy.LEAST_LOADED,
        "success_based": RoutingStrategy.SUCCESS_BASED,
        "type_based": RoutingStrategy.TYPE_BASED,
    }

    manager = SessionManager(
        routing_strategy=strategy_map.get(routing_strategy, RoutingStrategy.ROUND_ROBIN),
        auto_cleanup=auto_cleanup,
        cleanup_interval=cleanup_interval,
    )

    await manager.start()

    if initial_sessions:
        for config in initial_sessions:
            await manager.register_session(config)

    return manager


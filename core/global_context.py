"""
全局深度抓取上下文存储。

用途：
- 为外层 Claude Code 保留“跨命令会话”的抓取轨迹
- 提供轻量事件流，便于后续二次分析、追溯、重放
"""
from __future__ import annotations

import json
import logging
import os
import threading
import uuid
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Deque, Dict, List, Optional

logger = logging.getLogger(__name__)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class ContextEvent:
    """上下文事件。"""

    id: str
    event_type: str
    source: str
    timestamp: str
    payload: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "event_type": self.event_type,
            "source": self.source,
            "timestamp": self.timestamp,
            "payload": self.payload,
        }


class GlobalDeepContextStore:
    """进程内全局上下文存储。"""

    def __init__(
        self,
        max_events: int = 500,
        persist_path: Optional[Path] = None,
        max_persisted_events: Optional[int] = None,
    ):
        self._events: Deque[ContextEvent] = deque(maxlen=max_events)
        self._max_events = max_events
        self._lock = threading.Lock()
        self._persist_path = persist_path
        persisted_default = max(max_events, max_events * 4)
        self._max_persisted_events = max_persisted_events or persisted_default
        self._persisted_events = 0
        if self._persist_path:
            self._persist_path.parent.mkdir(parents=True, exist_ok=True)
            self._load_persisted_events()

    @property
    def size(self) -> int:
        return len(self._events)

    def record(self, event_type: str, source: str, payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        payload = self._trim_payload(payload or {})
        event = ContextEvent(
            id=str(uuid.uuid4()),
            event_type=event_type,
            source=source,
            timestamp=_utc_now_iso(),
            payload=payload,
        )
        with self._lock:
            self._events.append(event)
            self._persist_event(event)
        return event.to_dict()

    def snapshot(self, limit: int = 20, event_type: Optional[str] = None) -> Dict[str, Any]:
        limit = max(1, limit)
        with self._lock:
            events = list(self._events)
        if event_type:
            events = [e for e in events if e.event_type == event_type]
        sliced = events[-limit:]
        return {
            "stats": {
                "total_events": len(events),
                "store_size": self.size,
                "max_events": self._max_events,
            },
            "events": [e.to_dict() for e in sliced],
        }

    def clear(self) -> None:
        with self._lock:
            self._events.clear()
            if self._persist_path:
                self._rewrite_persisted_events_locked()

    def _persist_event(self, event: ContextEvent) -> None:
        if not self._persist_path:
            return
        try:
            with self._persist_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(event.to_dict(), ensure_ascii=False) + "\n")
            self._persisted_events += 1
            if self._persisted_events > self._max_persisted_events:
                self._rewrite_persisted_events_locked()
        except Exception as exc:
            logger.debug("写入全局上下文失败: %s", exc)

    def _load_persisted_events(self) -> None:
        if not self._persist_path or not self._persist_path.exists():
            return
        try:
            for line in self._tail_lines(self._persist_path, self._max_persisted_events):
                line = line.strip()
                if not line:
                    continue
                try:
                    item = json.loads(line)
                    event = ContextEvent(
                        id=str(item.get("id") or str(uuid.uuid4())),
                        event_type=str(item.get("event_type") or "unknown"),
                        source=str(item.get("source") or "unknown"),
                        timestamp=str(item.get("timestamp") or _utc_now_iso()),
                        payload=item.get("payload") if isinstance(item.get("payload"), dict) else {},
                    )
                    self._events.append(event)
                    self._persisted_events += 1
                except Exception:
                    continue
            if self._persisted_events > self._max_persisted_events:
                self._rewrite_persisted_events_locked()
        except Exception as exc:
            logger.debug("读取全局上下文失败: %s", exc)

    def _rewrite_persisted_events_locked(self) -> None:
        if not self._persist_path:
            return
        try:
            recent_events = list(self._events)[-self._max_persisted_events:]
            with self._persist_path.open("w", encoding="utf-8") as f:
                for event in recent_events:
                    f.write(json.dumps(event.to_dict(), ensure_ascii=False) + "\n")
            self._persisted_events = len(recent_events)
        except Exception as exc:
            logger.debug("压缩全局上下文失败: %s", exc)

    @staticmethod
    def _tail_lines(path: Path, limit: int, block_size: int = 4096) -> List[str]:
        if limit <= 0:
            return []

        with path.open("rb") as f:
            f.seek(0, os.SEEK_END)
            file_size = f.tell()
            if file_size <= 0:
                return []

            buffer = bytearray()
            lines: List[bytes] = []
            position = file_size

            while position > 0 and len(lines) <= limit:
                read_size = min(block_size, position)
                position -= read_size
                f.seek(position)
                buffer[:0] = f.read(read_size)
                lines = buffer.splitlines()

            tail = lines[-limit:]
            return [line.decode("utf-8", errors="ignore") for line in tail]

    @staticmethod
    def _trim_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
        def _trim_value(value: Any) -> Any:
            if isinstance(value, str):
                return value if len(value) <= 1200 else value[:1200] + "...[truncated]"
            if isinstance(value, list):
                return [_trim_value(v) for v in value[:40]]
            if isinstance(value, dict):
                trimmed: Dict[str, Any] = {}
                for idx, (k, v) in enumerate(value.items()):
                    if idx >= 60:
                        break
                    trimmed[str(k)] = _trim_value(v)
                return trimmed
            return value

        return _trim_value(payload)


_store: Optional[GlobalDeepContextStore] = None


def get_global_deep_context() -> GlobalDeepContextStore:
    global _store
    if _store is None:
        max_events = int(os.getenv("WEB_ROOTER_CONTEXT_MAX_EVENTS", "500") or 500)
        max_persisted_events = int(
            os.getenv("WEB_ROOTER_CONTEXT_MAX_PERSISTED_EVENTS", str(max(max_events, max_events * 4))) or max(max_events, max_events * 4)
        )
        default_path = Path(".web-rooter") / "global-context.jsonl"
        persist_path_raw = os.getenv("WEB_ROOTER_CONTEXT_PATH", "").strip()
        persist_path = Path(persist_path_raw).expanduser() if persist_path_raw else default_path
        _store = GlobalDeepContextStore(
            max_events=max_events,
            persist_path=persist_path,
            max_persisted_events=max_persisted_events,
        )
    return _store

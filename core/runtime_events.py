"""
Bounded runtime event stream with backpressure-friendly semantics.

Design goals:
- Keep observability data in-process and queryable.
- Enforce strict size limits so event logging cannot become a memory leak.
- Support incremental reads via sequence cursor (since_seq).
"""
from __future__ import annotations

import threading
import uuid
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Deque, Dict, List, Optional


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _trim_scalar(value: Any, max_chars: int) -> str:
    text = "" if value is None else str(value)
    return text if len(text) <= max_chars else text[:max_chars] + "...[truncated]"


def _trim_value(
    value: Any,
    *,
    max_depth: int,
    max_items: int,
    max_string_chars: int,
    depth: int = 0,
) -> Any:
    if depth >= max_depth:
        return _trim_scalar(value, max_string_chars)

    if isinstance(value, str):
        return _trim_scalar(value, max_string_chars)

    if isinstance(value, (int, float, bool)) or value is None:
        return value

    if isinstance(value, list):
        return [
            _trim_value(
                item,
                max_depth=max_depth,
                max_items=max_items,
                max_string_chars=max_string_chars,
                depth=depth + 1,
            )
            for item in value[:max_items]
        ]

    if isinstance(value, dict):
        compact: Dict[str, Any] = {}
        for idx, (key, item) in enumerate(value.items()):
            if idx >= max_items:
                break
            compact[_trim_scalar(key, 120)] = _trim_value(
                item,
                max_depth=max_depth,
                max_items=max_items,
                max_string_chars=max_string_chars,
                depth=depth + 1,
            )
        return compact

    return _trim_scalar(value, max_string_chars)


@dataclass(frozen=True)
class RuntimeEventBudget:
    """Budget controls for runtime event stream."""

    max_events: int = 600
    max_event_type_chars: int = 80
    max_source_chars: int = 80
    max_payload_items: int = 48
    max_payload_depth: int = 3
    max_payload_string_chars: int = 320


@dataclass
class RuntimeEvent:
    seq: int
    event_id: str
    event_type: str
    source: str
    timestamp: str
    payload: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "seq": self.seq,
            "id": self.event_id,
            "event_type": self.event_type,
            "source": self.source,
            "timestamp": self.timestamp,
            "payload": self.payload,
        }


class RuntimeEventStream:
    """Bounded in-process runtime event stream."""

    def __init__(self, budget: Optional[RuntimeEventBudget] = None):
        self._budget = budget or RuntimeEventBudget()
        self._events: Deque[RuntimeEvent] = deque(maxlen=self._budget.max_events)
        self._lock = threading.Lock()
        self._next_seq = 1
        self._total_recorded = 0
        self._total_dropped = 0

    @property
    def budget(self) -> RuntimeEventBudget:
        return self._budget

    def clear(self) -> None:
        with self._lock:
            self._events.clear()
            self._next_seq = 1
            self._total_recorded = 0
            self._total_dropped = 0

    def record(
        self,
        event_type: str,
        source: str,
        payload: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        compact_event_type = _trim_scalar(event_type or "unknown", self._budget.max_event_type_chars)
        compact_source = _trim_scalar(source or "unknown", self._budget.max_source_chars)
        compact_payload = self._compact_payload(payload or {})

        with self._lock:
            if len(self._events) >= self._budget.max_events:
                self._total_dropped += 1

            event = RuntimeEvent(
                seq=self._next_seq,
                event_id=str(uuid.uuid4()),
                event_type=compact_event_type,
                source=compact_source,
                timestamp=_utc_now_iso(),
                payload=compact_payload,
            )
            self._events.append(event)
            self._next_seq += 1
            self._total_recorded += 1
            return event.to_dict()

    def snapshot(
        self,
        *,
        limit: int = 50,
        event_type: Optional[str] = None,
        source: Optional[str] = None,
        since_seq: Optional[int] = None,
    ) -> Dict[str, Any]:
        bounded_limit = max(1, min(limit, 2000))
        normalized_event_type = (event_type or "").strip() or None
        normalized_source = (source or "").strip() or None
        min_seq = since_seq if isinstance(since_seq, int) and since_seq > 0 else None

        with self._lock:
            events = list(self._events)
            total_recorded = self._total_recorded
            total_dropped = self._total_dropped
            newest_seq = self._next_seq - 1

        if min_seq is not None:
            events = [item for item in events if item.seq > min_seq]
        if normalized_event_type is not None:
            events = [item for item in events if item.event_type == normalized_event_type]
        if normalized_source is not None:
            events = [item for item in events if item.source == normalized_source]

        sliced = events[-bounded_limit:]
        return {
            "stats": {
                "total_events": len(events),
                "store_size": len(self._events),
                "max_events": self._budget.max_events,
                "total_recorded": total_recorded,
                "dropped_events": total_dropped,
                "newest_seq": newest_seq,
            },
            "filters": {
                "limit": bounded_limit,
                "event_type": normalized_event_type,
                "source": normalized_source,
                "since_seq": min_seq,
            },
            "events": [item.to_dict() for item in sliced],
            "truncated": len(events) > len(sliced),
            "next_cursor": sliced[-1].seq if sliced else (min_seq or newest_seq),
        }

    def get_stats(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "store_size": len(self._events),
                "max_events": self._budget.max_events,
                "total_recorded": self._total_recorded,
                "dropped_events": self._total_dropped,
                "newest_seq": self._next_seq - 1,
            }

    def _compact_payload(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        compact = _trim_value(
            payload,
            max_depth=self._budget.max_payload_depth,
            max_items=self._budget.max_payload_items,
            max_string_chars=self._budget.max_payload_string_chars,
        )
        if isinstance(compact, dict):
            return compact
        return {"value": compact}

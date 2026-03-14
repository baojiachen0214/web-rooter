"""
Budgeted runtime state for long-lived agent sessions.

The goal is to keep the in-process research state useful while making memory
growth predictable and bounded.
"""
from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional


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
        trimmed: Dict[str, Any] = {}
        for idx, (key, item) in enumerate(value.items()):
            if idx >= max_items:
                break
            trimmed[str(key)] = _trim_value(
                item,
                max_depth=max_depth,
                max_items=max_items,
                max_string_chars=max_string_chars,
                depth=depth + 1,
            )
        return trimmed

    return _trim_scalar(value, max_string_chars)


@dataclass(frozen=True)
class RuntimeStateBudget:
    """Budget for in-process state."""

    max_pages: int = 128
    max_total_content_chars: int = 1_200_000
    max_page_content_chars: int = 16_000
    max_links_per_page: int = 24
    max_metadata_items: int = 40
    max_metadata_depth: int = 3
    max_metadata_string_chars: int = 500
    max_visited_urls: int = 512
    knowledge_preview_chars: int = 500


@dataclass
class PageSnapshot:
    """Compact page representation retained in the agent session."""

    url: str
    title: str
    content: str
    links: List[Dict[str, str]]
    extracted_info: Dict[str, Any]
    timestamp: datetime = field(default_factory=datetime.now)
    content_chars: int = 0
    truncated: bool = False

    def to_summary(self, preview_chars: int = 500) -> Dict[str, Any]:
        return {
            "url": self.url,
            "title": self.title,
            "content_preview": self.content[:preview_chars],
            "content_chars": self.content_chars,
            "links_count": len(self.links),
            "truncated": self.truncated,
            "timestamp": self.timestamp.isoformat(),
        }


class AgentRuntimeState:
    """Bounded LRU-like state for visited pages and session memory."""

    def __init__(self, budget: Optional[RuntimeStateBudget] = None):
        self._budget = budget or RuntimeStateBudget()
        self._pages: "OrderedDict[str, PageSnapshot]" = OrderedDict()
        self._visited_urls: "OrderedDict[str, None]" = OrderedDict()
        self._total_content_chars = 0
        self._counters: Dict[str, int] = {
            "pages_stored": 0,
            "pages_replaced": 0,
            "pages_evicted": 0,
            "visited_marked": 0,
            "visited_evicted": 0,
            "content_truncated": 0,
            "link_items_dropped": 0,
        }

    @property
    def budget(self) -> RuntimeStateBudget:
        return self._budget

    def mark_visited(self, url: str) -> None:
        if not url:
            return
        self._counters["visited_marked"] += 1
        if url in self._visited_urls:
            self._visited_urls.move_to_end(url)
        else:
            self._visited_urls[url] = None
        while len(self._visited_urls) > self._budget.max_visited_urls:
            self._visited_urls.popitem(last=False)
            self._counters["visited_evicted"] += 1

    def has_visited(self, url: str) -> bool:
        return url in self._visited_urls

    def get_visited_urls(self) -> List[str]:
        return list(self._visited_urls.keys())

    def has_page(self, url: str) -> bool:
        return url in self._pages

    def get_page(self, url: str) -> Optional[PageSnapshot]:
        snapshot = self._pages.get(url)
        if snapshot is not None:
            self._pages.move_to_end(url)
        return snapshot

    def iter_pages(self) -> Iterable[PageSnapshot]:
        return list(self._pages.values())

    def store_page(
        self,
        *,
        url: str,
        title: str,
        content: str,
        content_chars: Optional[int] = None,
        links: Optional[List[Dict[str, Any]]] = None,
        extracted_info: Optional[Dict[str, Any]] = None,
    ) -> PageSnapshot:
        self._counters["pages_stored"] += 1
        normalized_content = (content or "").strip()
        original_content_chars = max(len(normalized_content), int(content_chars or 0))
        truncated = original_content_chars > self._budget.max_page_content_chars
        if truncated:
            normalized_content = normalized_content[: self._budget.max_page_content_chars]
            self._counters["content_truncated"] += 1

        compact_links: List[Dict[str, str]] = []
        raw_links = links if isinstance(links, list) else []
        if len(raw_links) > self._budget.max_links_per_page:
            self._counters["link_items_dropped"] += len(raw_links) - self._budget.max_links_per_page
        for raw_link in raw_links[: self._budget.max_links_per_page]:
            if not isinstance(raw_link, dict):
                continue
            href = _trim_scalar(raw_link.get("href", ""), 500).strip()
            if not href:
                continue
            compact_links.append(
                {
                    "href": href,
                    "text": _trim_scalar(raw_link.get("text", ""), 160).strip(),
                }
            )

        compact_info = _trim_value(
            extracted_info or {},
            max_depth=self._budget.max_metadata_depth,
            max_items=self._budget.max_metadata_items,
            max_string_chars=self._budget.max_metadata_string_chars,
        )
        if not isinstance(compact_info, dict):
            compact_info = {"value": compact_info}

        snapshot = PageSnapshot(
            url=url,
            title=_trim_scalar(title, 300).strip(),
            content=normalized_content,
            links=compact_links,
            extracted_info=compact_info,
            content_chars=original_content_chars,
            truncated=truncated,
        )

        existing = self._pages.pop(url, None)
        if existing is not None:
            self._total_content_chars -= len(existing.content)
            self._counters["pages_replaced"] += 1

        self._pages[url] = snapshot
        self._total_content_chars += len(snapshot.content)
        self._evict_pages()
        return snapshot

    def get_knowledge_base(self) -> List[Dict[str, Any]]:
        return [
            page.to_summary(self._budget.knowledge_preview_chars)
            for page in self._pages.values()
        ]

    def get_stats(self) -> Dict[str, Any]:
        page_utilization = (
            len(self._pages) / max(1, self._budget.max_pages)
        )
        visited_utilization = (
            len(self._visited_urls) / max(1, self._budget.max_visited_urls)
        )
        content_utilization = (
            self._total_content_chars / max(1, self._budget.max_total_content_chars)
        )
        return {
            "pages": len(self._pages),
            "visited_urls": len(self._visited_urls),
            "total_content_chars": self._total_content_chars,
            "utilization": {
                "pages_ratio": round(page_utilization, 4),
                "visited_ratio": round(visited_utilization, 4),
                "content_ratio": round(content_utilization, 4),
            },
            "counters": dict(self._counters),
            "budget": {
                "max_pages": self._budget.max_pages,
                "max_total_content_chars": self._budget.max_total_content_chars,
                "max_page_content_chars": self._budget.max_page_content_chars,
                "max_visited_urls": self._budget.max_visited_urls,
            },
        }

    def clear(self) -> None:
        self._pages.clear()
        self._visited_urls.clear()
        self._total_content_chars = 0
        for key in list(self._counters.keys()):
            self._counters[key] = 0

    def _evict_pages(self) -> None:
        while self._pages and (
            len(self._pages) > self._budget.max_pages
            or self._total_content_chars > self._budget.max_total_content_chars
        ):
            _, evicted = self._pages.popitem(last=False)
            self._total_content_chars -= len(evicted.content)
            self._counters["pages_evicted"] += 1

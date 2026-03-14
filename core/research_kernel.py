"""
Research kernel.

This module owns the lowest-level page acquisition workflow:
- fetch through HTTP or browser
- fallback routing
- bounded page/session state
- bounded runtime event stream
- compact page payload generation

Higher layers such as WebAgent, CLI, MCP, or future planners should delegate to
this kernel instead of re-implementing page state logic.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

from core.artifact_graph import ArtifactGraph
from core.runtime_events import RuntimeEventStream
from core.runtime_pressure import RuntimePressureController
from core.runtime_state import AgentRuntimeState, PageSnapshot

logger = logging.getLogger(__name__)

try:
    from core.browser import BrowserManager, BrowserResult
except ModuleNotFoundError as exc:  # pragma: no cover - optional runtime dependency
    BrowserManager = None  # type: ignore[assignment]
    BrowserResult = Any  # type: ignore[misc,assignment]
    _BROWSER_IMPORT_ERROR: Optional[Exception] = exc
else:
    _BROWSER_IMPORT_ERROR = None

try:
    from core.crawler import CrawlResult, Crawler
except ModuleNotFoundError as exc:  # pragma: no cover - optional runtime dependency
    Crawler = None  # type: ignore[assignment]
    CrawlResult = Any  # type: ignore[misc,assignment]
    _CRAWLER_IMPORT_ERROR: Optional[Exception] = exc
else:
    _CRAWLER_IMPORT_ERROR = None

try:
    from core.parser import ExtractedData, Parser
except ModuleNotFoundError as exc:  # pragma: no cover - optional runtime dependency
    ExtractedData = Any  # type: ignore[misc,assignment]
    Parser = None  # type: ignore[assignment]
    _PARSER_IMPORT_ERROR: Optional[Exception] = exc
else:
    _PARSER_IMPORT_ERROR = None


@dataclass
class KernelVisitResult:
    success: bool
    payload: Optional[Dict[str, Any]] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None


@dataclass
class KernelHTMLResult:
    success: bool
    data: Optional[Dict[str, Any]] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None


class ResearchKernel:
    """Bounded page acquisition and session-state kernel."""

    def __init__(self):
        self._crawler: Optional[Crawler] = None
        self._browser: Optional[BrowserManager] = None
        self._browser_init_lock = asyncio.Lock()
        self._state = AgentRuntimeState()
        self._artifacts = ArtifactGraph()
        self._events = RuntimeEventStream()
        self._pressure = RuntimePressureController()
        self._last_pressure_snapshot = self._pressure.evaluate()
        self._artifact_session_node_id = self._artifacts.make_node_id("session", "runtime")
        self._ensure_artifact_session_node()

    @property
    def browser(self) -> Optional[BrowserManager]:
        return self._browser

    async def start(self) -> None:
        if self._crawler is None:
            if Crawler is None:
                raise RuntimeError(
                    "Crawler runtime is unavailable. Install optional dependencies from requirements.txt."
                ) from _CRAWLER_IMPORT_ERROR
            self._crawler = Crawler()
            self._emit_runtime_event(
                "kernel_start",
                {"crawler": True},
            )

    async def close(self) -> None:
        if self._crawler:
            await self._crawler.close()
        if self._browser:
            await self._browser.close()
        self._crawler = None
        self._browser = None
        self._state.clear()
        self._artifacts.clear()
        self._events.clear()
        self._pressure.clear()
        self._last_pressure_snapshot = self._pressure.snapshot()
        self._ensure_artifact_session_node()

    async def ensure_browser(self) -> Optional[BrowserManager]:
        if self._browser is not None:
            return self._browser
        async with self._browser_init_lock:
            if self._browser is None:
                if BrowserManager is None:
                    raise RuntimeError(
                        "Browser runtime is unavailable. Install optional dependencies from requirements.txt."
                    ) from _BROWSER_IMPORT_ERROR
                self._browser = BrowserManager()
                await self._browser.start()
                self._emit_runtime_event(
                    "browser_start",
                    {"browser": True},
                )
        return self._browser

    async def visit(
        self,
        url: str,
        use_browser: bool = False,
        auto_fallback: bool = True,
    ) -> KernelVisitResult:
        normalized_url = self.normalize_url(url)
        if not normalized_url:
            compact_input = self._compact_error_text(url, max_chars=240) or "empty"
            self._emit_runtime_event(
                "visit_invalid_url",
                {
                    "input_url": compact_input,
                },
            )
            return KernelVisitResult(
                success=False,
                error=f"invalid_url:{compact_input}",
            )
        self._state.mark_visited(normalized_url)
        pressure = self._refresh_pressure_state()
        limits = pressure.get("limits", {})
        pressure_level = str(pressure.get("level") or "normal")
        effective_auto_fallback = auto_fallback and bool(limits.get("allow_browser_fallback", True))
        self._emit_runtime_event(
            "visit_start",
            {
                "url": normalized_url,
                "use_browser": use_browser,
                "auto_fallback": auto_fallback,
                "effective_auto_fallback": effective_auto_fallback,
                "pressure_level": pressure_level,
            },
        )
        if auto_fallback and not effective_auto_fallback:
            self._emit_runtime_event(
                "pressure_fallback_suppressed",
                {
                    "url": normalized_url,
                    "pressure_level": pressure_level,
                    "reason": "browser_fallback_disabled",
                },
            )

        try:
            if use_browser:
                browser_result = await self.browser_fetch(normalized_url)
                visit_result = self._visit_from_browser_result(normalized_url, browser_result)
                self._emit_visit_event_outcome(normalized_url, visit_result)
                return visit_result

            crawler_result = await self.crawler_fetch(normalized_url)
            if crawler_result.success:
                visit_result = self._visit_from_crawl_result(normalized_url, crawler_result)
                self._emit_visit_event_outcome(normalized_url, visit_result)
                return visit_result

            if effective_auto_fallback and self.should_fallback_to_browser(crawler_result):
                logger.info("HTTP fetch failed for %s, trying browser fallback", normalized_url)
                self._emit_runtime_event(
                    "visit_fallback",
                    {
                        "url": normalized_url,
                        "reason": crawler_result.error or f"status={crawler_result.status_code}",
                    },
                )
                browser_result = await self.browser_fetch(normalized_url)
                if browser_result.error is None and browser_result.html:
                    visit_result = self._visit_from_browser_result(
                        normalized_url,
                        browser_result,
                        metadata_extra={
                            "fetch_mode": "browser_fallback",
                            "fallback_reason": crawler_result.error or f"status={crawler_result.status_code}",
                        },
                    )
                    if visit_result.success:
                        self._emit_visit_event_outcome(normalized_url, visit_result)
                        return visit_result
                failed_result = KernelVisitResult(
                    success=False,
                    error=(
                        f"HTTP失败：{self._compact_error_text(crawler_result.error) or crawler_result.status_code}; "
                        f"浏览器兜底失败：{self._compact_error_text(browser_result.error) or 'Empty content'}"
                    ),
                )
                self._emit_visit_event_outcome(normalized_url, failed_result)
                return failed_result

            failed_result = KernelVisitResult(
                success=False,
                error=self._compact_error_text(crawler_result.error) or "fetch_failed",
            )
            self._emit_visit_event_outcome(normalized_url, failed_result)
            return failed_result
        except Exception as exc:
            compact = self._compact_error_text(exc) or "visit_failed"
            compact_url = self._compact_error_text(normalized_url, max_chars=220) or "<empty>"
            logger.error("Kernel visit error for %s: %s", compact_url, compact)
            self._emit_runtime_event(
                "visit_exception",
                {
                    "url": normalized_url,
                    "error": compact,
                },
            )
            return KernelVisitResult(success=False, error=compact)

    async def fetch_html(
        self,
        url: str,
        use_browser: bool = False,
        auto_fallback: bool = True,
        max_chars: int = 80_000,
    ) -> KernelHTMLResult:
        normalized_url = self.normalize_url(url)
        if not normalized_url:
            compact_input = self._compact_error_text(url, max_chars=240) or "empty"
            self._emit_runtime_event(
                "fetch_html_invalid_url",
                {
                    "input_url": compact_input,
                },
            )
            return KernelHTMLResult(
                success=False,
                error=f"invalid_url:{compact_input}",
            )
        max_chars = max(1000, min(max_chars, 300000))
        pressure = self._refresh_pressure_state()
        limits = pressure.get("limits", {})
        pressure_level = str(pressure.get("level") or "normal")
        pressure_max_chars = self._safe_int(limits.get("fetch_html_max_chars"), default=max_chars)
        effective_max_chars = max(1000, min(max_chars, max(1000, pressure_max_chars)))
        effective_auto_fallback = auto_fallback and bool(limits.get("allow_browser_fallback", True))
        self._emit_runtime_event(
            "fetch_html_start",
            {
                "url": normalized_url,
                "use_browser": use_browser,
                "auto_fallback": auto_fallback,
                "effective_auto_fallback": effective_auto_fallback,
                "max_chars": max_chars,
                "effective_max_chars": effective_max_chars,
                "pressure_level": pressure_level,
            },
        )
        if effective_max_chars < max_chars:
            self._emit_runtime_event(
                "pressure_reduce_html_limit",
                {
                    "url": normalized_url,
                    "requested_max_chars": max_chars,
                    "effective_max_chars": effective_max_chars,
                    "pressure_level": pressure_level,
                },
            )
        if auto_fallback and not effective_auto_fallback:
            self._emit_runtime_event(
                "pressure_fallback_suppressed",
                {
                    "url": normalized_url,
                    "pressure_level": pressure_level,
                    "reason": "browser_fallback_disabled",
                },
            )

        html = ""
        title = ""
        fetch_mode = "http"
        final_url = normalized_url
        status_code: Optional[int] = None
        metadata: Dict[str, Any] = {}

        try:
            if use_browser:
                browser_result = await self.browser_fetch(normalized_url)
                if browser_result.error:
                    failed = KernelHTMLResult(
                        success=False,
                        error=self._compact_error_text(browser_result.error) or "browser_error",
                    )
                    self._emit_fetch_html_outcome(normalized_url, failed, fetch_mode="browser")
                    return failed
                html = browser_result.html or ""
                title = browser_result.title or ""
                final_url = browser_result.url or normalized_url
                fetch_mode = "browser"
                metadata = browser_result.metadata or {}
            else:
                crawler_result = await self.crawler_fetch(normalized_url)
                if crawler_result.success:
                    html = crawler_result.html or ""
                    status_code = crawler_result.status_code
                    final_url = crawler_result.url or normalized_url
                    fetch_mode = "http"
                    metadata = crawler_result.metadata or {}
                elif effective_auto_fallback and self.should_fallback_to_browser(crawler_result):
                    self._emit_runtime_event(
                        "fetch_html_fallback",
                        {
                            "url": normalized_url,
                            "reason": crawler_result.error or f"status={crawler_result.status_code}",
                        },
                    )
                    browser_result = await self.browser_fetch(normalized_url)
                    if browser_result.error:
                        failed = KernelHTMLResult(
                            success=False,
                            error=(
                                f"HTTP失败（{self._compact_error_text(crawler_result.error) or crawler_result.status_code}）；"
                                f"Browser失败（{self._compact_error_text(browser_result.error)}）"
                            ),
                        )
                        self._emit_fetch_html_outcome(normalized_url, failed, fetch_mode="browser_fallback")
                        return failed
                    html = browser_result.html or ""
                    title = browser_result.title or ""
                    final_url = browser_result.url or normalized_url
                    fetch_mode = "browser_fallback"
                    metadata = browser_result.metadata or {}
                else:
                    failed = KernelHTMLResult(
                        success=False,
                        error=self._compact_error_text(crawler_result.error) or f"status={crawler_result.status_code}",
                    )
                    self._emit_fetch_html_outcome(normalized_url, failed, fetch_mode="http")
                    return failed

            parser = self._build_parser().parse(html, final_url)
            extracted = parser.extract()
            if not title:
                title = extracted.title or ""
            dynamic_links_max = max(4, min(50, self._safe_int(limits.get("links_max"), default=50)))
            links = self._compact_link_items(extracted.links, max_items=dynamic_links_max, url_key="href")
            text_preview = (extracted.text or "")[:2000]
            html_truncated = len(html) > effective_max_chars
            result_payload = {
                "url": final_url,
                "title": title,
                "html": html[:effective_max_chars],
                "html_truncated": html_truncated,
                "html_chars": len(html),
                "text_preview": text_preview,
                "links": links,
                "fetch_mode": fetch_mode,
                "status_code": status_code,
            }
            result_metadata = {
                "fetch_mode": fetch_mode,
                "status_code": status_code,
                "login_wall": metadata.get("login_wall") if isinstance(metadata, dict) else None,
                "login_hint": metadata.get("login_hint") if isinstance(metadata, dict) else None,
                "pressure_level": pressure_level,
            }
            self._record_page_artifact(
                request_url=normalized_url,
                final_url=final_url,
                title=title,
                fetch_mode=fetch_mode,
                status_code=status_code,
                text_chars=len(extracted.text or ""),
                html_chars=len(html),
                links=links,
                metadata=result_metadata,
            )

            success_result = KernelHTMLResult(
                success=True,
                data=result_payload,
                metadata=result_metadata,
            )
            self._emit_fetch_html_outcome(
                normalized_url,
                success_result,
                fetch_mode=fetch_mode,
                status_code=status_code,
                html_chars=len(html),
            )
            return success_result
        except Exception as exc:
            compact = self._compact_error_text(exc) or "fetch_html_failed"
            compact_url = self._compact_error_text(normalized_url, max_chars=220) or "<empty>"
            logger.error("Kernel fetch_html error for %s: %s", compact_url, compact)
            self._emit_runtime_event(
                "fetch_html_exception",
                {
                    "url": normalized_url,
                    "error": compact,
                },
            )
            return KernelHTMLResult(success=False, error=compact)

    def has_page(self, url: str) -> bool:
        return self._state.has_page(self.normalize_url(url))

    def get_page(self, url: str) -> Optional[PageSnapshot]:
        return self._state.get_page(self.normalize_url(url))

    def iter_pages(self) -> List[PageSnapshot]:
        return list(self._state.iter_pages())

    def has_visited(self, url: str) -> bool:
        return self._state.has_visited(self.normalize_url(url))

    def get_visited_urls(self) -> List[str]:
        return self._state.get_visited_urls()

    def get_knowledge_base(self) -> List[Dict[str, Any]]:
        return self._state.get_knowledge_base()

    def get_runtime_state_stats(self) -> Dict[str, Any]:
        return self._state.get_stats()

    def get_artifact_graph_snapshot(
        self,
        *,
        node_limit: int = 80,
        edge_limit: int = 200,
        node_kind: Optional[str] = None,
    ) -> Dict[str, Any]:
        return self._artifacts.snapshot(
            node_limit=node_limit,
            edge_limit=edge_limit,
            node_kind=node_kind,
        )

    def get_artifact_graph_stats(self) -> Dict[str, Any]:
        return self._artifacts.get_stats()

    def get_runtime_events_snapshot(
        self,
        *,
        limit: int = 50,
        event_type: Optional[str] = None,
        source: Optional[str] = None,
        since_seq: Optional[int] = None,
    ) -> Dict[str, Any]:
        return self._events.snapshot(
            limit=limit,
            event_type=event_type,
            source=source,
            since_seq=since_seq,
        )

    def get_runtime_events_stats(self) -> Dict[str, Any]:
        return self._events.get_stats()

    def get_runtime_pressure_snapshot(self, refresh: bool = True) -> Dict[str, Any]:
        if refresh:
            return self._refresh_pressure_state()
        return dict(self._last_pressure_snapshot)

    def get_runtime_pressure_stats(self) -> Dict[str, Any]:
        snapshot = self.get_runtime_pressure_snapshot(refresh=False)
        return {
            "level": snapshot.get("level"),
            "changed": snapshot.get("changed"),
            "memory": snapshot.get("memory"),
            "errors": snapshot.get("errors"),
            "limits": snapshot.get("limits"),
        }

    def get_budget_telemetry_snapshot(self, refresh: bool = True) -> Dict[str, Any]:
        pressure = self.get_runtime_pressure_snapshot(refresh=refresh)
        runtime_state = self.get_runtime_state_stats()
        runtime_events = self.get_runtime_events_stats()
        artifact_graph = self.get_artifact_graph_stats()

        state_budget = runtime_state.get("budget", {}) if isinstance(runtime_state.get("budget"), dict) else {}
        artifact_budget = artifact_graph.get("budget", {}) if isinstance(artifact_graph.get("budget"), dict) else {}

        utilization = {
            "state_pages_ratio": self._safe_ratio(
                runtime_state.get("pages"),
                state_budget.get("max_pages"),
            ),
            "state_visited_ratio": self._safe_ratio(
                runtime_state.get("visited_urls"),
                state_budget.get("max_visited_urls"),
            ),
            "state_content_ratio": self._safe_ratio(
                runtime_state.get("total_content_chars"),
                state_budget.get("max_total_content_chars"),
            ),
            "event_store_ratio": self._safe_ratio(
                runtime_events.get("store_size"),
                runtime_events.get("max_events"),
            ),
            "artifact_nodes_ratio": self._safe_ratio(
                artifact_graph.get("nodes"),
                artifact_budget.get("max_nodes"),
            ),
            "artifact_edges_ratio": self._safe_ratio(
                artifact_graph.get("edges"),
                artifact_budget.get("max_edges"),
            ),
        }

        alerts: List[str] = []
        if self._safe_int(runtime_events.get("dropped_events"), default=0) > 0:
            alerts.append("runtime_events_dropped")

        state_counters = runtime_state.get("counters", {}) if isinstance(runtime_state.get("counters"), dict) else {}
        if self._safe_int(state_counters.get("pages_evicted"), default=0) > 0:
            alerts.append("runtime_state_pages_evicted")
        if self._safe_int(state_counters.get("content_truncated"), default=0) > 0:
            alerts.append("runtime_state_content_truncated")

        artifact_counters = artifact_graph.get("counters", {}) if isinstance(artifact_graph.get("counters"), dict) else {}
        if self._safe_int(artifact_counters.get("nodes_evicted"), default=0) > 0:
            alerts.append("artifact_nodes_evicted")
        if self._safe_int(artifact_counters.get("edges_evicted_total"), default=0) > 0:
            alerts.append("artifact_edges_evicted")

        pressure_level = str(pressure.get("level") or "normal")
        if pressure_level in {"high", "critical"}:
            alerts.append(f"pressure_{pressure_level}")

        max_utilization = max(utilization.values()) if utilization else 0.0
        if max_utilization >= 0.9:
            alerts.append("budget_near_capacity")
        health_score = max(0, min(100, int(round((1.0 - max_utilization) * 100))))

        return {
            "health_score": health_score,
            "pressure_level": pressure_level,
            "alerts": alerts,
            "utilization": utilization,
            "runtime_state": runtime_state,
            "runtime_events": runtime_events,
            "artifact_graph": artifact_graph,
            "runtime_pressure": pressure,
        }

    def normalize_url(self, url: str) -> str:
        normalized = str(url or "").strip()
        if not normalized:
            return ""

        parsed = urlparse(normalized)
        if parsed.scheme in {"http", "https"}:
            return normalized if parsed.netloc else ""

        if normalized.startswith("//"):
            candidate = f"https:{normalized}"
            parsed_candidate = urlparse(candidate)
            return candidate if parsed_candidate.netloc else ""

        if normalized.startswith(("/", "?", "#")):
            return ""

        if normalized.startswith("www."):
            candidate = f"https://{normalized}"
            parsed_candidate = urlparse(candidate)
            return candidate if parsed_candidate.netloc else ""

        hostname = normalized.split("/", 1)[0].split("?", 1)[0].split("#", 1)[0]
        if "." in hostname or hostname == "localhost":
            candidate = f"https://{normalized}"
            parsed_candidate = urlparse(candidate)
            return candidate if parsed_candidate.netloc else ""

        return ""

    def _build_parser(self):
        if Parser is None:
            raise RuntimeError(
                "HTML parser runtime is unavailable. Install optional dependencies from requirements.txt."
            ) from _PARSER_IMPORT_ERROR
        return Parser()

    async def crawler_fetch(self, url: str) -> CrawlResult:
        if self._crawler is None:
            await self.start()
        assert self._crawler is not None
        return await self._crawler.fetch_with_retry(url)

    async def browser_fetch(self, url: str) -> BrowserResult:
        browser = await self.ensure_browser()
        assert browser is not None
        result = await browser.fetch(url)
        if result.error is None and result.cookies and self._crawler is not None:
            try:
                injected = await self._crawler.seed_cookies(result.url or url, result.cookies)
                if injected > 0:
                    logger.info("已同步 %s 个浏览器 cookies 到 HTTP 会话: %s", injected, result.url or url)
            except Exception as exc:
                logger.debug("浏览器 cookie 同步失败（忽略） %s: %s", url, exc)
        return result

    def should_fallback_to_browser(self, result: CrawlResult) -> bool:
        if result.success:
            return False

        if result.status_code in {
            0, 401, 403, 404, 406, 408, 409, 410, 412, 418, 421, 425,
            426, 429, 451, 500, 502, 503, 504, 520, 521, 522, 523, 524, 525,
        }:
            return True

        error_text = (result.error or "").lower()
        fallback_keywords = [
            "timeout", "ssl", "cloudflare", "captcha", "forbidden", "blocked",
            "connection", "reset", "refused", "challenge", "javascript",
        ]
        return any(keyword in error_text for keyword in fallback_keywords)

    @staticmethod
    def _compact_error_text(error: Any, *, max_chars: int = 320) -> str:
        text = str(error or "").strip()
        if not text:
            return ""
        first_line = text.splitlines()[0].strip()
        if len(first_line) > max_chars:
            return first_line[: max_chars - 3] + "..."
        return first_line

    def _visit_from_browser_result(
        self,
        url: str,
        result: BrowserResult,
        metadata_extra: Optional[Dict[str, Any]] = None,
    ) -> KernelVisitResult:
        if result.error is not None or not result.html:
            return KernelVisitResult(
                success=False,
                error=self._compact_error_text(result.error) or "Empty content",
            )

        parser = self._build_parser().parse(result.html, url)
        extracted = parser.extract()
        compaction = self._current_compaction_limits()
        payload = self._compact_extracted_data(
            extracted,
            max_text_chars=self._safe_int(compaction.get("text_max_chars"), default=20_000),
            max_links=self._safe_int(compaction.get("links_max"), default=50),
            max_images=self._safe_int(compaction.get("images_max"), default=20),
            max_metadata_items=self._safe_int(compaction.get("metadata_items"), default=40),
            max_metadata_depth=self._safe_int(compaction.get("metadata_depth"), default=3),
            max_metadata_string_chars=self._safe_int(compaction.get("metadata_string_chars"), default=500),
        )
        self._remember_page(url, payload)

        metadata = {
            "url": result.url,
            "title": result.title,
            "fetch_mode": "browser",
            "login_wall": (result.metadata or {}).get("login_wall"),
            "login_hint": (result.metadata or {}).get("login_hint"),
            "auth": (result.metadata or {}).get("auth"),
            "html_truncated": (result.metadata or {}).get("html_truncated"),
            "html_chars": (result.metadata or {}).get("html_chars"),
            "pressure_level": self._current_pressure_level(),
        }
        if metadata_extra:
            metadata.update(metadata_extra)
        self._record_page_artifact(
            request_url=url,
            final_url=result.url or url,
            title=str(payload.get("title") or result.title or ""),
            fetch_mode=str(metadata.get("fetch_mode") or "browser"),
            status_code=None,
            text_chars=self._safe_int(payload.get("text_chars"), default=0),
            html_chars=result.metadata.get("html_chars") if isinstance(result.metadata, dict) else None,
            links=payload.get("links", []),
            metadata=metadata,
        )
        return KernelVisitResult(success=True, payload=payload, metadata=metadata)

    def _visit_from_crawl_result(self, url: str, result: CrawlResult) -> KernelVisitResult:
        parser = self._build_parser().parse(result.html, url)
        extracted = parser.extract()
        compaction = self._current_compaction_limits()
        payload = self._compact_extracted_data(
            extracted,
            max_text_chars=self._safe_int(compaction.get("text_max_chars"), default=20_000),
            max_links=self._safe_int(compaction.get("links_max"), default=50),
            max_images=self._safe_int(compaction.get("images_max"), default=20),
            max_metadata_items=self._safe_int(compaction.get("metadata_items"), default=40),
            max_metadata_depth=self._safe_int(compaction.get("metadata_depth"), default=3),
            max_metadata_string_chars=self._safe_int(compaction.get("metadata_string_chars"), default=500),
        )
        self._remember_page(url, payload)
        metadata = {
            "status_code": result.status_code,
            "response_time": result.response_time,
            "fetch_mode": "http",
            "body_truncated": (result.metadata or {}).get("body_truncated"),
            "body_bytes": (result.metadata or {}).get("body_bytes"),
            "body_limit_bytes": (result.metadata or {}).get("body_limit_bytes"),
            "pressure_level": self._current_pressure_level(),
        }
        self._record_page_artifact(
            request_url=url,
            final_url=result.url or url,
            title=str(payload.get("title") or ""),
            fetch_mode="http",
            status_code=result.status_code,
            text_chars=self._safe_int(payload.get("text_chars"), default=0),
            html_chars=self._safe_int(
                (result.metadata or {}).get("body_bytes"),
                default=len(result.html or ""),
            ),
            links=payload.get("links", []),
            metadata=metadata,
        )

        return KernelVisitResult(
            success=True,
            payload=payload,
            metadata=metadata,
        )

    def _compact_value(
        self,
        value: Any,
        *,
        max_depth: int = 3,
        max_items: int = 40,
        max_string_chars: int = 500,
        depth: int = 0,
    ) -> Any:
        if depth >= max_depth:
            text = "" if value is None else str(value)
            return text[:max_string_chars]

        if isinstance(value, str):
            return value[:max_string_chars]

        if isinstance(value, (int, float, bool)) or value is None:
            return value

        if isinstance(value, list):
            return [
                self._compact_value(
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
                compact[str(key)] = self._compact_value(
                    item,
                    max_depth=max_depth,
                    max_items=max_items,
                    max_string_chars=max_string_chars,
                    depth=depth + 1,
                )
            return compact

        return str(value)[:max_string_chars]

    def _compact_link_items(
        self,
        items: List[Dict[str, Any]],
        *,
        max_items: int,
        url_key: str = "href",
        href_chars: int = 500,
        text_chars: int = 160,
    ) -> List[Dict[str, str]]:
        compact_items: List[Dict[str, str]] = []
        for item in items[:max_items]:
            if not isinstance(item, dict):
                continue
            url_value = str(item.get(url_key) or "")[:href_chars]
            if not url_value:
                continue
            compact_item = {url_key: url_value}
            text_value = item.get("text") or item.get("alt") or item.get("title") or ""
            text_value = str(text_value)[:text_chars]
            if text_value:
                compact_item["text"] = text_value
            compact_items.append(compact_item)
        return compact_items

    def _compact_extracted_data(
        self,
        extracted: ExtractedData,
        *,
        max_text_chars: int = 20_000,
        max_links: int = 50,
        max_images: int = 20,
        max_metadata_items: int = 40,
        max_metadata_depth: int = 3,
        max_metadata_string_chars: int = 500,
    ) -> Dict[str, Any]:
        text = extracted.text or ""
        return {
            "url": extracted.url,
            "title": extracted.title,
            "text": text[:max_text_chars],
            "text_chars": len(text),
            "text_truncated": len(text) > max_text_chars,
            "links": self._compact_link_items(extracted.links, max_items=max_links, url_key="href"),
            "images": self._compact_link_items(extracted.images, max_items=max_images, url_key="src"),
            "metadata": self._compact_value(
                extracted.metadata,
                max_depth=max_metadata_depth,
                max_items=max_metadata_items,
                max_string_chars=max_metadata_string_chars,
            ),
            "structured": self._compact_value(
                extracted.structured,
                max_depth=max_metadata_depth,
                max_items=max_metadata_items,
                max_string_chars=max_metadata_string_chars,
            ),
        }

    def _remember_page(self, url: str, payload: Dict[str, Any]) -> Optional[PageSnapshot]:
        if not url:
            return None
        return self._state.store_page(
            url=url,
            title=str(payload.get("title", "")),
            content=str(payload.get("text", "")),
            content_chars=payload.get("text_chars"),
            links=payload.get("links", []) if isinstance(payload.get("links"), list) else [],
            extracted_info=payload.get("metadata", {}) if isinstance(payload.get("metadata"), dict) else {},
        )

    def _ensure_artifact_session_node(self) -> None:
        self._artifacts.upsert_node(
            node_id=self._artifact_session_node_id,
            kind="session",
            label="runtime-session",
            attrs={"scope": "web-rooter"},
        )

    def _record_page_artifact(
        self,
        *,
        request_url: str,
        final_url: str,
        title: str,
        fetch_mode: str,
        status_code: Optional[int],
        text_chars: Optional[int],
        html_chars: Optional[int],
        links: Optional[List[Dict[str, Any]]],
        metadata: Optional[Dict[str, Any]],
    ) -> None:
        try:
            self._ensure_artifact_session_node()
            normalized_request = self.normalize_url(request_url)
            normalized_final = self.normalize_url(final_url or request_url)

            page_node_id = self._build_url_node_id("page", normalized_final)
            page_attrs: Dict[str, Any] = {
                "url": normalized_final,
                "title": title,
                "fetch_mode": fetch_mode,
                "status_code": status_code,
                "text_chars": text_chars,
                "html_chars": html_chars,
                "links": len(links or []),
            }
            meta_flags = self._select_metadata_flags(metadata)
            if meta_flags:
                page_attrs["flags"] = meta_flags
            self._artifacts.upsert_node(
                node_id=page_node_id,
                kind="page",
                label=title or normalized_final,
                attrs=page_attrs,
            )

            self._artifacts.upsert_edge(
                source=self._artifact_session_node_id,
                target=page_node_id,
                relation="visited",
                attrs={"mode": fetch_mode},
            )

            if normalized_request and normalized_request != normalized_final:
                request_node_id = self._build_url_node_id("request", normalized_request)
                self._artifacts.upsert_node(
                    node_id=request_node_id,
                    kind="request",
                    label=normalized_request,
                    attrs={"url": normalized_request},
                )
                self._artifacts.upsert_edge(
                    source=request_node_id,
                    target=page_node_id,
                    relation="resolved_to",
                    attrs={"mode": fetch_mode},
                )

            self._record_domain_relation(page_node_id, normalized_final)

            for item in (links or [])[:8]:
                if not isinstance(item, dict):
                    continue
                href = str(item.get("href") or "").strip()
                if not href.startswith(("http://", "https://")):
                    continue
                link_node_id = self._build_url_node_id("url", href)
                self._artifacts.upsert_node(
                    node_id=link_node_id,
                    kind="url",
                    label=href,
                    attrs={"url": href},
                )
                self._artifacts.upsert_edge(
                    source=page_node_id,
                    target=link_node_id,
                    relation="links_to",
                    attrs={"anchor": str(item.get("text") or "")[:120]},
                )
        except Exception as exc:
            logger.debug("Record artifact failed for %s: %s", final_url, exc)

    def _record_domain_relation(self, page_node_id: str, url: str) -> None:
        host = (urlparse(url).hostname or "").strip().lower()
        if not host:
            return
        domain_node_id = self._artifacts.make_node_id("domain", host)
        self._artifacts.upsert_node(
            node_id=domain_node_id,
            kind="domain",
            label=host,
            attrs={"host": host},
        )
        self._artifacts.upsert_edge(
            source=page_node_id,
            target=domain_node_id,
            relation="hosted_on",
            attrs={},
        )

    def _build_url_node_id(self, kind: str, url: str) -> str:
        return self._artifacts.make_node_id(kind, url)

    def _select_metadata_flags(self, metadata: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        if not isinstance(metadata, dict):
            return {}
        keys = [
            "fetch_mode",
            "status_code",
            "login_wall",
            "login_hint",
            "fallback_reason",
            "body_truncated",
            "html_truncated",
            "body_limit_bytes",
        ]
        flags: Dict[str, Any] = {}
        for key in keys:
            if key in metadata and metadata.get(key) is not None:
                flags[key] = metadata.get(key)
        return flags

    def _safe_int(self, value: Any, default: int = 0) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return int(default)

    def _safe_ratio(self, value: Any, total: Any) -> float:
        numerator = self._safe_int(value, default=0)
        denominator = max(1, self._safe_int(total, default=1))
        return round(max(0.0, min(float(numerator) / float(denominator), 5.0)), 4)

    def _safe_bool(self, value: Any, default: bool = False) -> bool:
        if isinstance(value, bool):
            return value
        if value is None:
            return default
        text = str(value).strip().lower()
        if text in {"1", "true", "yes", "on"}:
            return True
        if text in {"0", "false", "no", "off"}:
            return False
        return default

    def _current_pressure_level(self) -> str:
        return str(self._last_pressure_snapshot.get("level") or "normal")

    def _current_compaction_limits(self) -> Dict[str, Any]:
        limits = self._last_pressure_snapshot.get("limits")
        if isinstance(limits, dict):
            return limits
        return self._pressure.get_current_limits()

    def _refresh_pressure_state(self) -> Dict[str, Any]:
        snapshot = self._pressure.evaluate()
        self._last_pressure_snapshot = snapshot
        if snapshot.get("changed"):
            self._emit_runtime_event(
                "pressure_level_changed",
                {
                    "previous_level": snapshot.get("previous_level"),
                    "level": snapshot.get("level"),
                    "reason": snapshot.get("reason"),
                    "rss_mb": (snapshot.get("memory") or {}).get("rss_mb") if isinstance(snapshot.get("memory"), dict) else None,
                },
            )
        return snapshot

    def _record_runtime_outcome(self, success: bool) -> None:
        previous = self._current_pressure_level()
        self._pressure.record_outcome(success)
        snapshot = self._pressure.evaluate()
        self._last_pressure_snapshot = snapshot
        if snapshot.get("changed"):
            self._emit_runtime_event(
                "pressure_level_changed",
                {
                    "previous_level": previous,
                    "level": snapshot.get("level"),
                    "reason": "outcome_update",
                    "error_rate": (snapshot.get("errors") or {}).get("error_rate") if isinstance(snapshot.get("errors"), dict) else None,
                },
            )

    def _emit_runtime_event(self, event_type: str, payload: Optional[Dict[str, Any]] = None) -> None:
        try:
            self._events.record(
                event_type=event_type,
                source="research_kernel",
                payload=payload or {},
            )
        except Exception as exc:
            logger.debug("Runtime event emit failed (%s): %s", event_type, exc)

    def _emit_visit_event_outcome(self, url: str, result: KernelVisitResult) -> None:
        self._record_runtime_outcome(result.success)
        payload = {
            "url": url,
            "success": result.success,
            "error": result.error,
            "fetch_mode": (result.metadata or {}).get("fetch_mode"),
            "status_code": (result.metadata or {}).get("status_code"),
            "pressure_level": self._current_pressure_level(),
        }
        self._emit_runtime_event("visit_complete", payload)

    def _emit_fetch_html_outcome(
        self,
        url: str,
        result: KernelHTMLResult,
        *,
        fetch_mode: str,
        status_code: Optional[int] = None,
        html_chars: Optional[int] = None,
    ) -> None:
        self._record_runtime_outcome(result.success)
        payload = {
            "url": url,
            "success": result.success,
            "error": result.error,
            "fetch_mode": fetch_mode,
            "status_code": status_code,
            "html_chars": html_chars,
            "pressure_level": self._current_pressure_level(),
        }
        self._emit_runtime_event("fetch_html_complete", payload)

"""
MindSearch 风格研究管线（Python 轻量实现）。

设计目标：
- 接近 MindSearch 的“规划 -> 多节点搜索 -> 图增量扩展 -> 汇总”流程
- 与现有 DeepSearchEngine 无缝复用（不重复造轮子）
- 输出可被 CLI/MCP 直接消费的图结构 + 引用映射
"""
from __future__ import annotations

import asyncio
import inspect
import logging
import os
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Awaitable, Callable, Dict, List, Optional, Set, Tuple, Union

from core.citation import build_comparison_summary, build_web_citations, format_reference_block
from core.global_context import get_global_deep_context
from core.postprocess import PostProcessContext, run_post_processors
from core.result_queue import ResultQueue
from core.search.advanced import DeepSearchEngine
from core.search.research_planner import is_chinese_text, resolve_research_planner

logger = logging.getLogger(__name__)


EventCallback = Optional[Callable[[str, Dict[str, Any]], Union[Awaitable[None], None]]]


@dataclass
class MindSearchNode:
    """MindSearch 图节点。"""

    id: str
    query: str
    depth: int
    parent_id: Optional[str] = None
    rationale: str = ""
    status: str = "pending"  # pending/running/completed/failed
    result_count: int = 0
    citations: List[Dict[str, Any]] = field(default_factory=list)
    urls: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    search_summary: str = ""
    started_at: Optional[str] = None
    completed_at: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "query": self.query,
            "depth": self.depth,
            "parent_id": self.parent_id,
            "rationale": self.rationale,
            "status": self.status,
            "result_count": self.result_count,
            "citations": self.citations,
            "urls": self.urls,
            "errors": self.errors,
            "search_summary": self.search_summary,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
        }


class MindSearchPipeline:
    """MindSearch 风格研究执行器。"""

    def __init__(
        self,
        max_turns: int = 3,
        max_branches: int = 4,
        num_results: int = 8,
        crawl_top: int = 1,
        use_english: bool = False,
        channel_profiles: Optional[List[str]] = None,
        max_nodes: Optional[int] = None,
        planner_name: Optional[str] = None,
        strict_expand: Optional[bool] = None,
        pressure_level: Optional[str] = None,
        pressure_limits: Optional[Dict[str, Any]] = None,
    ):
        self.max_turns = max(1, max_turns)
        self.max_branches = max(1, max_branches)
        self.num_results = max(3, num_results)
        self.crawl_top = max(0, crawl_top)
        self.use_english = use_english
        self.channel_profiles = list(channel_profiles or [])
        self.max_nodes = max_nodes or int(os.getenv("WEB_ROOTER_MINDSEARCH_MAX_NODES", "14") or 14)
        self.max_stream_queue_size = max(
            1,
            int(os.getenv("WEB_ROOTER_MINDSEARCH_STREAM_QUEUE_SIZE", "128") or 128),
        )
        self.planner_name = (planner_name or "").strip() or None
        strict_env = str(os.getenv("WEB_ROOTER_MINDSEARCH_STRICT", "0") or "0").strip().lower()
        strict_default = strict_env in {"1", "true", "yes", "on"}
        self.strict_expand = strict_default if strict_expand is None else bool(strict_expand)
        self.pressure_level = self._normalize_pressure_level(pressure_level)
        self.pressure_limits = pressure_limits if isinstance(pressure_limits, dict) else {}
        self._apply_pressure_profile()
        self._planner = resolve_research_planner(self.planner_name)

        self._nodes: Dict[str, MindSearchNode] = {}
        self._edges: List[Dict[str, str]] = []
        self._seen_queries: Set[str] = set()

    async def run(self, query: str, event_callback: EventCallback = None) -> Dict[str, Any]:
        """
        执行 MindSearch 风格研究。
        """
        root = self._add_node(
            query=query.strip(),
            depth=0,
            parent_id=None,
            rationale="root-question",
        )
        await self._emit(event_callback, "node_added", root.to_dict())

        # 第一层规划（MindSearch decomposition）
        seeds = self._planner.decompose_seed_queries(
            query=query,
            max_branches=self.max_branches,
            is_chinese=is_chinese_text(query),
        )
        if not seeds:
            seeds = self._decompose_seed_queries(query, depth=0)
        level_nodes: Dict[int, List[str]] = {0: [root.id]}
        if self.max_turns > 1:
            level_nodes[1] = []
            for seed_query, seed_reason in seeds:
                if len(self._nodes) >= self.max_nodes:
                    break
                child = self._add_node(
                    query=seed_query,
                    depth=1,
                    parent_id=root.id,
                    rationale=seed_reason,
                )
                level_nodes[1].append(child.id)
                await self._emit(event_callback, "node_added", child.to_dict())

        deep_search = DeepSearchEngine()
        try:
            for depth in range(0, self.max_turns):
                node_ids = level_nodes.get(depth, [])
                if not node_ids:
                    continue
                await self._emit(
                    event_callback,
                    "level_start",
                    {"depth": depth, "node_count": len(node_ids)},
                )

                # 并行执行当前层
                await asyncio.gather(
                    *[
                        self._execute_node(
                            node_id=node_id,
                            deep_search=deep_search,
                            event_callback=event_callback,
                        )
                        for node_id in node_ids
                    ],
                    return_exceptions=True,
                )

                # 生成下一层 follow-up
                next_depth = depth + 1
                if next_depth >= self.max_turns:
                    continue
                level_nodes.setdefault(next_depth, [])
                for node_id in node_ids:
                    node = self._nodes[node_id]
                    if node.status != "completed":
                        continue
                    if len(self._nodes) >= self.max_nodes:
                        break
                    node_payload = node.to_dict()
                    should_expand = self._planner.should_expand(
                        node=node_payload,
                        max_turns=self.max_turns,
                        strict=self.strict_expand,
                    )
                    if not should_expand:
                        should_expand = self._should_expand(node)
                    if not should_expand:
                        continue
                    followups = self._planner.generate_followup_queries(
                        node=node_payload,
                        max_branches=self.max_branches,
                        is_chinese=is_chinese_text(node.query),
                    )
                    if not followups:
                        followups = self._generate_followup_queries(node)
                    for follow_query, follow_reason in followups:
                        if len(self._nodes) >= self.max_nodes:
                            break
                        child = self._add_node(
                            query=follow_query,
                            depth=next_depth,
                            parent_id=node.id,
                            rationale=follow_reason,
                        )
                        level_nodes[next_depth].append(child.id)
                        await self._emit(event_callback, "node_added", child.to_dict())

                await self._emit(
                    event_callback,
                    "level_complete",
                    {"depth": depth, "executed": len(node_ids)},
                )
        finally:
            await deep_search.close()

        payload = self._build_payload(query=query)
        payload["planner"] = {
            "name": str(getattr(self._planner, "name", "heuristic")),
            "strict_expand": self.strict_expand,
        }
        payload["runtime_profile"] = {
            "pressure_level": self.pressure_level,
            "max_turns": self.max_turns,
            "max_branches": self.max_branches,
            "max_nodes": self.max_nodes,
            "num_results": self.num_results,
            "crawl_top": self.crawl_top,
            "stream_queue_max_size": self.max_stream_queue_size,
        }
        payload, post_report = run_post_processors(
            payload,
            PostProcessContext(
                query=query,
                mode="mindsearch",
                metadata={
                    "max_turns": self.max_turns,
                    "max_nodes": self.max_nodes,
                    "planner": str(getattr(self._planner, "name", "heuristic")),
                },
            ),
        )
        payload["postprocess"] = post_report

        event = get_global_deep_context().record(
            event_type="mindsearch_complete",
            source="mindsearch_pipeline",
            payload={
                "query": query,
                "total_nodes": payload.get("stats", {}).get("total_nodes", 0),
                "completed_nodes": payload.get("stats", {}).get("completed_nodes", 0),
                "total_results": payload.get("total_results", 0),
                "planner": str(getattr(self._planner, "name", "heuristic")),
                "top_urls": [item.get("url") for item in payload.get("results", [])[:8]],
            },
        )
        payload["global_context_event_id"] = event.get("id")
        return payload

    def _normalize_pressure_level(self, level: Optional[str]) -> str:
        normalized = str(level or "").strip().lower()
        if normalized in {"elevated", "high", "critical"}:
            return normalized
        return "normal"

    def _apply_pressure_profile(self) -> None:
        level = self.pressure_level
        if level == "elevated":
            self.max_branches = min(self.max_branches, 3)
            self.max_nodes = min(self.max_nodes, 12)
            self.num_results = min(self.num_results, 6)
            self.crawl_top = min(self.crawl_top, 1)
            self.max_stream_queue_size = min(self.max_stream_queue_size, 96)
        elif level == "high":
            self.max_turns = min(self.max_turns, 2)
            self.max_branches = min(self.max_branches, 3)
            self.max_nodes = min(self.max_nodes, 9)
            self.num_results = min(self.num_results, 5)
            self.crawl_top = min(self.crawl_top, 1)
            self.max_stream_queue_size = min(self.max_stream_queue_size, 64)
            self.strict_expand = False
        elif level == "critical":
            self.max_turns = min(self.max_turns, 2)
            self.max_branches = min(self.max_branches, 2)
            self.max_nodes = min(self.max_nodes, 6)
            self.num_results = min(self.num_results, 3)
            self.crawl_top = 0
            self.max_stream_queue_size = min(self.max_stream_queue_size, 32)
            self.strict_expand = False

        if self._safe_bool(self.pressure_limits.get("allow_browser_fallback"), default=True) is False:
            self.crawl_top = 0

        links_max = self._safe_int(self.pressure_limits.get("links_max"), default=0)
        if links_max > 0:
            derived = max(3, min(8, links_max))
            self.num_results = min(self.num_results, derived)

    @staticmethod
    def _safe_int(value: Any, default: int = 0) -> int:
        try:
            return int(value)
        except Exception:
            return default

    @staticmethod
    def _safe_bool(value: Any, default: bool = False) -> bool:
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

    async def run_stream(self, query: str):
        """
        流式执行，输出 MindSearch 风格事件。
        """
        queue = ResultQueue(
            maxsize=self.max_stream_queue_size,
            overflow_strategy="drop_oldest",
        )

        async def _emit(event: str, data: Dict[str, Any]) -> None:
            item = {"event": event, "data": data}
            queue.put_nowait(item, item_type="event")

        task = asyncio.create_task(self.run(query, event_callback=_emit))
        try:
            while True:
                if task.done() and queue.is_empty():
                    break
                item = await queue.get(timeout=0.6)
                if item is not None:
                    yield item.data
            result = await task
            queue_stats = queue.get_stats()
            result.setdefault("stream", {})
            result["stream"].update(
                {
                    "queue_max_size": self.max_stream_queue_size,
                    "dropped_events": queue_stats["items_dropped"],
                }
            )
            yield {"event": "complete", "data": result}
        except Exception:
            if not task.done():
                task.cancel()
            raise

    def _add_node(self, query: str, depth: int, parent_id: Optional[str], rationale: str) -> MindSearchNode:
        normalized = self._normalize_query(query)
        if normalized in self._seen_queries:
            # 命中重复则不重复创建；返回已存在节点
            for node in self._nodes.values():
                if self._normalize_query(node.query) == normalized:
                    if parent_id and node.parent_id is None:
                        node.parent_id = parent_id
                    return node

        node = MindSearchNode(
            id=str(uuid.uuid4()),
            query=query.strip(),
            depth=depth,
            parent_id=parent_id,
            rationale=rationale,
        )
        self._nodes[node.id] = node
        self._seen_queries.add(normalized)
        if parent_id:
            self._edges.append({"from": parent_id, "to": node.id})
        return node

    async def _execute_node(
        self,
        node_id: str,
        deep_search: DeepSearchEngine,
        event_callback: EventCallback = None,
    ) -> None:
        node = self._nodes[node_id]
        node.status = "running"
        node.started_at = datetime.now().isoformat()
        await self._emit(event_callback, "node_start", {"id": node.id, "query": node.query, "depth": node.depth})

        try:
            response = await deep_search.deep_search(
                node.query,
                num_results=self.num_results,
                use_english=self.use_english,
                crawl_top=self.crawl_top,
                query_variants=1,
                channel_profiles=self.channel_profiles or None,
            )
            results = response.get("results", []) if isinstance(response.get("results"), list) else []
            citations = response.get("citations", []) if isinstance(response.get("citations"), list) else []
            errors = response.get("errors", []) if isinstance(response.get("errors"), list) else []

            node.result_count = len(results)
            node.citations = citations[:40]
            node.urls = [item.get("url") for item in results[:15] if isinstance(item, dict) and item.get("url")]
            node.errors = [str(e) for e in errors[:10]]
            node.search_summary = str(response.get("search_summary", "") or "")
            node.status = "completed"
        except Exception as exc:
            node.status = "failed"
            node.errors.append(str(exc))
            logger.warning("MindSearch node failed: %s (%s)", node.query, exc)
        finally:
            node.completed_at = datetime.now().isoformat()
            await self._emit(
                event_callback,
                "node_complete",
                {
                    "id": node.id,
                    "query": node.query,
                    "status": node.status,
                    "result_count": node.result_count,
                    "errors": node.errors[:3],
                },
            )
            capture_nodes = str(os.getenv("WEB_ROOTER_CONTEXT_CAPTURE_MINDSEARCH_NODES", "1") or "1").strip().lower()
            if capture_nodes in {"1", "true", "yes", "on"}:
                try:
                    get_global_deep_context().record(
                        event_type="mindsearch_node_complete",
                        source="mindsearch_pipeline",
                        payload={
                            "id": node.id,
                            "query": node.query,
                            "depth": node.depth,
                            "status": node.status,
                            "result_count": node.result_count,
                            "errors": node.errors[:3],
                            "top_urls": node.urls[:5],
                        },
                    )
                except Exception as exc:
                    logger.debug("mindsearch node context record failed: %s", exc)

    def _should_expand(self, node: MindSearchNode) -> bool:
        # 命中少或错误多则扩展（强化 MindSearch 的“补充搜索”）
        if node.depth + 1 >= self.max_turns:
            return False
        if node.status != "completed":
            return False
        if node.result_count <= 2:
            return True
        if node.errors:
            return True
        return False

    def _decompose_seed_queries(self, query: str, depth: int) -> List[Tuple[str, str]]:
        is_cn = self._is_chinese(query)
        if is_cn:
            templates = [
                ("{q} 最新进展", "latest-updates"),
                ("{q} 核心概念与原理", "core-concepts"),
                ("{q} 代表性案例", "representative-cases"),
                ("{q} 常见争议与反例", "controversies"),
                ("{q} 学术论文 与 引用", "academic-links"),
            ]
        else:
            templates = [
                ("{q} latest updates", "latest-updates"),
                ("{q} core concepts", "core-concepts"),
                ("{q} representative case studies", "representative-cases"),
                ("{q} limitations and controversy", "controversies"),
                ("{q} papers and citations", "academic-links"),
            ]

        pairs = []
        for template, reason in templates[: self.max_branches]:
            pairs.append((template.format(q=query).strip(), reason))
        return pairs

    def _generate_followup_queries(self, node: MindSearchNode) -> List[Tuple[str, str]]:
        followups: List[Tuple[str, str]] = []
        if self._is_chinese(node.query):
            fallback_templates = [
                f"{node.query} 关键数据对比",
                f"{node.query} 社区讨论与评测",
                f"{node.query} 实操指南",
            ]
        else:
            fallback_templates = [
                f"{node.query} benchmark comparison",
                f"{node.query} community discussion",
                f"{node.query} practical tutorial",
            ]

        for q in fallback_templates[: self.max_branches]:
            followups.append((q, "followup-expansion"))
        return followups

    def _build_payload(self, query: str) -> Dict[str, Any]:
        node_dict = {node_id: node.to_dict() for node_id, node in self._nodes.items()}
        completed = [n for n in self._nodes.values() if n.status == "completed"]
        failed = [n for n in self._nodes.values() if n.status == "failed"]

        # 聚合结果与引用
        merged_results: List[Dict[str, Any]] = []
        merged_urls: Set[str] = set()
        for node in completed:
            for citation in node.citations:
                url = citation.get("url")
                if not url or url in merged_urls:
                    continue
                if self._is_low_signal_url(url):
                    continue
                merged_urls.add(url)
                merged_results.append(
                    {
                        "title": citation.get("title", ""),
                        "url": url,
                        "snippet": citation.get("snippet", ""),
                        "engine": citation.get("engine", "mindsearch"),
                        "rank": int(citation.get("rank", 9999) or 9999),
                        "language": citation.get("language", "zh"),
                        "metadata": {
                            "citation_id": citation.get("id"),
                            "source_engines": citation.get("source_engines", []),
                            "source_queries": citation.get("source_queries", []),
                        },
                    }
                )
        merged_results.sort(key=lambda x: (x.get("rank", 9999), x.get("url", "")))

        citations = build_web_citations(merged_results, query=query, prefix="M")
        references_text = format_reference_block(citations, max_items=60)
        comparison = build_comparison_summary(merged_results)
        ref_num_by_url = {
            str(item.get("url")): idx + 1
            for idx, item in enumerate(citations)
            if str(item.get("url") or "").strip()
        }

        reference_index_lines = ["Reference Index (MindSearch style):"]
        for idx, item in enumerate(citations, 1):
            title = str(item.get("title") or "").strip() or "Untitled"
            url = str(item.get("url") or "").strip()
            reference_index_lines.append(f"[[{idx}]] {title} {url}")
        reference_index_text = "\n".join(reference_index_lines) if len(reference_index_lines) > 1 else ""

        # MindSearch 兼容输出（node / adjacency_list / ref2url）
        compat_nodes: Dict[str, Dict[str, Any]] = {}
        compat_adj: Dict[str, List[Dict[str, Any]]] = {node_id: [] for node_id in self._nodes.keys()}
        node_sections: List[Dict[str, Any]] = []

        for node in sorted(self._nodes.values(), key=lambda item: (item.depth, item.started_at or "", item.id)):
            refs: List[int] = []
            for citation in node.citations:
                url = str(citation.get("url") or "")
                if not url:
                    continue
                ref_num = ref_num_by_url.get(url)
                if ref_num and ref_num not in refs:
                    refs.append(ref_num)
                if len(refs) >= 8:
                    break

            response_text = (node.search_summary or "").strip()
            if not response_text and node.citations:
                response_text = str(node.citations[0].get("snippet") or "").strip()[:320]
            if not response_text:
                response_text = "No summary generated for this node."

            ref_markers = "".join([f"[[{n}]]" for n in refs[:4]])
            answer_with_refs = f"{response_text} {ref_markers}".strip()
            node_sections.append(
                {
                    "node_id": node.id,
                    "question": node.query,
                    "answer": answer_with_refs,
                    "refs": refs,
                }
            )

            compat_nodes[node.id] = {
                "content": node.query,
                "type": "root" if node.parent_id is None and node.depth == 0 else "searcher",
                "depth": node.depth,
                "status": node.status,
                "response": {
                    "content": answer_with_refs,
                    "stream_state": 3 if node.status == "completed" else (4 if node.status == "failed" else 1),
                },
                "memory": {
                    "result_count": node.result_count,
                    "urls": node.urls[:8],
                    "errors": node.errors[:5],
                },
            }

        for edge in self._edges:
            from_id = edge.get("from")
            to_id = edge.get("to")
            if not from_id or not to_id:
                continue
            target = self._nodes.get(to_id)
            if target is None:
                state = 2
            elif target.status == "completed":
                state = 3
            elif target.status == "running":
                state = 1
            else:
                state = 2
            compat_adj.setdefault(from_id, []).append(
                {
                    "id": f"{from_id}->{to_id}",
                    "name": to_id,
                    "state": state,
                }
            )

        compat_ref2url: Dict[int, Dict[str, Any]] = {}
        for idx, item in enumerate(citations, 1):
            compat_ref2url[idx] = {
                "url": item.get("url"),
                "title": item.get("title"),
                "domain": item.get("domain"),
            }

        return {
            "mode": "mindsearch",
            "query": query,
            "graph": {
                "nodes": node_dict,
                "edges": self._edges,
            },
            "mindsearch_compat": {
                "node": compat_nodes,
                "adjacency_list": compat_adj,
                "ref2url": compat_ref2url,
                "sections": node_sections,
            },
            "stats": {
                "total_nodes": len(self._nodes),
                "completed_nodes": len(completed),
                "failed_nodes": len(failed),
                "max_turns": self.max_turns,
                "max_branches": self.max_branches,
            },
            "total_results": len(merged_results),
            "results": merged_results,
            "citations": citations,
            "references_text": references_text,
            "reference_index_text": reference_index_text,
            "comparison": comparison,
            "summary": (
                f"MindSearch 风格研究完成：共 {len(self._nodes)} 个节点，"
                f"完成 {len(completed)} 个，失败 {len(failed)} 个，汇总 {len(merged_results)} 条结果。"
            ),
        }

    async def _emit(self, callback: EventCallback, event: str, data: Dict[str, Any]) -> None:
        if callback is None:
            return
        try:
            result = callback(event, data)
            if inspect.isawaitable(result):
                await result
        except Exception as exc:
            logger.debug("MindSearch event callback failed: %s", exc)

    @staticmethod
    def _normalize_query(text: str) -> str:
        return re.sub(r"\s+", " ", str(text or "").strip().lower())

    @staticmethod
    def _is_chinese(text: str) -> bool:
        return is_chinese_text(text)

    @staticmethod
    def _is_low_signal_url(url: str) -> bool:
        lowered = str(url or "").lower()
        return any(
            token in lowered
            for token in (
                "login",
                "signin",
                "signup",
                "register",
                "passport.",
                "account",
                "privacy",
                "terms",
                "policy",
                "newpneumonia",
            )
        )

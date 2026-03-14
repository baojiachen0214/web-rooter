"""
Bounded artifact graph for runtime observability.

The graph stores compact, deduplicated entities (nodes) and relations (edges)
produced during crawling/research workflows, while enforcing strict memory-like
budgets to avoid unbounded growth.
"""
from __future__ import annotations

import hashlib
import json
from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional


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
class ArtifactGraphBudget:
    """Budget controls to keep graph memory bounded."""

    max_nodes: int = 320
    max_edges: int = 1200
    max_out_edges_per_node: int = 24
    max_node_attrs: int = 24
    max_edge_attrs: int = 12
    max_attr_depth: int = 2
    max_attr_items: int = 16
    max_attr_string_chars: int = 280
    max_label_chars: int = 160


@dataclass
class ArtifactNode:
    node_id: str
    kind: str
    label: str
    attrs: Dict[str, Any]
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    touches: int = 1

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.node_id,
            "kind": self.kind,
            "label": self.label,
            "attrs": self.attrs,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "touches": self.touches,
        }


@dataclass
class ArtifactEdge:
    edge_id: str
    source: str
    target: str
    relation: str
    attrs: Dict[str, Any]
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    touches: int = 1

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.edge_id,
            "source": self.source,
            "target": self.target,
            "relation": self.relation,
            "attrs": self.attrs,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "touches": self.touches,
        }


class ArtifactGraph:
    """In-memory bounded graph with LRU-style eviction."""

    def __init__(self, budget: Optional[ArtifactGraphBudget] = None):
        self._budget = budget or ArtifactGraphBudget()
        self._nodes: "OrderedDict[str, ArtifactNode]" = OrderedDict()
        self._edges: "OrderedDict[str, ArtifactEdge]" = OrderedDict()
        self._outgoing: Dict[str, "OrderedDict[str, None]"] = {}
        self._incoming: Dict[str, "OrderedDict[str, None]"] = {}
        self._counters: Dict[str, int] = {
            "nodes_upserted": 0,
            "nodes_evicted": 0,
            "edges_upserted": 0,
            "edges_evicted_total": 0,
            "edges_evicted_by_budget": 0,
            "edges_evicted_by_out_degree": 0,
            "edges_removed_by_node_eviction": 0,
        }

    @property
    def budget(self) -> ArtifactGraphBudget:
        return self._budget

    def clear(self) -> None:
        self._nodes.clear()
        self._edges.clear()
        self._outgoing.clear()
        self._incoming.clear()
        for key in list(self._counters.keys()):
            self._counters[key] = 0

    def make_node_id(self, kind: str, key: str) -> str:
        normalized_kind = _trim_scalar((kind or "artifact").strip().lower(), 32)
        normalized_key = (key or "").strip().lower()
        digest = hashlib.sha1(normalized_key.encode("utf-8", errors="ignore")).hexdigest()[:18]
        return f"{normalized_kind}:{digest}"

    def upsert_node(
        self,
        *,
        node_id: str,
        kind: str,
        label: str,
        attrs: Optional[Dict[str, Any]] = None,
    ) -> ArtifactNode:
        normalized_kind = _trim_scalar((kind or "artifact").strip().lower(), 32)
        normalized_label = _trim_scalar(label or node_id, self._budget.max_label_chars)
        compact_attrs = self._compact_attrs(attrs or {}, max_attrs=self._budget.max_node_attrs)
        now = datetime.now()

        existing = self._nodes.get(node_id)
        if existing is not None:
            existing.kind = normalized_kind
            existing.label = normalized_label
            existing.attrs = compact_attrs
            existing.updated_at = now
            existing.touches += 1
            self._nodes.move_to_end(node_id)
            return existing

        node = ArtifactNode(
            node_id=node_id,
            kind=normalized_kind,
            label=normalized_label,
            attrs=compact_attrs,
            created_at=now,
            updated_at=now,
            touches=1,
        )
        self._nodes[node_id] = node
        self._counters["nodes_upserted"] += 1
        self._evict_nodes()
        return node

    def upsert_edge(
        self,
        *,
        source: str,
        target: str,
        relation: str,
        attrs: Optional[Dict[str, Any]] = None,
    ) -> ArtifactEdge:
        if source not in self._nodes:
            self.upsert_node(node_id=source, kind="placeholder", label=source, attrs={})
        if target not in self._nodes:
            self.upsert_node(node_id=target, kind="placeholder", label=target, attrs={})

        relation_key = _trim_scalar((relation or "related_to").strip().lower(), 48)
        edge_id = self._make_edge_id(source, relation_key, target)
        compact_attrs = self._compact_attrs(attrs or {}, max_attrs=self._budget.max_edge_attrs)
        now = datetime.now()

        existing = self._edges.get(edge_id)
        if existing is not None:
            existing.attrs = compact_attrs
            existing.updated_at = now
            existing.touches += 1
            self._edges.move_to_end(edge_id)
            self._touch_edge_index(edge_id, existing.source, existing.target)
            return existing

        edge = ArtifactEdge(
            edge_id=edge_id,
            source=source,
            target=target,
            relation=relation_key,
            attrs=compact_attrs,
            created_at=now,
            updated_at=now,
            touches=1,
        )
        self._edges[edge_id] = edge
        self._counters["edges_upserted"] += 1
        self._register_edge_index(edge_id, source, target)
        self._enforce_out_degree_limit(source)
        self._evict_edges()
        return edge

    def snapshot(
        self,
        *,
        node_limit: int = 80,
        edge_limit: int = 200,
        node_kind: Optional[str] = None,
    ) -> Dict[str, Any]:
        max_nodes = max(1, min(node_limit, 2000))
        max_edges = max(1, min(edge_limit, 4000))
        normalized_kind = (node_kind or "").strip().lower() or None

        recent_nodes = list(reversed(list(self._nodes.values())))
        if normalized_kind:
            recent_nodes = [node for node in recent_nodes if node.kind == normalized_kind]
        selected_nodes = recent_nodes[:max_nodes]
        node_ids = {node.node_id for node in selected_nodes}

        recent_edges = list(reversed(list(self._edges.values())))
        selected_edges: List[ArtifactEdge] = []
        for edge in recent_edges:
            if edge.source in node_ids and edge.target in node_ids:
                selected_edges.append(edge)
            if len(selected_edges) >= max_edges:
                break

        return {
            "nodes": [node.to_dict() for node in selected_nodes],
            "edges": [edge.to_dict() for edge in selected_edges],
            "stats": self.get_stats(),
            "filters": {
                "node_kind": normalized_kind,
                "node_limit": max_nodes,
                "edge_limit": max_edges,
            },
            "truncated": {
                "nodes": len(recent_nodes) > len(selected_nodes),
                "edges": len(recent_edges) > len(selected_edges),
            },
        }

    def get_stats(self) -> Dict[str, Any]:
        approx_chars = 0
        for node in self._nodes.values():
            approx_chars += len(node.node_id) + len(node.kind) + len(node.label)
            approx_chars += len(json.dumps(node.attrs, ensure_ascii=False, separators=(",", ":")))
        for edge in self._edges.values():
            approx_chars += len(edge.edge_id) + len(edge.source) + len(edge.target) + len(edge.relation)
            approx_chars += len(json.dumps(edge.attrs, ensure_ascii=False, separators=(",", ":")))

        return {
            "nodes": len(self._nodes),
            "edges": len(self._edges),
            "approx_chars": approx_chars,
            "counters": dict(self._counters),
            "budget": {
                "max_nodes": self._budget.max_nodes,
                "max_edges": self._budget.max_edges,
                "max_out_edges_per_node": self._budget.max_out_edges_per_node,
                "max_node_attrs": self._budget.max_node_attrs,
                "max_edge_attrs": self._budget.max_edge_attrs,
                "max_attr_depth": self._budget.max_attr_depth,
                "max_attr_items": self._budget.max_attr_items,
                "max_attr_string_chars": self._budget.max_attr_string_chars,
                "max_label_chars": self._budget.max_label_chars,
            },
        }

    def _compact_attrs(self, attrs: Dict[str, Any], *, max_attrs: int) -> Dict[str, Any]:
        compact: Dict[str, Any] = {}
        for idx, (key, value) in enumerate((attrs or {}).items()):
            if idx >= max_attrs:
                break
            compact[_trim_scalar(key, 80)] = _trim_value(
                value,
                max_depth=self._budget.max_attr_depth,
                max_items=self._budget.max_attr_items,
                max_string_chars=self._budget.max_attr_string_chars,
            )
        return compact

    def _make_edge_id(self, source: str, relation: str, target: str) -> str:
        return f"{source}|{relation}|{target}"

    def _touch_edge_index(self, edge_id: str, source: str, target: str) -> None:
        out_bucket = self._outgoing.setdefault(source, OrderedDict())
        in_bucket = self._incoming.setdefault(target, OrderedDict())
        out_bucket.pop(edge_id, None)
        in_bucket.pop(edge_id, None)
        out_bucket[edge_id] = None
        in_bucket[edge_id] = None

    def _register_edge_index(self, edge_id: str, source: str, target: str) -> None:
        self._outgoing.setdefault(source, OrderedDict())[edge_id] = None
        self._incoming.setdefault(target, OrderedDict())[edge_id] = None

    def _unregister_edge_index(self, edge_id: str, source: str, target: str) -> None:
        out_bucket = self._outgoing.get(source)
        if out_bucket is not None:
            out_bucket.pop(edge_id, None)
            if not out_bucket:
                self._outgoing.pop(source, None)
        in_bucket = self._incoming.get(target)
        if in_bucket is not None:
            in_bucket.pop(edge_id, None)
            if not in_bucket:
                self._incoming.pop(target, None)

    def _remove_edge(self, edge_id: str, *, reason: str = "generic") -> None:
        edge = self._edges.pop(edge_id, None)
        if edge is None:
            return
        self._unregister_edge_index(edge_id, edge.source, edge.target)
        self._counters["edges_evicted_total"] += 1
        if reason == "edge_budget":
            self._counters["edges_evicted_by_budget"] += 1
        elif reason == "out_degree":
            self._counters["edges_evicted_by_out_degree"] += 1
        elif reason == "node_evicted":
            self._counters["edges_removed_by_node_eviction"] += 1

    def _remove_node(self, node_id: str, *, reason: str = "generic") -> None:
        self._nodes.pop(node_id, None)
        outgoing_keys = list((self._outgoing.get(node_id) or {}).keys())
        incoming_keys = list((self._incoming.get(node_id) or {}).keys())
        for edge_id in outgoing_keys:
            self._remove_edge(edge_id, reason=reason)
        for edge_id in incoming_keys:
            self._remove_edge(edge_id, reason=reason)

    def _evict_nodes(self) -> None:
        while len(self._nodes) > self._budget.max_nodes:
            node_id = next(iter(self._nodes))
            self._counters["nodes_evicted"] += 1
            self._remove_node(node_id, reason="node_evicted")

    def _evict_edges(self) -> None:
        while len(self._edges) > self._budget.max_edges:
            edge_id = next(iter(self._edges))
            self._remove_edge(edge_id, reason="edge_budget")

    def _enforce_out_degree_limit(self, source: str) -> None:
        bucket = self._outgoing.get(source)
        if bucket is None:
            return
        while len(bucket) > self._budget.max_out_edges_per_node:
            oldest_edge_id = next(iter(bucket))
            self._remove_edge(oldest_edge_id, reason="out_degree")
            bucket = self._outgoing.get(source)
            if bucket is None:
                break

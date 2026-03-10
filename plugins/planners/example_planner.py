"""Example MindSearch planner plugin."""

from __future__ import annotations

from typing import Any, Dict, List, Tuple


class AcademicDensePlanner:
    """Aggressive planner for research-heavy queries."""

    name = "academic_dense"

    def decompose_seed_queries(
        self,
        query: str,
        max_branches: int,
        is_chinese: bool,
    ) -> List[Tuple[str, str]]:
        if is_chinese:
            templates = [
                ("{q} 核心论文", "paper-discovery"),
                ("{q} 方法对比 与 benchmark", "benchmark"),
                ("{q} 开源实现 与 复现", "implementation"),
                ("{q} 社区争议 与 局限", "limitations"),
                ("{q} 最新讨论 与 新闻", "discussion"),
            ]
        else:
            templates = [
                ("{q} seminal papers", "paper-discovery"),
                ("{q} benchmark and ablation", "benchmark"),
                ("{q} open-source implementation", "implementation"),
                ("{q} limitations and controversy", "limitations"),
                ("{q} latest discussion", "discussion"),
            ]

        return [(tpl.format(q=query).strip(), reason) for tpl, reason in templates[: max(1, max_branches)]]

    def should_expand(
        self,
        node: Dict[str, Any],
        max_turns: int,
        strict: bool = False,
    ) -> bool:
        depth = int(node.get("depth", 0) or 0)
        if depth + 1 >= max_turns:
            return False
        if str(node.get("status") or "") != "completed":
            return False

        if strict:
            return True

        result_count = int(node.get("result_count", 0) or 0)
        return result_count <= 8

    def generate_followup_queries(
        self,
        node: Dict[str, Any],
        max_branches: int,
        is_chinese: bool,
    ) -> List[Tuple[str, str]]:
        query = str(node.get("query") or "").strip()
        if not query:
            return []

        if is_chinese:
            variants = [
                f"{query} 引用网络",
                f"{query} 复现细节",
                f"{query} 负面结果",
                f"{query} 工业落地",
            ]
        else:
            variants = [
                f"{query} citation network",
                f"{query} reproduction details",
                f"{query} negative results",
                f"{query} industry deployment",
            ]

        return [(item, "academic-followup") for item in variants[: max(1, max_branches)]]


def create_planner() -> AcademicDensePlanner:
    return AcademicDensePlanner()

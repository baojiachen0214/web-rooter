"""
MindSearch planner registry.

IronClaw-inspired design points:
- registry-based pluggability
- deterministic fallback planner
- fail-open dynamic loader
"""
from __future__ import annotations

import importlib
import importlib.util
import inspect
import logging
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Protocol, Tuple

logger = logging.getLogger(__name__)


class ResearchPlanner(Protocol):
    """Planner contract used by MindSearch pipeline."""

    name: str

    def decompose_seed_queries(
        self,
        query: str,
        max_branches: int,
        is_chinese: bool,
    ) -> List[Tuple[str, str]]:
        ...

    def should_expand(
        self,
        node: Dict[str, Any],
        max_turns: int,
        strict: bool = False,
    ) -> bool:
        ...

    def generate_followup_queries(
        self,
        node: Dict[str, Any],
        max_branches: int,
        is_chinese: bool,
    ) -> List[Tuple[str, str]]:
        ...


class HeuristicResearchPlanner:
    """Default planner that mirrors current MindSearch heuristics."""

    name = "heuristic"

    def decompose_seed_queries(
        self,
        query: str,
        max_branches: int,
        is_chinese: bool,
    ) -> List[Tuple[str, str]]:
        if is_chinese:
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

        pairs: List[Tuple[str, str]] = []
        for template, reason in templates[: max(1, max_branches)]:
            pairs.append((template.format(q=query).strip(), reason))
        return pairs

    def should_expand(
        self,
        node: Dict[str, Any],
        max_turns: int,
        strict: bool = False,
    ) -> bool:
        depth = int(node.get("depth", 0) or 0)
        if depth + 1 >= max_turns:
            return False

        status = str(node.get("status") or "")
        if status != "completed":
            return False

        if strict:
            return True

        result_count = int(node.get("result_count", 0) or 0)
        errors = node.get("errors", [])
        if result_count <= 2:
            return True
        if isinstance(errors, list) and len(errors) > 0:
            return True
        return False

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
            fallback_templates = [
                f"{query} 关键数据对比",
                f"{query} 社区讨论与评测",
                f"{query} 实操指南",
            ]
        else:
            fallback_templates = [
                f"{query} benchmark comparison",
                f"{query} community discussion",
                f"{query} practical tutorial",
            ]

        pairs: List[Tuple[str, str]] = []
        for item in fallback_templates[: max(1, max_branches)]:
            pairs.append((item, "followup-expansion"))
        return pairs


class ResearchPlannerRegistry:
    """Planner registry with dynamic loader."""

    _REQUIRED_METHODS = (
        "decompose_seed_queries",
        "should_expand",
        "generate_followup_queries",
    )

    def __init__(self):
        self._entries: List[Tuple[int, ResearchPlanner]] = []
        self._loaded_specs: set[str] = set()
        self.register(HeuristicResearchPlanner(), priority=100)

    def register(self, planner: ResearchPlanner, priority: int = 100) -> None:
        name = str(getattr(planner, "name", "")).strip()
        if not name:
            raise ValueError("Research planner must provide a non-empty name")

        for method in self._REQUIRED_METHODS:
            if not callable(getattr(planner, method, None)):
                raise ValueError(f"Research planner '{name}' missing method: {method}")

        self._entries = [(p, x) for p, x in self._entries if str(getattr(x, "name", "")) != name]
        self._entries.append((priority, planner))
        self._entries.sort(key=lambda item: item[0])

    def list_planners(self) -> List[str]:
        return [str(getattr(item, "name", "unknown")) for _, item in self._entries]

    def load_from_env(self, force: bool = False) -> List[str]:
        loaded: List[str] = []
        specs: List[str] = []

        raw_many = os.getenv("WEB_ROOTER_MINDSEARCH_PLANNERS", "").strip()
        if raw_many:
            specs.extend([x.strip() for x in raw_many.split(",") if x.strip()])

        raw_one = os.getenv("WEB_ROOTER_MINDSEARCH_PLANNER", "").strip()
        # one-line env can be name (already registered) or loader spec module:file
        if raw_one and ":" in raw_one:
            specs.append(raw_one)

        if specs:
            loaded.extend(self.load_from_specs(specs, force=force))

        return loaded

    def load_from_specs(self, specs: List[str], force: bool = False) -> List[str]:
        loaded: List[str] = []
        for spec in specs:
            if not force and spec in self._loaded_specs:
                continue
            try:
                planner = self._resolve_planner_spec(spec)
                self.register(planner, priority=200)
                self._loaded_specs.add(spec)
                loaded.append(str(getattr(planner, "name", spec)))
                logger.info("已加载 MindSearch planner: %s <- %s", getattr(planner, "name", spec), spec)
            except Exception as exc:
                logger.warning("加载 MindSearch planner 失败 %s: %s", spec, exc)
        return loaded

    def resolve(self, name: Optional[str] = None) -> ResearchPlanner:
        if not self._entries:
            planner = HeuristicResearchPlanner()
            self.register(planner, priority=100)

        preferred = (name or os.getenv("WEB_ROOTER_MINDSEARCH_PLANNER_NAME", "")).strip()
        if not preferred:
            preferred = os.getenv("WEB_ROOTER_MINDSEARCH_PLANNER", "").strip()
            if ":" in preferred:
                preferred = ""

        if preferred:
            for _, planner in self._entries:
                if str(getattr(planner, "name", "")).strip().lower() == preferred.lower():
                    return planner

        # priority ascending; last fallback to heuristic by registration order
        return self._entries[0][1]

    def _resolve_planner_spec(self, spec: str) -> ResearchPlanner:
        if ":" not in spec:
            raise ValueError("Invalid planner spec, expected '<module_or_file>:<object>'")

        module_part, object_name = spec.split(":", 1)
        module_part = module_part.strip()
        object_name = object_name.strip()
        if not module_part or not object_name:
            raise ValueError("Invalid planner spec, module/object missing")

        target = self._load_object(module_part, object_name)
        planner = self._coerce_to_planner(target, module_part, object_name)
        self._validate_planner(planner)
        return planner

    def _coerce_to_planner(self, target: Any, module_part: str, object_name: str) -> ResearchPlanner:
        if self._looks_like_planner_instance(target):
            return target

        if isinstance(target, type):
            instance = target()
            if self._looks_like_planner_instance(instance):
                return instance
            raise ValueError(f"Class '{target.__name__}' is not a valid research planner")

        if callable(target):
            try:
                sig = inspect.signature(target)
                if len(sig.parameters) == 0:
                    instance = target()
                    if self._looks_like_planner_instance(instance):
                        return instance
            except Exception:
                pass

        raise ValueError(f"Unsupported planner target: {module_part}:{object_name}")

    def _validate_planner(self, planner: Any) -> None:
        name = str(getattr(planner, "name", "")).strip()
        if not name:
            raise ValueError("Planner must have 'name'")

        for method in self._REQUIRED_METHODS:
            if not callable(getattr(planner, method, None)):
                raise ValueError(f"Planner '{name}' missing required method: {method}")

    def _looks_like_planner_instance(self, value: Any) -> bool:
        if value is None:
            return False
        name = str(getattr(value, "name", "")).strip()
        if not name:
            return False
        return all(callable(getattr(value, method, None)) for method in self._REQUIRED_METHODS)

    @staticmethod
    def _load_object(module_part: str, object_name: str) -> Any:
        path_candidate = Path(module_part)
        module = None
        if path_candidate.suffix.lower() == ".py" and path_candidate.exists():
            module_name = f"web_rooter_mindsearch_planner_{abs(hash(str(path_candidate.resolve())))}"
            spec = importlib.util.spec_from_file_location(module_name, str(path_candidate.resolve()))
            if spec is None or spec.loader is None:
                raise ImportError(f"无法加载模块文件: {path_candidate}")
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
        else:
            module = importlib.import_module(module_part)

        if not hasattr(module, object_name):
            raise AttributeError(f"{module_part} has no attribute '{object_name}'")
        return getattr(module, object_name)


_registry: Optional[ResearchPlannerRegistry] = None


def get_research_planner_registry() -> ResearchPlannerRegistry:
    global _registry
    if _registry is None:
        _registry = ResearchPlannerRegistry()
        _registry.load_from_env(force=False)
    return _registry


def resolve_research_planner(name: Optional[str] = None) -> ResearchPlanner:
    return get_research_planner_registry().resolve(name=name)


def is_chinese_text(text: str) -> bool:
    return bool(re.search(r"[\u4e00-\u9fff]", str(text or "")))

"""
搜索结果后处理扩展接口。

设计目标：
- 允许用户在“抓取完成后”接入自己的数据处理逻辑
- 保持默认 fail-open，不影响主链路稳定性
- 提供内置处理器（质量统计等）并支持动态加载自定义处理器
"""
from __future__ import annotations

import importlib
import importlib.util
import inspect
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Protocol, Tuple

logger = logging.getLogger(__name__)


@dataclass
class PostProcessContext:
    """后处理上下文。"""

    query: str
    mode: str
    metadata: Dict[str, Any] = field(default_factory=dict)


class ResultPostProcessor(Protocol):
    """后处理器协议。"""

    name: str

    def process(self, result: Dict[str, Any], context: PostProcessContext) -> Dict[str, Any]:
        """接收结果并返回（可修改后的）结果。"""
        ...


class _CallablePostProcessor:
    """把简单函数包装为处理器对象。"""

    def __init__(self, name: str, func: Callable[[Dict[str, Any], PostProcessContext], Dict[str, Any]]):
        self.name = name
        self._func = func

    def process(self, result: Dict[str, Any], context: PostProcessContext) -> Dict[str, Any]:
        return self._func(result, context)


class _QualityStatsProcessor:
    """内置处理器：追加高信号统计。"""

    name = "quality_stats"

    _LOW_SIGNAL_KEYWORDS = (
        "login", "signup", "register", "privacy", "terms", "agreement", "policy",
        "help", "about", "account", "my", "cart", "coupon", "service",
        "user/self", "notification",
    )

    def process(self, result: Dict[str, Any], context: PostProcessContext) -> Dict[str, Any]:
        payload = dict(result or {})
        raw_results = payload.get("results", [])
        if not isinstance(raw_results, list):
            raw_results = []

        query_tokens = [t.lower() for t in str(context.query or "").split() if len(t) >= 2]
        high_signal = 0
        for item in raw_results:
            if not isinstance(item, dict):
                continue
            url = str(item.get("url") or "").lower()
            title = str(item.get("title") or "").lower()
            snippet = str(item.get("snippet") or item.get("description") or "").lower()
            text = f"{title} {snippet} {url}"
            if any(k in url for k in self._LOW_SIGNAL_KEYWORDS):
                continue
            if query_tokens and not any(token in text for token in query_tokens):
                continue
            high_signal += 1

        payload.setdefault("quality", {})
        payload["quality"]["high_signal_results"] = high_signal
        payload["quality"]["raw_result_count"] = len(raw_results)
        payload["quality"]["mode"] = context.mode
        return payload


class PostProcessorRegistry:
    """后处理器注册中心（按优先级执行）。"""

    def __init__(self):
        self._entries: List[Tuple[int, ResultPostProcessor]] = []
        self._loaded_specs: set[str] = set()
        self._register_builtin()

    def _register_builtin(self) -> None:
        self.register(_QualityStatsProcessor(), priority=100)

    def register(self, processor: ResultPostProcessor, priority: int = 100) -> None:
        name = getattr(processor, "name", "").strip()
        if not name:
            raise ValueError("Post processor must have a non-empty name")
        # 同名覆盖
        self._entries = [(p, inst) for p, inst in self._entries if getattr(inst, "name", "") != name]
        self._entries.append((priority, processor))
        self._entries.sort(key=lambda x: x[0])

    def list_processors(self) -> List[str]:
        return [getattr(proc, "name", "unknown") for _, proc in self._entries]

    def load_from_env(self, force: bool = False) -> List[str]:
        raw = os.getenv("WEB_ROOTER_POSTPROCESSORS", "").strip()
        if not raw:
            return []
        specs = [x.strip() for x in raw.split(",") if x.strip()]
        return self.load_from_specs(specs, force=force)

    def load_from_specs(self, specs: List[str], force: bool = False) -> List[str]:
        loaded: List[str] = []
        for spec in specs:
            if not force and spec in self._loaded_specs:
                continue
            try:
                processor = self._resolve_processor_spec(spec)
                self.register(processor, priority=200)
                self._loaded_specs.add(spec)
                loaded.append(getattr(processor, "name", spec))
                logger.info("已加载后处理器: %s <- %s", getattr(processor, "name", spec), spec)
            except Exception as exc:
                logger.warning("加载后处理器失败 %s: %s", spec, exc)
        return loaded

    def run(
        self,
        result: Dict[str, Any],
        context: PostProcessContext,
    ) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        payload = dict(result or {})
        report: Dict[str, Any] = {
            "processors": [],
            "errors": [],
        }

        for _, processor in self._entries:
            name = getattr(processor, "name", "unknown")
            try:
                payload = processor.process(payload, context)
                report["processors"].append(name)
            except Exception as exc:
                report["errors"].append(f"{name}: {exc}")
                logger.warning("后处理器执行失败 %s: %s", name, exc)

        return payload, report

    def _resolve_processor_spec(self, spec: str) -> ResultPostProcessor:
        """
        解析 spec：
        - module.path:object_name
        - /abs/or/rel/path.py:object_name
        对象可为：
        - 处理器实例（有 name + process）
        - 处理器类（可实例化）
        - 函数 fn(result, context) -> dict
        """
        if ":" not in spec:
            raise ValueError("Invalid spec, expected '<module_or_file>:<object>'")
        module_part, object_name = spec.split(":", 1)
        module_part = module_part.strip()
        object_name = object_name.strip()
        if not module_part or not object_name:
            raise ValueError("Invalid spec, module/object missing")

        target = self._load_object(module_part, object_name)
        if hasattr(target, "process") and hasattr(target, "name"):
            return target  # instance
        if isinstance(target, type):
            instance = target()
            if hasattr(instance, "process") and hasattr(instance, "name"):
                return instance
            raise ValueError(f"Class '{target.__name__}' is not a valid post processor")
        if callable(target):
            # 支持工厂函数：factory() -> processor instance
            try:
                sig = inspect.signature(target)
                if len(sig.parameters) == 0:
                    instance = target()
                    if hasattr(instance, "process") and hasattr(instance, "name"):
                        return instance
            except Exception:
                pass
            name = f"callable:{module_part}:{object_name}"
            return _CallablePostProcessor(name=name, func=target)
        raise ValueError("Unsupported processor target type")

    @staticmethod
    def _load_object(module_part: str, object_name: str) -> Any:
        path_candidate = Path(module_part)
        module = None
        if path_candidate.suffix.lower() == ".py" and path_candidate.exists():
            module_name = f"web_rooter_postproc_{abs(hash(str(path_candidate.resolve())))}"
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


_registry: Optional[PostProcessorRegistry] = None


def get_post_processor_registry() -> PostProcessorRegistry:
    global _registry
    if _registry is None:
        _registry = PostProcessorRegistry()
        _registry.load_from_env(force=False)
    return _registry


def run_post_processors(
    result: Dict[str, Any],
    context: PostProcessContext,
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    registry = get_post_processor_registry()
    return registry.run(result, context)

"""
AI Web Agents package.

Keep package imports lightweight so helper utilities can import WebAgent without
also forcing spider/crawler runtime dependencies.
"""
from __future__ import annotations

from importlib import import_module
from typing import Any, Dict, Tuple


_LAZY_EXPORTS: Dict[str, Tuple[str, str]] = {
    "WebAgent": (".web_agent", "WebAgent"),
    "AgentResponse": (".web_agent", "AgentResponse"),
    "Spider": (".spider", "Spider"),
    "SpiderConfig": (".spider", "SpiderConfig"),
    "run_spider": (".spider", "run_spider"),
    "create_spider_class": (".spider", "create_spider_class"),
}


def __getattr__(name: str) -> Any:
    if name not in _LAZY_EXPORTS:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module_name, attr_name = _LAZY_EXPORTS[name]
    module = import_module(module_name, __name__)
    value = getattr(module, attr_name)
    globals()[name] = value
    return value


__all__ = list(_LAZY_EXPORTS.keys())

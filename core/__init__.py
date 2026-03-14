"""
Web-Rooter core package.

This package used to eagerly import almost every submodule, which made even
lightweight utilities depend on heavy optional runtime packages at import time.
We keep the public surface but switch to lazy loading so internal layers can be
tested and composed independently.
"""
from __future__ import annotations

from importlib import import_module
from typing import Any, Dict, Tuple

from .version import APP_VERSION

__version__ = APP_VERSION
__author__ = "Web-Rooter Team"


_LAZY_EXPORTS: Dict[str, Tuple[str, str]] = {
    "Crawler": (".crawler", "Crawler"),
    "CrawlResult": (".crawler", "CrawlResult"),
    "Parser": (".parser", "Parser"),
    "ExtractedData": (".parser", "ExtractedData"),
    "AdaptiveParser": (".parser", "AdaptiveParser"),
    "BrowserManager": (".browser", "BrowserManager"),
    "BrowserResult": (".browser", "BrowserResult"),
    "Request": (".request", "Request"),
    "Response": (".response", "Response"),
    "TextResponse": (".response", "TextResponse"),
    "JsonResponse": (".response", "JsonResponse"),
    "make_request": (".request", "make_request"),
    "make_requests_from_urls": (".request", "make_requests_from_urls"),
    "create_response": (".response", "create_response"),
    "Scheduler": (".scheduler", "Scheduler"),
    "SchedulerConfig": (".scheduler", "SchedulerConfig"),
    "CheckpointManager": (".checkpoint", "CheckpointManager"),
    "SessionManager": (".session_manager", "SessionManager"),
    "SessionType": (".session_manager", "SessionType"),
    "ResultQueue": (".result_queue", "ResultQueue"),
    "StreamItem": (".result_queue", "StreamItem"),
    "StreamConsumer": (".result_queue", "StreamConsumer"),
    "RequestCache": (".cache", "RequestCache"),
    "MemoryCache": (".cache", "MemoryCache"),
    "SQLiteCache": (".cache", "SQLiteCache"),
    "ConnectionPool": (".connection_pool", "ConnectionPool"),
    "PooledSession": (".connection_pool", "PooledSession"),
    "MetricsCollector": (".metrics", "MetricsCollector"),
    "ProxyPoolMetrics": (".metrics", "ProxyPoolMetrics"),
    "SearchEngine": (".search_engine", "SearchEngine"),
    "SearchEngineClient": (".search_engine", "SearchEngineClient"),
    "MultiSearchEngine": (".search_engine", "MultiSearchEngine"),
    "BaseSearchEngine": (".search_engine_base", "BaseSearchEngine"),
    "SearchEngineBase": (".search_engine_base", "BaseSearchEngine"),
    "AcademicSearchEngine": (".academic_search", "AcademicSearchEngine"),
    "PaperResult": (".academic_search", "PaperResult"),
    "CodeProjectResult": (".academic_search", "CodeProjectResult"),
    "ResearchKernel": (".research_kernel", "ResearchKernel"),
    "KernelVisitResult": (".research_kernel", "KernelVisitResult"),
    "KernelHTMLResult": (".research_kernel", "KernelHTMLResult"),
    "RuntimeEventStream": (".runtime_events", "RuntimeEventStream"),
    "RuntimeEventBudget": (".runtime_events", "RuntimeEventBudget"),
    "RuntimeEvent": (".runtime_events", "RuntimeEvent"),
    "RuntimePressureController": (".runtime_pressure", "RuntimePressureController"),
    "RuntimePressurePolicy": (".runtime_pressure", "RuntimePressurePolicy"),
    "ArtifactGraph": (".artifact_graph", "ArtifactGraph"),
    "ArtifactGraphBudget": (".artifact_graph", "ArtifactGraphBudget"),
    "ArtifactNode": (".artifact_graph", "ArtifactNode"),
    "ArtifactEdge": (".artifact_graph", "ArtifactEdge"),
    "FormFiller": (".form_search", "FormFiller"),
    "FormField": (".form_search", "FormField"),
    "SearchForm": (".form_search", "SearchForm"),
    "SearchFormResult": (".form_search", "SearchFormResult"),
    "auto_search": (".form_search", "auto_search"),
}


async def site_search(*args: Any, **kwargs: Any) -> Any:
    from .form_search import FormFiller

    filler = FormFiller()
    try:
        return await filler.site_search(*args, **kwargs)
    finally:
        await filler.close()


def __getattr__(name: str) -> Any:
    if name == "site_search":
        return site_search

    if name not in _LAZY_EXPORTS:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

    module_name, attr_name = _LAZY_EXPORTS[name]
    module = import_module(module_name, __name__)
    value = getattr(module, attr_name)
    globals()[name] = value
    return value


__all__ = list(_LAZY_EXPORTS.keys()) + ["site_search"]

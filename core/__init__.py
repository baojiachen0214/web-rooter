"""
Web-Rooter - AI Web Crawling Agent
"""

from .version import APP_VERSION

__version__ = APP_VERSION
__author__ = "Web-Rooter Team"

# Core modules
from .crawler import Crawler, CrawlResult
from .parser import Parser, ExtractedData, AdaptiveParser
from .browser import BrowserManager, BrowserResult
from .request import Request, make_request, make_requests_from_urls
from .response import Response, create_response, TextResponse, JsonResponse
from .scheduler import Scheduler, SchedulerConfig
from .checkpoint import CheckpointManager
from .session_manager import SessionManager, SessionType
from .result_queue import ResultQueue, StreamItem, StreamConsumer
from .cache import RequestCache, MemoryCache, SQLiteCache
from .connection_pool import ConnectionPool, PooledSession
from .metrics import MetricsCollector, ProxyPoolMetrics

# Search modules
from .search_engine import SearchEngine, SearchEngineClient, MultiSearchEngine
from .search_engine_base import BaseSearchEngine
from .academic_search import AcademicSearchEngine, PaperResult, CodeProjectResult
from .form_search import FormFiller, FormField, SearchForm, SearchFormResult

__all__ = [
    # Crawler
    "Crawler",
    "CrawlResult",
    "Parser",
    "ExtractedData",
    "AdaptiveParser",
    "BrowserManager",
    "BrowserResult",

    # Request/Response
    "Request",
    "Response",
    "TextResponse",
    "JsonResponse",
    "make_request",
    "make_requests_from_urls",
    "create_response",

    # Scheduler & Session
    "Scheduler",
    "SchedulerConfig",
    "CheckpointManager",
    "SessionManager",
    "SessionType",

    # Phase 3 modules
    "ResultQueue",
    "StreamItem",
    "StreamConsumer",
    "RequestCache",
    "MemoryCache",
    "SQLiteCache",
    "ConnectionPool",
    "PooledSession",
    "MetricsCollector",
    "ProxyPoolMetrics",

    # Search
    "SearchEngine",
    "SearchEngineClient",
    "MultiSearchEngine",
    "SearchEngineBase",
    "AcademicSearchEngine",
    "PaperResult",
    "CodeProjectResult",
    "FormFiller",

    # Utils
    "site_search",
    "auto_search",
]

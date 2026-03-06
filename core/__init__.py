"""
核心爬虫模块
"""
from .crawler import Crawler, CrawlResult
from .parser import Parser, ExtractedData
from .browser import BrowserManager, BrowserResult
from .search_engine import (
    SearchEngine,
    SearchResult,
    SearchResponse,
    SearchEngineClient,
    MultiSearchEngine,
    web_search,
    web_search_multi,
    web_search_smart,
)
from .academic_search import (
    AcademicSource,
    PaperResult,
    CodeProjectResult,
    AcademicSearchEngine,
    is_academic_query,
    academic_search,
    code_search,
)
from .form_search import (
    FormField,
    SearchForm,
    SearchFormResult,
    FormFiller,
    auto_search,
)

__all__ = [
    "Crawler",
    "CrawlResult",
    "Parser",
    "ExtractedData",
    "BrowserManager",
    "BrowserResult",
    "SearchEngine",
    "SearchResult",
    "SearchResponse",
    "SearchEngineClient",
    "MultiSearchEngine",
    "web_search",
    "web_search_multi",
    "web_search_smart",
    # Academic search
    "AcademicSource",
    "PaperResult",
    "CodeProjectResult",
    "AcademicSearchEngine",
    "is_academic_query",
    "academic_search",
    "code_search",
    # Form search
    "FormField",
    "SearchForm",
    "SearchFormResult",
    "FormFiller",
    "auto_search",
]

"""
Web-Rooter - AI Web Crawling Agent
"""

__version__ = "1.0.0"
__author__ = "Web-Rooter Team"

from .core import Crawler, Parser, BrowserManager
from .agents import WebAgent
from .tools import WebTools

__all__ = [
    "Crawler",
    "Parser",
    "BrowserManager",
    "WebAgent",
    "WebTools",
]

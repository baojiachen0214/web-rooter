"""
AI Web Agents
"""
from .web_agent import WebAgent, AgentResponse
from .spider import Spider, SpiderConfig, run_spider, create_spider_class

__all__ = [
    "WebAgent",
    "AgentResponse",
    "Spider",
    "SpiderConfig",
    "run_spider",
    "create_spider_class",
]

"""
配置模块
"""
import os
from dataclasses import dataclass
from typing import Optional

@dataclass
class CrawlerConfig:
    """爬虫配置"""
    # 请求头
    USER_AGENT: str = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

    # 超时设置
    TIMEOUT: int = 30  # 秒

    # 重试配置
    MAX_RETRIES: int = 3
    RETRY_DELAY: float = 1.0  # 秒

    # 限流配置
    REQUEST_DELAY: float = 0.5  # 请求间隔

    # 并发限制
    MAX_CONCURRENT: int = 5

    #  robots.txt 遵守
    RESPECT_ROBOTS: bool = True

    # 最大爬取深度
    MAX_DEPTH: int = 3

    # 允许的文件大小（字节）
    MAX_FILE_SIZE: int = 10 * 1024 * 1024  # 10MB


@dataclass
class BrowserConfig:
    """浏览器配置"""
    HEADLESS: bool = True
    TIMEOUT: int = 30000  # 毫秒
    WAIT_FOR_NETWORK: bool = True
    BLOCK_IMAGES: bool = True  # 加快速度
    BLOCK_FONTS: bool = True


@dataclass
class ServerConfig:
    """服务器配置"""
    HOST: str = "127.0.0.1"
    PORT: int = 8765


# 单例配置
crawler_config = CrawlerConfig()
browser_config = BrowserConfig()
server_config = ServerConfig()

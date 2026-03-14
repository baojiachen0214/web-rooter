"""
配置模块
"""
import os
from dataclasses import dataclass, field
from typing import Optional, List
from enum import Enum

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

    # 单次响应读取上限（内存保护）
    MAX_IN_MEMORY_RESPONSE_BYTES: int = 2 * 1024 * 1024  # 2MB

    # 请求缓存预算（避免 HTML 缓存吞掉进程内存）
    CACHE_MEMORY_MAX_ENTRIES: int = 128
    CACHE_MEMORY_MAX_BYTES: int = 32 * 1024 * 1024  # 32MB
    CACHE_MEMORY_BODY_MAX_BYTES: int = 256 * 1024  # 256KB
    CACHE_SQLITE_MAX_ENTRIES: int = 5000
    CACHE_SQLITE_BODY_MAX_BYTES: int = 2 * 1024 * 1024  # 2MB


class ProxyRotationStrategy(Enum):
    """代理轮换策略"""
    ROUND_ROBIN = "round_robin"  # 循环轮换
    RANDOM = "random"  # 随机选择
    SUCCESS_BASED = "success_based"  # 基于成功率


@dataclass
class ProxyConfig:
    """代理配置"""
    # 代理列表
    PROXIES: List[str] = field(default_factory=list)

    # 轮换策略
    ROTATION_STRATEGY: ProxyRotationStrategy = ProxyRotationStrategy.ROUND_ROBIN

    # 代理超时
    PROXY_TIMEOUT: int = 10  # 秒

    # 自动检测失败代理
    AUTO_DETECT_FAILURE: bool = True

    # 失败阈值（超过此值标记为不可用）
    FAILURE_THRESHOLD: int = 3

    # 代理重用次数
    MAX_REUSE: int = 5


@dataclass
class StealthConfig:
    """隐身配置 - 反检测功能"""
    # 启用隐身模式
    ENABLE_STEALTH: bool = True

    # 随机 User-Agent
    RANDOM_USER_AGENT: bool = True

    # User-Agent 列表（Chrome）
    USER_AGENTS: List[str] = field(default_factory=lambda: [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    ])

    # 添加 canvas 指纹噪声
    CANVAS_NOISE: bool = True

    # WebRTC 控制（防止 IP 泄露）
    DISABLE_WEBRTC: bool = True

    # 拦截资源类型
    BLOCK_RESOURCES: bool = True
    BLOCK_IMAGES: bool = True
    BLOCK_FONTS: bool = True
    BLOCK_TRACKERS: bool = True  # 拦截跟踪脚本

    # Cloudflare 自动处理
    AUTO_CLOUDFLARE: bool = True

    # Referer 设置（来自 Google 搜索）
    GOOGLE_REFERER: bool = True

    # 屏幕分辨率随机化
    RANDOM_VIEWPORT: bool = True
    VIEWPORTS: List[dict] = field(default_factory=lambda: [
        {"width": 1920, "height": 1080},
        {"width": 1366, "height": 768},
        {"width": 1536, "height": 864},
        {"width": 1440, "height": 900},
        {"width": 2560, "height": 1440},
    ])

    # 语言设置
    ACCEPT_LANGUAGE: str = "zh-CN,zh;q=0.9,en;q=0.8"

    # 时区设置
    TIMEZONE: str = "Asia/Shanghai"


@dataclass
class AdaptiveParserConfig:
    """自适应解析器配置"""
    # 启用自适应模式
    ENABLE_ADAPTIVE: bool = True

    # 相似度阈值（低于此值认为不匹配）
    SIMILARITY_THRESHOLD: float = 0.6

    # 元素特征权重
    TAG_WEIGHT: float = 0.15       # 标签名权重
    ATTRS_WEIGHT: float = 0.35     # 属性权重
    TEXT_WEIGHT: float = 0.25      # 文本内容权重
    POSITION_WEIGHT: float = 0.25  # 相对位置权重

    # 存储路径
    STORAGE_PATH: str = "./data/element_cache.db"

    # 缓存过期时间（天）
    CACHE_EXPIRY_DAYS: int = 30

    # 最大缓存元素数
    MAX_CACHED_ELEMENTS: int = 10000


@dataclass
class BrowserConfig:
    """浏览器配置"""
    HEADLESS: bool = True
    TIMEOUT: int = 30000  # 毫秒
    WAIT_FOR_NETWORK: bool = True
    BLOCK_IMAGES: bool = True  # 加快速度
    BLOCK_FONTS: bool = True
    USER_AGENT: str = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    MAX_HTML_CHARS: int = 250000
    MAX_CONSOLE_LOGS: int = 50

    # CDP 支持
    CDP_URL: Optional[str] = None  # CDP 端点 URL
    USE_REAL_CHROME: bool = False  # 使用真实 Chrome
    CHROME_PATH: Optional[str] = None  # Chrome 安装路径
    USER_DATA_DIR: Optional[str] = None  # 用户数据目录

    # 隐身模式配置
    stealth_config: StealthConfig = field(default_factory=StealthConfig)

    # 代理配置
    proxy_config: ProxyConfig = field(default_factory=ProxyConfig)


@dataclass
class ServerConfig:
    """服务器配置"""
    HOST: str = "127.0.0.1"
    PORT: int = 8765


# 单例配置
crawler_config = CrawlerConfig()
browser_config = BrowserConfig()
server_config = ServerConfig()
proxy_config = ProxyConfig()
stealth_config = StealthConfig()
adaptive_parser_config = AdaptiveParserConfig()

"""
Request 对象 - 封装爬虫请求

功能：
- 封装 URL、回调、优先级、元数据
- URL 规范化和指纹生成
- 支持请求链和错误处理
"""
import hashlib
import re
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, Callable, List
from urllib.parse import urlparse, urlunparse, parse_qs, urlencode
from datetime import datetime


@dataclass
class Request:
    """
    Request 对象 - 封装单次请求

    Attributes:
        url: 目标 URL
        callback: 回调函数名（用于 Spider 处理响应）
        priority: 请求优先级（数字越小优先级越高）
        meta: 元数据字典，在请求链中传递
        headers: HTTP 请求头
        method: HTTP 方法
        body: 请求体（用于 POST）
        cookies: Cookies
        dont_filter: 是否跳过 URL 去重
        retry_times: 重试次数
        max_retries: 最大重试次数
        proxy: 代理 URL
        session_id: 会话 ID（用于 SessionManager）
        timeout: 请求超时（秒）
    """
    url: str
    callback: str = "parse"
    priority: int = 0
    meta: Dict[str, Any] = field(default_factory=dict)
    headers: Dict[str, str] = field(default_factory=dict)
    method: str = "GET"
    body: Optional[bytes] = None
    cookies: Dict[str, str] = field(default_factory=dict)
    dont_filter: bool = False
    retry_times: int = 0
    max_retries: int = 3
    proxy: Optional[str] = None
    session_id: Optional[str] = None
    timeout: int = 30
    created_at: datetime = field(default_factory=datetime.now)
    fingerprint: str = field(init=False)

    def __post_init__(self):
        # URL 规范化
        self.url = self._normalize_url(self.url)
        # 生成指纹
        self.fingerprint = self._generate_fingerprint()
        # 注入请求 ID 到 meta
        if "request_id" not in self.meta:
            self.meta["request_id"] = self.fingerprint[:16]

    def _normalize_url(self, url: str) -> str:
        """
        规范化 URL
        - 移除片段（# 后面的部分）
        - 规范化查询参数顺序
        - 移除跟踪参数（如 utm_*）
        """
        # 处理相对 URL
        if url.startswith("//"):
            url = "https:" + url

        if not url.startswith(("http://", "https://")):
            url = "https://" + url

        parsed = urlparse(url)

        # 移除片段
        fragment = ""

        # 解析并排序查询参数
        params = parse_qs(parsed.query, keep_blank_values=True)

        # 移除常见的跟踪参数
        tracking_params = [
            "utm_source", "utm_medium", "utm_campaign",
            "utm_term", "utm_content", "fbclid", "gclid",
            "ref", "referer", "source"
        ]
        for param in tracking_params:
            params.pop(param, None)

        # 排序参数
        sorted_query = urlencode(sorted(params.items()), doseq=True)

        # 规范化路径（移除连续的 /）
        path = re.sub(r"/+", "/", parsed.path)

        # 小写主机名
        netloc = parsed.netloc.lower()

        return urlunparse((
            parsed.scheme,
            netloc,
            path,
            parsed.params,
            sorted_query,
            fragment
        ))

    def _generate_fingerprint(self) -> str:
        """
        生成请求指纹（用于去重）
        基于 URL、方法和请求体生成唯一标识
        """
        # 指纹内容：URL + 方法 + 请求体
        content = f"{self.method.upper()}|{self.url}|{self.body.decode() if self.body else ''}"
        return hashlib.sha256(content.encode()).hexdigest()

    def replace(self, **kwargs) -> "Request":
        """
        创建当前请求的副本，并替换指定的属性

        Args:
            **kwargs: 要替换的属性

        Returns:
            新的 Request 对象
        """
        kwargs.setdefault("callback", self.callback)
        kwargs.setdefault("priority", self.priority)
        kwargs.setdefault("meta", dict(self.meta))
        kwargs.setdefault("headers", dict(self.headers))
        kwargs.setdefault("method", self.method)
        kwargs.setdefault("body", self.body)
        kwargs.setdefault("cookies", dict(self.cookies))
        kwargs.setdefault("dont_filter", self.dont_filter)
        kwargs.setdefault("retry_times", self.retry_times)
        kwargs.setdefault("max_retries", self.max_retries)
        kwargs.setdefault("proxy", self.proxy)
        kwargs.setdefault("session_id", self.session_id)
        kwargs.setdefault("timeout", self.timeout)

        return Request(url=kwargs.pop("url", self.url), **kwargs)

    def copy(self) -> "Request":
        """创建深拷贝"""
        return self.replace(
            meta=dict(self.meta),
            headers=dict(self.headers),
            cookies=dict(self.cookies),
        )

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典（用于序列化）"""
        return {
            "url": self.url,
            "callback": self.callback,
            "priority": self.priority,
            "meta": self.meta,
            "headers": self.headers,
            "method": self.method,
            "body": self.body.decode() if self.body else None,
            "cookies": self.cookies,
            "dont_filter": self.dont_filter,
            "retry_times": self.retry_times,
            "max_retries": self.max_retries,
            "proxy": self.proxy,
            "session_id": self.session_id,
            "timeout": self.timeout,
            "fingerprint": self.fingerprint,
            "created_at": self.created_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Request":
        """从字典创建 Request"""
        data = dict(data)  # 创建副本
        data["body"] = data["body"].encode() if data.get("body") else None
        data["created_at"] = datetime.fromisoformat(data["created_at"]) if data.get("created_at") else datetime.now()
        return cls(**data)

    def __repr__(self) -> str:
        return f"<Request {self.method} {self.url[:50]}...>"

    def __eq__(self, other) -> bool:
        if not isinstance(other, Request):
            return False
        return self.fingerprint == other.fingerprint

    def __hash__(self) -> int:
        return hash(self.fingerprint)


@dataclass
class RequestBuilder:
    """
    Request 构建器 - 流式 API 创建请求

    用法:
        request = (RequestBuilder("https://example.com")
                   .with_method("POST")
                   .with_header("User-Agent", "...")
                   .with_body(b"data")
                   .with_priority(10)
                   .build())
    """
    url: str
    _kwargs: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        self._kwargs = {
            "url": self.url,
        }

    def with_callback(self, callback: str) -> "RequestBuilder":
        """设置回调函数名"""
        self._kwargs["callback"] = callback
        return self

    def with_priority(self, priority: int) -> "RequestBuilder":
        """设置优先级"""
        self._kwargs["priority"] = priority
        return self

    def with_meta(self, meta: Dict[str, Any]) -> "RequestBuilder":
        """设置元数据"""
        self._kwargs["meta"] = meta
        return self

    def add_meta(self, key: str, value: Any) -> "RequestBuilder":
        """添加单个元数据"""
        if "meta" not in self._kwargs:
            self._kwargs["meta"] = {}
        self._kwargs["meta"][key] = value
        return self

    def with_headers(self, headers: Dict[str, str]) -> "RequestBuilder":
        """设置请求头"""
        self._kwargs["headers"] = headers
        return self

    def add_header(self, key: str, value: str) -> "RequestBuilder":
        """添加单个请求头"""
        if "headers" not in self._kwargs:
            self._kwargs["headers"] = {}
        self._kwargs["headers"][key] = value
        return self

    def with_method(self, method: str) -> "RequestBuilder":
        """设置 HTTP 方法"""
        self._kwargs["method"] = method.upper()
        return self

    def with_body(self, body: bytes) -> "RequestBuilder":
        """设置请求体"""
        self._kwargs["body"] = body
        return self

    def with_json(self, data: Dict[str, Any]) -> "RequestBuilder":
        """设置 JSON 请求体（自动设置 Content-Type）"""
        import json
        self._kwargs["body"] = json.dumps(data).encode()
        if "headers" not in self._kwargs:
            self._kwargs["headers"] = {}
        self._kwargs["headers"]["Content-Type"] = "application/json"
        return self

    def with_cookies(self, cookies: Dict[str, str]) -> "RequestBuilder":
        """设置 Cookies"""
        self._kwargs["cookies"] = cookies
        return self

    def add_cookie(self, name: str, value: str) -> "RequestBuilder":
        """添加单个 Cookie"""
        if "cookies" not in self._kwargs:
            self._kwargs["cookies"] = {}
        self._kwargs["cookies"][name] = value
        return self

    def dont_filter(self) -> "RequestBuilder":
        """禁用 URL 去重"""
        self._kwargs["dont_filter"] = True
        return self

    def with_retries(self, max_retries: int) -> "RequestBuilder":
        """设置最大重试次数"""
        self._kwargs["max_retries"] = max_retries
        return self

    def with_proxy(self, proxy: str) -> "RequestBuilder":
        """设置代理"""
        self._kwargs["proxy"] = proxy
        return self

    def with_session(self, session_id: str) -> "RequestBuilder":
        """设置会话 ID"""
        self._kwargs["session_id"] = session_id
        return self

    def with_timeout(self, timeout: int) -> "RequestBuilder":
        """设置超时（秒）"""
        self._kwargs["timeout"] = timeout
        return self

    def build(self) -> Request:
        """构建 Request 对象"""
        return Request(**self._kwargs)


def make_request(
    url: str,
    callback: str = "parse",
    priority: int = 0,
    meta: Optional[Dict[str, Any]] = None,
    headers: Optional[Dict[str, str]] = None,
    method: str = "GET",
    body: Optional[bytes] = None,
    cookies: Optional[Dict[str, str]] = None,
    dont_filter: bool = False,
    max_retries: int = 3,
    proxy: Optional[str] = None,
    session_id: Optional[str] = None,
    timeout: int = 30,
) -> Request:
    """
    便捷函数：创建 Request 对象

    Args:
        url: 目标 URL
        callback: 回调函数名
        priority: 优先级
        meta: 元数据
        headers: 请求头
        method: HTTP 方法
        body: 请求体
        cookies: Cookies
        dont_filter: 是否跳过过滤
        max_retries: 最大重试次数
        proxy: 代理
        session_id: 会话 ID
        timeout: 超时（秒）

    Returns:
        Request 对象
    """
    return Request(
        url=url,
        callback=callback,
        priority=priority,
        meta=meta or {},
        headers=headers or {},
        method=method,
        body=body,
        cookies=cookies or {},
        dont_filter=dont_filter,
        max_retries=max_retries,
        proxy=proxy,
        session_id=session_id,
        timeout=timeout,
    )


def make_requests_from_urls(
    urls: List[str],
    callback: str = "parse",
    priority: int = 0,
    **kwargs,
) -> List[Request]:
    """
    便捷函数：从 URL 列表批量创建请求

    Args:
        urls: URL 列表
        callback: 回调函数名
        priority: 优先级
        **kwargs: 其他参数传递给 make_request

    Returns:
        Request 对象列表
    """
    return [
        make_request(url, callback=callback, priority=priority, **kwargs)
        for url in urls
    ]


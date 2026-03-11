"""
Response 对象 - 封装爬虫响应

功能：
- 封装 HTML、状态码、头信息
- 提供便捷的解析方法
- 支持相对 URL 转换
"""
import re
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List, Tuple
from urllib.parse import urljoin, urlparse
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


@dataclass
class Response:
    """
    Response 对象 - 封装单次响应

    Attributes:
        url: 实际响应的 URL（可能有重定向）
        status: HTTP 状态码
        headers: 响应头
        body: 响应体（字节）
        text: 响应体文本（自动解码）
        encoding: 字符编码
        request: 对应的 Request 对象
        cookies: 响应 Cookies
        elapsed: 请求耗时（毫秒）
        timestamp: 响应时间戳
    """
    url: str
    status: int = 200
    headers: Dict[str, str] = field(default_factory=dict)
    body: bytes = b""
    text: str = ""
    encoding: str = "utf-8"
    request: Optional[Any] = None  # Request 对象
    cookies: Dict[str, str] = field(default_factory=dict)
    elapsed: int = 0  # 毫秒
    timestamp: datetime = field(default_factory=datetime.now)

    # 缓存的解析结果
    _soup: Any = field(default=None, repr=False)
    _links: List[Dict[str, str]] = field(default_factory=list)
    _title: str = ""

    def __post_init__(self):
        # 自动解码文本
        if self.body and not self.text:
            self._decode_text()

    def _decode_text(self):
        """解码响应体为文本"""
        # 尝试从 Content-Type 获取编码
        content_type = self.headers.get("Content-Type", "").lower()
        if "charset=" in content_type:
            encoding = content_type.split("charset=")[-1].strip()
        else:
            # 尝试从 HTML meta 标签获取编码
            encoding = self._detect_encoding_from_html()

        if encoding:
            self.encoding = encoding

        # 解码
        try:
            self.text = self.body.decode(self.encoding, errors="replace")
        except (UnicodeDecodeError, LookupError):
            self.text = self.body.decode("utf-8", errors="replace")
            self.encoding = "utf-8"

    def _detect_encoding_from_html(self) -> Optional[str]:
        """从 HTML 检测编码"""
        if not self.body:
            return None

        # 尝试常见编码
        for encoding in ["utf-8", "gbk", "gb2312", "big5", "shift_jis", "euc-jp"]:
            try:
                text = self.body.decode(encoding, errors="ignore")
                # 查找 meta charset
                match = re.search(r'<meta[^>]+charset=["\']?([^"\'>\s]+)', text, re.IGNORECASE)
                if match:
                    return match.group(1)
                # 查找 XML 声明
                match = re.search(r'<\?xml[^>]+encoding=["\']?([^"\'>\s]+)', text, re.IGNORECASE)
                if match:
                    return match.group(1)
            except:
                continue

        return "utf-8"

    @property
    def success(self) -> bool:
        """请求是否成功（2xx 状态码）"""
        return 200 <= self.status < 400

    @property
    def is_redirect(self) -> bool:
        """是否是重定向"""
        return self.status in (301, 302, 303, 307, 308)

    @property
    def redirect_url(self) -> Optional[str]:
        """获取重定向 URL"""
        if self.is_redirect:
            return self.headers.get("Location")
        return None

    @property
    def soup(self):
        """获取 BeautifulSoup 对象（懒加载）"""
        if self._soup is None:
            try:
                from bs4 import BeautifulSoup
                self._soup = BeautifulSoup(self.text, "lxml")
            except Exception as e:
                logger.error(f"Failed to parse HTML: {e}")
                self._soup = None
        return self._soup

    def json(self) -> Any:
        """解析 JSON 响应"""
        import json
        return json.loads(self.text)

    def urljoin(self, url: str) -> str:
        """将相对 URL 转换为绝对 URL"""
        return urljoin(self.url, url)

    def follow(
        self,
        url: str,
        callback: str = "parse",
        priority: int = 0,
        **kwargs,
    ) -> Any:
        """
        从当前响应创建 follow 请求

        Args:
            url: 相对或绝对 URL
            callback: 回调函数名
            priority: 优先级
            **kwargs: 传递给 Request 的其他参数

        Returns:
            Request 对象
        """
        from .request import Request

        absolute_url = self.urljoin(url)
        return Request(
            url=absolute_url,
            callback=callback,
            priority=priority,
            **kwargs,
        )

    def follow_all(
        self,
        urls: List[str],
        callback: str = "parse",
        priority: int = 0,
        **kwargs,
    ) -> List[Any]:
        """
        批量创建 follow 请求

        Args:
            urls: URL 列表
            callback: 回调函数名
            priority: 优先级
            **kwargs: 传递给 Request 的其他参数

        Returns:
            Request 对象列表
        """
        return [
            self.follow(url, callback=callback, priority=priority, **kwargs)
            for url in urls
        ]

    def css(self, selector: str) -> List[Any]:
        """
        CSS 选择器查询

        Args:
            selector: CSS 选择器

        Returns:
            匹配的元素列表
        """
        if not self.soup:
            return []
        return self.soup.select(selector)

    def xpath(self, xpath: str) -> List[Any]:
        """
        XPath 查询

        Args:
            xpath: XPath 表达式

        Returns:
            匹配的元素列表
        """
        if not self.soup:
            return []
        try:
            return self.soup.xpath(xpath)
        except Exception as e:
            logger.error(f"XPath query failed: {e}")
            return []

    def get_title(self) -> str:
        """获取页面标题"""
        if self._title:
            return self._title

        if self.soup:
            title_tag = self.soup.find("title")
            if title_tag:
                self._title = title_tag.get_text(strip=True)
                return self._title

            h1 = self.soup.find("h1")
            if h1:
                self._title = h1.get_text(strip=True)
                return self._title

        return ""

    def get_links(self, internal_only: bool = False) -> List[Dict[str, str]]:
        """
        获取所有链接

        Args:
            internal_only: 是否仅返回内部链接

        Returns:
            链接信息列表
        """
        if self._links and not internal_only:
            return self._links

        if not self.soup:
            return []

        links = []
        parsed_base = urlparse(self.url)

        for a in self.soup.find_all("a", href=True):
            href = a.get("href", "").strip()
            if not href or href.startswith(("#", "javascript:", "mailto:")):
                continue

            absolute_url = self.urljoin(href)

            # 检查是否内部链接
            if internal_only:
                parsed_link = urlparse(absolute_url)
                if parsed_link.netloc != parsed_base.netloc:
                    continue

            link_data = {
                "href": absolute_url,
                "text": a.get_text(strip=True)[:100],
            }

            if a.get("title"):
                link_data["title"] = a["title"]

            links.append(link_data)

        if not internal_only:
            self._links = links

        return links

    def get_text(self, min_length: int = 20) -> str:
        """
        获取主要文本内容

        Args:
            min_length: 最小行长度

        Returns:
            清理后的文本
        """
        if not self.soup:
            return ""

        # 移除不需要的元素
        for tag in self.soup(["script", "style", "noscript", "iframe", "nav", "footer", "header"]):
            tag.decompose()

        # 获取文章区域
        article = self.soup.find("article") or self.soup.find("main")

        if article:
            text = article.get_text(separator="\n", strip=True)
        else:
            text = self.soup.get_text(separator="\n", strip=True)

        # 清理文本
        lines = [line.strip() for line in text.split("\n") if len(line.strip()) >= min_length]
        return "\n".join(lines)

    def get_metadata(self) -> Dict[str, str]:
        """获取页面元数据"""
        if not self.soup:
            return {}

        metadata = {}

        # meta 标签
        for meta in self.soup.find_all("meta"):
            name = meta.get("name") or meta.get("property")
            content = meta.get("content")
            if name and content:
                metadata[name] = content

        return metadata

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "url": self.url,
            "status": self.status,
            "headers": self.headers,
            "text": self.text[:5000],  # 限制长度
            "encoding": self.encoding,
            "cookies": self.cookies,
            "elapsed": self.elapsed,
            "timestamp": self.timestamp.isoformat(),
            "title": self.get_title(),
            "links_count": len(self.get_links()),
        }

    def __repr__(self) -> str:
        return f"<Response {self.status} {self.url[:50]}...>"

    def __str__(self) -> str:
        return f"<Response {self.status} {self.url}>"


@dataclass
class TextResponse(Response):
    """
    文本响应 - 用于非 HTML 内容
    继承自 Response，禁用 HTML 解析
    """

    @property
    def soup(self):
        """文本响应不支持 HTML 解析"""
        return None

    def get_links(self, **kwargs) -> List:
        """文本响应没有链接"""
        return []

    def get_title(self) -> str:
        """文本响应没有标题"""
        return ""


@dataclass
class JsonResponse(Response):
    """
    JSON 响应 - 用于 JSON API
    继承自 Response，提供便捷的 JSON 解析
    """
    _json_data: Any = field(default=None, repr=False)

    def json(self) -> Any:
        """解析并缓存 JSON 数据"""
        if self._json_data is None:
            import json
            self._json_data = json.loads(self.text)
        return self._json_data

    def get(self, key: str, default: Any = None) -> Any:
        """获取 JSON 字段"""
        data = self.json()
        if isinstance(data, dict):
            return data.get(key, default)
        return default

    @property
    def soup(self):
        """JSON 响应不支持 HTML 解析"""
        return None


def create_response(
    url: str,
    body: bytes,
    status: int = 200,
    headers: Optional[Dict[str, str]] = None,
    encoding: str = "utf-8",
    request: Optional[Any] = None,
    cookies: Optional[Dict[str, str]] = None,
    elapsed: int = 0,
    response_type: str = "html",
) -> Response:
    """
    便捷函数：创建 Response 对象

    Args:
        url: 响应 URL
        body: 响应体
        status: 状态码
        headers: 响应头
        encoding: 编码
        request: 对应的 Request
        cookies: Cookies
        elapsed: 耗时
        response_type: 响应类型（html/json/text）

    Returns:
        Response 对象
    """
    headers = headers or {}
    cookies = cookies or {}

    if response_type == "json":
        return JsonResponse(
            url=url,
            status=status,
            headers=headers,
            body=body,
            encoding=encoding,
            request=request,
            cookies=cookies,
            elapsed=elapsed,
        )
    elif response_type == "text":
        return TextResponse(
            url=url,
            status=status,
            headers=headers,
            body=body,
            encoding=encoding,
            request=request,
            cookies=cookies,
            elapsed=elapsed,
        )
    else:
        return Response(
            url=url,
            status=status,
            headers=headers,
            body=body,
            encoding=encoding,
            request=request,
            cookies=cookies,
            elapsed=elapsed,
        )


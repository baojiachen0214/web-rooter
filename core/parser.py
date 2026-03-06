"""
内容解析器 - 提取结构化数据
"""
import re
import json
from dataclasses import dataclass, field
from typing import Optional, Dict, List, Any, Tuple
from bs4 import BeautifulSoup, Tag
from urllib.parse import urljoin, urlparse
import logging

logger = logging.getLogger(__name__)


@dataclass
class ExtractedData:
    """提取的数据"""
    url: str
    title: str = ""
    text: str = ""
    links: List[Dict[str, str]] = field(default_factory=list)
    images: List[Dict[str, str]] = field(default_factory=list)
    metadata: Dict[str, str] = field(default_factory=dict)
    structured: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "url": self.url,
            "title": self.title,
            "text": self.text,
            "links": self.links,
            "images": self.images,
            "metadata": self.metadata,
            "structured": self.structured,
        }


@dataclass
class Link:
    """链接信息"""
    href: str
    text: str
    title: Optional[str] = None
    rel: Optional[str] = None


@dataclass
class Article:
    """文章信息"""
    title: str
    content: str
    author: Optional[str] = None
    published_date: Optional[str] = None
    image: Optional[str] = None


class Parser:
    """HTML 解析器"""

    def __init__(self):
        self.soup: Optional[BeautifulSoup] = None
        self.base_url: str = ""

    def parse(self, html: str, url: str = "") -> "Parser":
        """解析 HTML"""
        self.soup = BeautifulSoup(html, "lxml")
        self.base_url = url
        return self

    def extract(self) -> ExtractedData:
        """提取所有数据"""
        if not self.soup:
            raise ValueError("No HTML parsed")

        return ExtractedData(
            url=self.base_url,
            title=self.get_title(),
            text=self.get_text(),
            links=self.get_links(),
            images=self.get_images(),
            metadata=self.get_metadata(),
            structured=self.get_structured_data(),
        )

    def get_title(self) -> str:
        """获取页面标题"""
        # 尝试多个来源
        title = ""

        # 1. <title> 标签
        title_tag = self.soup.find("title")
        if title_tag:
            title = title_tag.get_text(strip=True)

        # 2. <h1> 标签
        if not title:
            h1 = self.soup.find("h1")
            if h1:
                title = h1.get_text(strip=True)

        # 3. og:title
        if not title:
            og_title = self.soup.find("meta", property="og:title")
            if og_title and og_title.get("content"):
                title = og_title["content"]

        return title

    def get_text(self, min_length: int = 20) -> str:
        """获取主要文本内容"""
        # 移除不需要元素
        for tag in self.soup(["script", "style", "noscript", "iframe", "nav", "footer", "header"]):
            tag.decompose()

        # 获取文章区域（如果有）
        article = self.soup.find("article") or self.soup.find("main") or self.soup.find(class_=re.compile(r"(article|content|post|main)"))

        if article:
            text = article.get_text(separator="\n", strip=True)
        else:
            text = self.soup.get_text(separator="\n", strip=True)

        # 清理文本
        lines = [line.strip() for line in text.split("\n") if len(line.strip()) >= min_length]
        return "\n".join(lines)

    def get_links(self, internal_only: bool = False) -> List[Dict[str, str]]:
        """获取所有链接"""
        links = []
        parsed_base = urlparse(self.base_url) if self.base_url else None

        for a in self.soup.find_all("a", href=True):
            href = a.get("href", "").strip()
            if not href or href.startswith(("#", "javascript:", "mailto:")):
                continue

            # 转换为绝对 URL
            absolute_url = urljoin(self.base_url, href) if self.base_url else href

            # 检查是否内部链接
            if internal_only and parsed_base:
                parsed_link = urlparse(absolute_url)
                if parsed_link.netloc != parsed_base.netloc:
                    continue

            link_data = {
                "href": absolute_url,
                "text": a.get_text(strip=True)[:100],
            }

            if a.get("title"):
                link_data["title"] = a["title"]
            if a.get("rel"):
                link_data["rel"] = " ".join(a["rel"])

            links.append(link_data)

        return links

    def get_images(self, min_width: int = 0) -> List[Dict[str, str]]:
        """获取所有图片"""
        images = []

        for img in self.soup.find_all("img"):
            src = img.get("src") or img.get("data-src")
            if not src:
                continue

            img_data = {
                "src": urljoin(self.base_url, src) if self.base_url else src,
            }

            if img.get("alt"):
                img_data["alt"] = img["alt"]
            if img.get("width"):
                img_data["width"] = img["width"]
            if img.get("height"):
                img_data["height"] = img["height"]

            images.append(img_data)

        return images

    def get_metadata(self) -> Dict[str, str]:
        """获取页面元数据"""
        metadata = {}

        # meta 标签
        for meta in self.soup.find_all("meta"):
            name = meta.get("name") or meta.get("property")
            content = meta.get("content")
            if name and content:
                metadata[name] = content

        # JSON-LD
        for ld in self.soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(ld.string)
                metadata["json_ld"] = data
            except (json.JSONDecodeError, TypeError):
                continue

        return metadata

    def get_structured_data(self) -> Optional[Dict[str, Any]]:
        """获取结构化数据（JSON-LD）"""
        structured = {}

        for ld in self.soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(ld.string)
                if isinstance(data, list):
                    for item in data:
                        if item.get("@type"):
                            structured[item["@type"]] = item
                elif data.get("@type"):
                    structured[data["@type"]] = data
            except (json.JSONDecodeError, TypeError):
                continue

        return structured if structured else None

    def extract_article(self) -> Optional[Article]:
        """提取文章信息"""
        # 查找文章区域
        article_tags = self.soup.find_all(["article", "main"])
        article_content = None

        for tag in article_tags:
            article_content = tag
            break

        if not article_content:
            # 尝试通过 class 查找
            article_content = self.soup.find(class_=re.compile(r"(article|post|content|entry)"))

        if not article_content:
            return None

        # 清理
        for tag in article_content(["script", "style", "nav", "footer", "header", "aside"]):
            tag.decompose()

        return Article(
            title=self.get_title(),
            content=article_content.get_text(separator="\n", strip=True),
            author=self._extract_author(),
            published_date=self._extract_date(),
            image=self._extract_main_image(),
        )

    def _extract_author(self) -> Optional[str]:
        """提取作者"""
        patterns = [
            self.soup.find("meta", {"name": "author"}),
            self.soup.find(class_=re.compile(r"author|byline")),
        ]

        for p in patterns:
            if p:
                text = p.get("content") or p.get_text(strip=True)
                if text:
                    return text
        return None

    def _extract_date(self) -> Optional[str]:
        """提取日期"""
        patterns = [
            self.soup.find("meta", {"property": "article:published_time"}),
            self.soup.find("time"),
            self.soup.find(class_=re.compile(r"date|time|published")),
        ]

        for p in patterns:
            if p:
                text = p.get("content") or p.get("datetime") or p.get_text(strip=True)
                if text:
                    return text[:10]  # 返回 YYYY-MM-DD
        return None

    def _extract_main_image(self) -> Optional[str]:
        """提取主要图片"""
        # og:image
        og_image = self.soup.find("meta", property="og:image")
        if og_image and og_image.get("content"):
            return og_image["content"]

        # 查找最大的图片
        images = self.get_images()
        if images:
            return images[0].get("src")

        return None

    def find_all(self, name=None, attrs=None, class_=None, text=None) -> List[Tag]:
        """查找所有匹配元素"""
        return self.soup.find_all(name=name, attrs=attrs, class_=class_, string=text)

    def find(self, name=None, attrs=None, class_=None, text=None) -> Optional[Tag]:
        """查找第一个匹配元素"""
        return self.soup.find(name=name, attrs=attrs, class_=class_, string=text)

    def select(self, selector: str) -> List[Tag]:
        """CSS 选择器"""
        return self.soup.select(selector)

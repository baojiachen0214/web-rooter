"""
内容解析器 - 提取结构化数据

注意：ElementFeature 已从 core.element_storage 导入
"""
import re
import json
import os
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Optional, Dict, List, Any, Tuple
from bs4 import BeautifulSoup, Tag
from urllib.parse import urljoin, urlparse
import logging

# 从 element_storage 导入 ElementFeature（带 SQLite 支持）
from core.element_storage import (
    ElementStorageSystem,
    ElementFeature,
    compute_text_hash,
    get_parent_path,
    get_sibling_index,
    generate_xpath,
    element_to_feature,
)

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

    def select_one(self, selector: str) -> Optional[Tag]:
        """CSS 选择器（返回第一个匹配项）"""
        return self.soup.select_one(selector)

    def generate_css_selector(self, element: Tag) -> str:
        """为元素生成 CSS 选择器"""
        if not element or not element.name:
            return ""

        parts = []
        current = element

        while current and hasattr(current, "name") and current.name:
            selector = current.name

            # 添加 id
            if current.get("id"):
                selector += f"#{current['id']}"
                parts.insert(0, selector)
                break

            # 添加 class
            classes = current.get("class", [])
            if classes:
                selector += "." + ".".join(classes[:2])  # 最多两个 class

            # 添加 nth-child 如果兄弟元素中有同名标签
            parent = current.parent
            if parent:
                siblings = [s for s in parent.children
                           if hasattr(s, "name") and s.name == current.name]
                if len(siblings) > 1:
                    index = siblings.index(current) + 1
                    selector += f":nth-child({index})"

            parts.insert(0, selector)
            current = current.parent

        return " > ".join(parts)

    def generate_xpath(self, element: Tag) -> str:
        """为元素生成 XPath"""
        if not element or not element.name:
            return ""

        path = []
        current = element

        while current and hasattr(current, "name") and current.name:
            parent = current.parent
            if parent:
                siblings = [s for s in parent.children
                           if hasattr(s, "name") and s.name == current.name]
                if len(siblings) > 1:
                    index = siblings.index(current) + 1
                    path.insert(0, f"{current.name}[{index}]")
                else:
                    path.insert(0, current.name)
            else:
                path.insert(0, current.name)
            current = parent

        return "/" + "/".join(path)

    def generate_full_css_selector(self, element: Tag) -> str:
        """
        生成元素的完整 CSS 选择器路径 (从根到元素)

        Args:
            element: BeautifulSoup Tag 元素

        Returns:
            完整的 CSS 选择器路径

        用法:
            selector = parser.generate_full_css_selector(element)
            # 返回：html > body > div.container > main > article > h1
        """
        if not element or not element.name:
            return ""

        parts = []
        current = element

        while current and hasattr(current, "name") and current.name:
            selector = current.name

            # 添加 id (如果有)
            if current.get("id"):
                selector += f"#{current['id']}"
                parts.insert(0, selector)
                break

            # 添加 class (如果有，最多两个)
            classes = current.get("class", [])
            if classes:
                # 过滤无效的 class 名
                valid_classes = [c for c in classes if c and isinstance(c, str)]
                if valid_classes:
                    selector += "." + ".".join(valid_classes[:2])

            # 添加 nth-child 如果兄弟元素中有同名标签
            parent = current.parent
            if parent:
                siblings = [s for s in parent.children
                           if hasattr(s, "name") and s.name == current.name]
                if len(siblings) > 1:
                    index = siblings.index(current) + 1
                    selector += f":nth-child({index})"

            parts.insert(0, selector)
            current = current.parent

        return " > ".join(parts)

    def generate_full_xpath_selector(
        self,
        element: Tag,
        absolute: bool = True,
    ) -> str:
        """
        生成元素的完整 XPath 选择器路径

        Args:
            element: BeautifulSoup Tag 元素
            absolute: 是否生成绝对路径 (从根开始)

        Returns:
            完整的 XPath 选择器

        用法:
            # 绝对路径
            xpath = parser.generate_full_xpath_selector(element)
            # 返回：/html/body/div[@class='container']/main/article[2]/h1

            # 相对路径
            xpath = parser.generate_full_xpath_selector(element, absolute=False)
            # 返回：//article[@class='post']/h1
        """
        if not element or not element.name:
            return ""

        path = []
        current = element

        while current and hasattr(current, "name") and current.name:
            part = current.name

            # 添加属性条件
            if current.get("id"):
                part += f"[@id='{current['id']}']"
            elif current.get("class"):
                classes = current.get("class", [])
                valid_classes = [c for c in classes if c and isinstance(c, str)]
                if valid_classes:
                    # 使用 contains 匹配 class
                    class_str = " ".join(valid_classes)
                    part += f"[contains(concat(' ', normalize-space(@class), ' '), ' {class_str} ')]"

            # 添加索引如果兄弟元素中有同名标签
            parent = current.parent
            if parent:
                siblings = [s for s in parent.children
                           if hasattr(s, "name") and s.name == current.name]
                if len(siblings) > 1:
                    index = siblings.index(current) + 1
                    part += f"[{index}]"

            path.insert(0, part)
            current = current.parent

            # 相对路径：找到第一个有唯一标识的祖先后停止
            if not absolute and len(path) >= 2:
                last_part = path[-1]
                if "[" in last_part:  # 有属性条件
                    break

        if absolute:
            return "/" + "/".join(path)
        else:
            return "//" + "/".join(path[len(path)-min(len(path), 3):])

    def find_by_text(
        self,
        text: str,
        exact: bool = False,
        case_sensitive: bool = False,
    ) -> Optional[Tag]:
        """
        根据文本内容查找元素

        Args:
            text: 要查找的文本
            exact: 是否精确匹配
            case_sensitive: 是否区分大小写

        Returns:
            匹配的 Tag 元素或 None

        用法:
            # 模糊匹配
            element = parser.find_by_text("点击这里")

            # 精确匹配
            element = parser.find_by_text("Submit", exact=True)

            # 区分大小写
            element = parser.find_by_text("PYTHON", case_sensitive=True)
        """
        if not self.soup:
            return None

        # 查找所有包含文本的元素
        for tag in self.soup.find_all(string=True):
            tag_text = str(tag).strip()

            # 大小写处理
            search_text = text if case_sensitive else text.lower()
            compare_text = tag_text if case_sensitive else tag_text.lower()

            # 匹配
            if exact:
                if compare_text == search_text:
                    return tag.parent
            else:
                if search_text in compare_text:
                    return tag.parent

        return None

    def find_all_by_text(
        self,
        text: str,
        exact: bool = False,
        case_sensitive: bool = False,
    ) -> List[Tag]:
        """
        根据文本内容查找所有匹配元素

        Args:
            text: 要查找的文本
            exact: 是否精确匹配
            case_sensitive: 是否区分大小写

        Returns:
            匹配的 Tag 元素列表

        用法:
            # 查找所有包含"登录"的链接
            links = parser.find_all_by_text("登录")
        """
        if not self.soup:
            return []

        results = []

        # 查找所有包含文本的元素
        for tag in self.soup.find_all(string=True):
            tag_text = str(tag).strip()

            # 大小写处理
            search_text = text if case_sensitive else text.lower()
            compare_text = tag_text if case_sensitive else tag_text.lower()

            # 匹配
            if exact:
                if compare_text == search_text:
                    results.append(tag.parent)
            else:
                if search_text in compare_text:
                    results.append(tag.parent)

        return results

    def find_by_regex(
        self,
        pattern: str,
        name: Optional[str] = None,
    ) -> Optional[Tag]:
        """
        根据正则表达式查找元素

        Args:
            pattern: 正则表达式
            name: 标签名限制

        Returns:
            匹配的 Tag 元素或 None
        """
        if not self.soup:
            return None

        import re
        regex = re.compile(pattern, re.IGNORECASE)

        # 查找文本
        for tag in self.soup.find_all(string=regex):
            if name is None or (tag.parent and tag.parent.name == name):
                return tag.parent

        return None

    def find_all_by_regex(
        self,
        pattern: str,
        name: Optional[str] = None,
    ) -> List[Tag]:
        """
        根据正则表达式查找所有匹配元素

        Args:
            pattern: 正则表达式
            name: 标签名限制

        Returns:
            匹配的 Tag 元素列表
        """
        if not self.soup:
            return []

        import re
        regex = re.compile(pattern, re.IGNORECASE)
        results = []

        for tag in self.soup.find_all(string=regex):
            if name is None or (tag.parent and tag.parent.name == name):
                results.append(tag.parent)

        return results


# 注意：ElementFeature 已移动到 core.element_storage 模块
# 并从上方导入，避免重复定义
class AdaptiveParser(Parser):
    """
    自适应解析器 - 当选择器失效时自动找到相似元素


    功能：
    - 保存首次成功提取的元素特征
    - 当原始选择器失败时，计算相似度找到最佳匹配
    - 无需 AI，使用确定性算法
    - SQLite 持久化支持（跨会话重用特征）
    """

    def __init__(
        self,
        adaptive: bool = True,
        similarity_threshold: float = 0.6,
        tag_weight: float = 0.15,
        attrs_weight: float = 0.35,
        text_weight: float = 0.25,
        position_weight: float = 0.25,
        db_path: Optional[str] = None,
        use_db: bool = True,
        feature_cache_max_entries: Optional[int] = None,
    ):
        super().__init__()
        self.adaptive = adaptive
        self.similarity_threshold = similarity_threshold
        self.weights = {
            "tag": tag_weight,
            "attrs": attrs_weight,
            "text": text_weight,
            "position": position_weight,
        }
        self._feature_cache_max_entries = max(
            1,
            int(
                feature_cache_max_entries
                or os.getenv("WEB_ROOTER_ADAPTIVE_FEATURE_CACHE_MAX", "512")
                or 512
            ),
        )
        self._feature_cache: "OrderedDict[str, ElementFeature]" = OrderedDict()

        # SQLite 元素存储
        self._element_storage: Optional[ElementStorageSystem] = None
        self._use_db = use_db
        self._db_path = db_path

        if use_db:
            try:
                self._element_storage = ElementStorageSystem(db_path=db_path)
                logger.info(f"AdaptiveParser initialized with SQLite storage: {db_path}")
            except Exception as e:
                logger.warning(f"Failed to initialize element storage: {e}")
                self._use_db = False

    def parse(self, html: str, url: str = "") -> "AdaptiveParser":
        """解析 HTML"""
        super().parse(html, url)
        return self

    def select_adaptive(self, selector: str, auto_save: bool = True) -> List[Tag]:
        """
        自适应选择器 - 当选择器失效时尝试找到相似元素

        Args:
            selector: CSS 选择器
            auto_save: 是否自动保存成功找到的元素特征

        Returns:
            匹配的元素列表
        """
        if not self.adaptive:
            return self.select(selector)

        # 首先尝试原始选择器
        results = self.select(selector)

        if results:
            # 成功找到，保存特征
            if auto_save:
                feature = element_to_feature(results[0], selector, self.base_url)
                self._cache_put(selector, feature)
                # 保存到数据库
                self._save_feature_to_db(selector, feature)
            return results

        # 选择器失效，尝试自适应匹配
        logger.info(f"Selector '{selector}' failed, trying adaptive match")

        # 先从数据库加载特征
        cached_feature = self._load_feature_from_db(selector)
        if not cached_feature:
            # 回退到内存缓存
            cached_feature = self._cache_get(selector)
        else:
            # DB 回填到内存 LRU，减少重复 IO
            self._cache_put(selector, cached_feature)

        if not cached_feature:
            logger.warning(f"No cached feature for selector '{selector}'")
            return []

        # 找到最相似的元素
        best_match, similarity = self._find_similar_element(cached_feature)

        if best_match and similarity >= self.similarity_threshold:
            logger.info(f"Found adaptive match with similarity {similarity:.2f}")
            # 更新数据库中的成功率
            self._update_feature_success_db(selector, True)
            return [best_match]

        logger.warning(f"No similar element found (max similarity: {similarity:.2f})")
        self._update_feature_success_db(selector, False)
        return []

    def find_adaptive(
        self,
        name=None,
        attrs=None,
        class_=None,
        text=None,
    ) -> Optional[Tag]:
        """自适应查找元素"""
        if not self.adaptive:
            return self.find(name=name, attrs=attrs, class_=class_, text=text)

        # 构建选择器
        selector = self._build_selector(name, attrs, class_)
        results = self.select_adaptive(selector)

        return results[0] if results else None

    def _find_similar_element(
        self,
        feature: ElementFeature,
    ) -> Tuple[Optional[Tag], float]:
        """找到最相似的元素"""
        best_match = None
        best_similarity = 0.0

        # 查找所有同标签名的元素
        candidates = self.soup.find_all(feature.tag_name)

        for candidate in candidates:
            candidate_feature = ElementFeature.from_element(candidate)
            similarity = self._compute_similarity(feature, candidate_feature)

            if similarity > best_similarity:
                best_similarity = similarity
                best_match = candidate

        return best_match, best_similarity

    def _compute_similarity(
        self,
        f1: ElementFeature,
        f2: ElementFeature,
    ) -> float:
        """计算两个元素特征的相似度"""
        scores = {
            "tag": self._tag_similarity(f1, f2),
            "attrs": self._attrs_similarity(f1, f2),
            "text": self._text_similarity(f1, f2),
            "position": self._position_similarity(f1, f2),
        }

        total = sum(
            scores[k] * self.weights[k]
            for k in self.weights
        )

        return total

    def _tag_similarity(self, f1: ElementFeature, f2: ElementFeature) -> float:
        """标签名相似度"""
        return 1.0 if f1.tag_name == f2.tag_name else 0.0

    def _attrs_similarity(
        self,
        f1: ElementFeature,
        f2: ElementFeature,
    ) -> float:
        """属性相似度"""
        if not f1.attributes and not f2.attributes:
            return 1.0

        all_keys = set(f1.attributes.keys()) | set(f2.attributes.keys())
        if not all_keys:
            return 1.0

        matches = 0
        for key in all_keys:
            v1 = f1.attributes.get(key, "")
            v2 = f2.attributes.get(key, "")
            if v1 == v2:
                matches += 1
            elif v1 in v2 or v2 in v1:
                matches += 0.5

        return matches / len(all_keys)

    def _text_similarity(
        self,
        f1: ElementFeature,
        f2: ElementFeature,
    ) -> float:
        """文本内容相似度"""
        if not f1.text_content and not f2.text_content:
            return 1.0

        # 使用哈希快速比较
        if f1.text_hash and f2.text_hash:
            if f1.text_hash == f2.text_hash:
                return 1.0

        # 计算文本重叠度
        t1 = f1.text_content.lower().split()
        t2 = f2.text_content.lower().split()

        if not t1 or not t2:
            return 0.5

        intersection = set(t1) & set(t2)
        union = set(t1) | set(t2)

        if not union:
            return 1.0

        return len(intersection) / len(union)

    def _position_similarity(
        self,
        f1: ElementFeature,
        f2: ElementFeature,
    ) -> float:
        """位置相似度"""
        score = 0.0

        # 父路径相似度
        if f1.parent_path and f2.parent_path:
            p1 = f1.parent_path.split(" > ")
            p2 = f2.parent_path.split(" > ")

            if p1 == p2:
                score += 0.5
            elif len(p1) == len(p2):
                score += 0.3

            # 共同路径长度
            common = 0
            for a, b in zip(p1, p2):
                if a == b:
                    common += 1
                else:
                    break
            score += 0.2 * (common / max(len(p1), len(p2)))

        # 兄弟索引相似度
        if f1.sibling_index == f2.sibling_index:
            score += 0.3
        elif abs(f1.sibling_index - f2.sibling_index) <= 1:
            score += 0.15

        return score

    def _build_selector(
        self,
        name=None,
        attrs=None,
        class_=None,
    ) -> str:
        """构建 CSS 选择器"""
        parts = []

        if name:
            parts.append(name)

        if class_:
            if isinstance(class_, str):
                parts.append(f".{class_}")
            elif isinstance(class_, list):
                parts.append(".".join(class_))
            elif hasattr(class_, "__iter__"):
                parts.append(".".join(str(c) for c in class_))

        if attrs:
            for key, value in attrs.items():
                if value is None:
                    parts.append(f"[{key}]")
                else:
                    parts.append(f"[{key}='{value}']")

        return "".join(parts)

    def save_feature(self, selector: str, element: Tag):
        """手动保存元素特征"""
        feature = element_to_feature(element, selector, self.base_url)
        self._cache_put(selector, feature)
        self._save_feature_to_db(selector, feature)

    def clear_cache(self):
        """清除特征缓存"""
        self._feature_cache.clear()

    def _cache_get(self, selector: str) -> Optional[ElementFeature]:
        feature = self._feature_cache.get(selector)
        if feature is None:
            return None
        self._feature_cache.move_to_end(selector)
        return feature

    def _cache_put(self, selector: str, feature: ElementFeature) -> None:
        if selector in self._feature_cache:
            self._feature_cache.pop(selector, None)
        self._feature_cache[selector] = feature
        while len(self._feature_cache) > self._feature_cache_max_entries:
            self._feature_cache.popitem(last=False)

    # ==================== SQLite 持久化方法 ====================

    def _save_feature_to_db(self, selector: str, feature: ElementFeature):
        """保存特征到数据库"""
        if not self._use_db or not self._element_storage:
            return

        try:
            self._element_storage.save_feature(feature)
        except Exception as e:
            logger.debug(f"Failed to save feature to DB: {e}")

    def _load_feature_from_db(self, selector: str) -> Optional[ElementFeature]:
        """从数据库加载特征"""
        if not self._use_db or not self._element_storage:
            return None

        try:
            features = self._element_storage.get_features(self.base_url, selector)
            if features:
                # 返回成功率最高的特征
                return features[0]
        except Exception as e:
            logger.debug(f"Failed to load feature from DB: {e}")

        return None

    def _update_feature_success_db(self, selector: str, success: bool):
        """更新特征成功率"""
        if not self._use_db or not self._element_storage:
            return

        try:
            features = self._element_storage.get_features(self.base_url, selector)
            if features:
                self._element_storage.update_access(features[0], success)
        except Exception as e:
            logger.debug(f"Failed to update feature success in DB: {e}")

    def get_storage_stats(self) -> Optional[Dict[str, Any]]:
        """获取存储统计信息"""
        if not self._use_db or not self._element_storage:
            return None

        try:
            return self._element_storage.get_stats()
        except Exception as e:
            logger.error(f"Failed to get storage stats: {e}")
            return None

    async def close(self):
        """关闭解析器（释放数据库连接）"""
        if self._element_storage:
            self._element_storage.close()
            self._element_storage = None

    def __enter__(self) -> "AdaptiveParser":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


class AttributesHandler:
    """
    属性处理器 - 处理和提取元素属性

    """

    def __init__(self, element: Tag):
        self.element = element
        self._attrs = element.attrs if element else {}

    def get(self, name: str, default: Any = None) -> Any:
        """获取属性值"""
        return self._attrs.get(name, default)

    def has(self, name: str) -> bool:
        """检查是否有某个属性"""
        return name in self._attrs

    def all(self) -> Dict[str, Any]:
        """获取所有属性"""
        return dict(self._attrs)

    def get_href(self, absolute: bool = False, base_url: str = "") -> Optional[str]:
        """获取 href 属性"""
        href = self._attrs.get("href")
        if href and absolute and base_url:
            from urllib.parse import urljoin
            return urljoin(base_url, href)
        return href

    def get_src(self, absolute: bool = False, base_url: str = "") -> Optional[str]:
        """获取 src 属性"""
        src = self._attrs.get("src") or self._attrs.get("data-src")
        if src and absolute and base_url:
            from urllib.parse import urljoin
            return urljoin(base_url, src)
        return src

    def get_class(self) -> List[str]:
        """获取 class 属性"""
        cls = self._attrs.get("class", [])
        if isinstance(cls, str):
            return cls.split()
        return list(cls) if cls else []

    def get_data_attrs(self) -> Dict[str, str]:
        """获取所有 data-* 属性"""
        return {
            k.replace("data-", ""): v
            for k, v in self._attrs.items()
            if k.startswith("data-")
        }

    def get_aria_attrs(self) -> Dict[str, str]:
        """获取所有 aria-* 属性"""
        return {
            k.replace("aria-", ""): v
            for k, v in self._attrs.items()
            if k.startswith("aria-")
        }

    def matches_selector(self, selector: str) -> bool:
        """检查元素是否匹配选择器"""
        try:
            from bs4 import CSSSelectors
            soup = self.element.find_parent() if self.element.parent else self.element
            if soup:
                return self.element in soup.select(selector)
            return False
        except Exception:
            return False


class TextHandler:
    """
    文本处理器 - 处理和提取元素文本

    """

    def __init__(self, element: Tag):
        self.element = element

    def get(self, strip: bool = True, separator: str = "") -> str:
        """获取完整文本"""
        if not self.element:
            return ""
        return self.element.get_text(strip=strip, separator=separator)

    def get_all(self, strip: bool = True) -> List[str]:
        """获取所有文本节点"""
        if not self.element:
            return []
        return [
            str(t).strip() if strip else str(t)
            for t in self.element.find_all(string=True, recursive=False)
        ]

    def find(self, pattern, regex: bool = False) -> List[str]:
        """查找匹配的文本"""
        import re
        if not self.element:
            return []

        results = []
        for text in self.element.find_all(string=True):
            text_str = str(text).strip()
            if regex:
                if re.search(pattern, text_str):
                    results.append(text_str)
            else:
                if pattern in text_str:
                    results.append(text_str)
        return results

    def get_first(self, default: str = "") -> str:
        """获取第一个非空文本节点"""
        texts = self.get_all(strip=True)
        return next((t for t in texts if t), default)

    def normalize(self, whitespace: bool = True) -> str:
        """归一化文本（移除多余空白）"""
        text = self.get(strip=False)
        if whitespace:
            return " ".join(text.split())
        return text

    def get_int(self, default: int = 0) -> int:
        """提取整数"""
        import re
        text = self.normalize()
        match = re.search(r"-?\d+", text)
        return int(match.group()) if match else default

    def get_float(self, default: float = 0.0) -> float:
        """提取浮点数"""
        import re
        text = self.normalize()
        match = re.search(r"-?\d+\.?\d*", text)
        return float(match.group()) if match else default

    def get_number(self, default: float = 0.0) -> float:
        """提取数字（支持百分比、货币等）"""
        import re
        text = self.normalize()

        # 移除货币符号
        text = re.sub(r"[$¥€£]", "", text)
        # 移除百分比
        match = re.search(r"-?\d+\.?\d*", text)
        value = float(match.group()) if match else default

        if "%" in text:
            return value / 100
        return value

    def strip_tags(self, keep_text: bool = True) -> str:
        """移除所有标签"""
        if not self.element:
            return ""
        if keep_text:
            return self.get()
        return ""


class CSSToXPath:
    """
    CSS 到 XPath 转换器

    """

    # 常见 CSS 选择器到 XPath 的映射
    TRANSLATIONS = {
        ">": "/",
        " ": "//",
        "+": "/following-sibling::*[1]/self::",
        "~": "/following-sibling::",
    }

    @classmethod
    def convert(cls, css_selector: str) -> str:
        """
        将 CSS 选择器转换为 XPath

        Args:
            css_selector: CSS 选择器

        Returns:
            XPath 表达式
        """
        # 简单转换
        xpath = css_selector.strip()

        # 处理 ID 选择器
        xpath = re.sub(r"#([\w-]+)", r"[@id='\1']", xpath)

        # 处理 class 选择器
        xpath = re.sub(r"\.([\w-]+)", r"[contains(concat(' ', normalize-space(@class), ' '), ' \1 ')]", xpath)

        # 处理 nth-child
        xpath = re.sub(r":nth-child\((\d+)\)", r"[\1]", xpath)

        # 处理:first-child
        xpath = xpath.replace(":first-child", "[1]")

        # 处理:last-child
        xpath = xpath.replace(":last-child", "[last()]")

        # 处理属性选择器
        xpath = re.sub(r"\[([\w-]+)\]", r"[@\1]", xpath)
        xpath = re.sub(r"\[([\w-]+)=['\"]?([^'\"]+)['\"]?\]", r"[@\1='\2']", xpath)

        # 处理直接子元素
        xpath = xpath.replace(" > ", "/")

        # 处理后代选择器
        if " " in xpath and not xpath.startswith("//"):
            parts = xpath.split(" ", 1)
            if not parts[0].startswith("["):
                xpath = "//" + xpath.replace(" ", "//", 1)
            else:
                xpath = "//" + xpath

        # 如果不是从//开头，添加//
        if not xpath.startswith("//") and not xpath.startswith("/"):
            xpath = "//" + xpath

        return xpath

    @classmethod
    def convert_back(cls, xpath: str) -> str:
        """
        将 XPath 转换为 CSS 选择器（近似）

        Args:
            xpath: XPath 表达式

        Returns:
            CSS 选择器（近似）
        """
        css = xpath

        # 移除//
        css = css.replace("//", " ").replace("/", " > ")

        # 简化属性
        css = re.sub(r"\[@id='([^']+)'\]", r"#\1", css)
        css = re.sub(r"\[@([\w-]+)='([^']+)'\]", r"[\1='\2']", css)

        # 移除位置
        css = re.sub(r"\[(\d+)\]", r":nth-child(\1)", css)
        css = css.replace("[last()]", ":last-child")

        return css.strip()

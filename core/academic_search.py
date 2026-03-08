"""
学术搜索引擎 - 专门用于论文、代码项目搜索
"""
import asyncio
import re
import json
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any, Literal
from datetime import datetime
from enum import Enum
import logging

from core.crawler import Crawler, CrawlResult
from core.parser import Parser, ExtractedData

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class AcademicSource(Enum):
    """学术资源来源"""
    ARXIV = "arxiv"           # 预印本论文
    GOOGLE_SCHOLAR = "google_scholar"  # Google 学术
    SEMANTIC_SCHOLAR = "semantic_scholar"  # Semantic Scholar
    PUBMED = "pubmed"         # 生物医学论文
    IEEE = "ieee"             # IEEE 论文
    CNKI = "cnki"             # 中国知网
    WANFANG = "wanfang"       # 万方数据
    GITHUB = "github"         # GitHub 代码
    GITEE = "gitee"           # Gitee 代码
    PAPER_WITH_CODE = "paper_with_code"  # Papers With Code


@dataclass
class PaperResult:
    """论文结果"""
    title: str
    url: str
    abstract: str
    authors: List[str]
    source: str
    publish_date: Optional[str]
    citations: Optional[str]
    pdf_url: Optional[str]
    code_url: Optional[str]
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "title": self.title,
            "url": self.url,
            "abstract": self.abstract,
            "authors": self.authors,
            "source": self.source,
            "publish_date": self.publish_date,
            "citations": self.citations,
            "pdf_url": self.pdf_url,
            "code_url": self.code_url,
            "metadata": self.metadata,
        }


@dataclass
class CodeProjectResult:
    """代码项目结果"""
    name: str
    url: str
    description: str
    language: str
    stars: str
    forks: str
    source: str
    topics: List[str]
    last_updated: Optional[str]
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "url": self.url,
            "description": self.description,
            "language": self.language,
            "stars": self.stars,
            "forks": self.forks,
            "source": self.source,
            "topics": self.topics,
            "last_updated": self.last_updated,
            "metadata": self.metadata,
        }


class AcademicSearchEngine:
    """
    学术搜索引擎

    支持：
    - 论文搜索（arXiv、Google Scholar、Semantic Scholar、PubMed、IEEE、CNKI、万方）
    - 代码项目搜索（GitHub、Gitee）
    - 论文摘要自动爬取
    """

    # 学术搜索 URL
    SEARCH_URLS = {
        AcademicSource.ARXIV: "https://arxiv.org/search/?query={query}&searchtype=all&start=0",
        AcademicSource.GOOGLE_SCHOLAR: "https://scholar.google.com/scholar?q={query}&hl=zh-CN&num={count}",
        AcademicSource.SEMANTIC_SCHOLAR: "https://www.semanticscholar.org/search?q={query}&sort=relevance",
        AcademicSource.PUBMED: "https://pubmed.ncbi.nlm.nih.gov/?term={query}&size={count}",
        AcademicSource.IEEE: "https://ieeexplore.ieee.org/search/searchresult.jsp?newsearch=true&queryText={query}&rows={count}",
        AcademicSource.CNKI: "https://kns.cnki.net/kns8s/defaultresult/index?kwd={query}",
        AcademicSource.WANFANG: "https://c.wanfangdata.com.cn.cnki.net.kcisrc.com.cn/search/list?searchword={query}&clustertype=all&pagesize=20",
        AcademicSource.GITHUB: "https://github.com/search?q={query}&type=repositories",
        AcademicSource.GITEE: "https://search.gitee.com/?skin=rec&type=repository&q={query}",
        AcademicSource.PAPER_WITH_CODE: "https://paperswithcode.com/search?q={query}&page=1",
    }

    def __init__(self):
        self._crawler = Crawler()
        self._headers = {
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        }

    async def search_papers(
        self,
        query: str,
        sources: Optional[List[AcademicSource]] = None,
        num_results: int = 10,
        fetch_abstract: bool = True,
    ) -> List[PaperResult]:
        """
        搜索论文

        Args:
            query: 搜索关键词
            sources: 学术来源列表
            num_results: 结果数量
            fetch_abstract: 是否获取摘要

        Returns:
            论文结果列表
        """
        if sources is None:
            sources = [AcademicSource.ARXIV, AcademicSource.GOOGLE_SCHOLAR]

        all_results = []
        for source in sources:
            try:
                results = await self._search_source(source, query, num_results // len(sources) + 1)
                all_results.extend(results)
            except Exception as e:
                logger.warning(f"Error searching {source.value}: {e}")

        # 去重（按标题）
        seen = set()
        unique = []
        for r in all_results:
            if r.title.lower() not in seen:
                seen.add(r.title.lower())
                unique.append(r)

        return unique[:num_results]

    async def search_code(
        self,
        query: str,
        sources: Optional[List[AcademicSource]] = None,
        num_results: int = 10,
    ) -> List[CodeProjectResult]:
        """
        搜索代码项目

        Args:
            query: 搜索关键词
            sources: 代码平台列表
            num_results: 结果数量

        Returns:
            代码项目结果列表
        """
        if sources is None:
            sources = [AcademicSource.GITHUB, AcademicSource.GITEE]

        all_results = []
        for source in sources:
            try:
                results = await self._search_code_source(source, query, num_results // len(sources) + 1)
                all_results.extend(results)
            except Exception as e:
                logger.warning(f"Error searching {source.value}: {e}")

        return all_results[:num_results]

    async def _search_source(
        self,
        source: AcademicSource,
        query: str,
        num_results: int,
    ) -> List[PaperResult]:
        """搜索特定学术来源"""
        url = self.SEARCH_URLS[source].format(
            query=self._encode_query(query),
            count=num_results,
        )

        result = await self._crawler.fetch(url)
        if not result.success:
            return []

        if source == AcademicSource.ARXIV:
            return self._parse_arxiv(result.html, num_results)
        elif source == AcademicSource.GOOGLE_SCHOLAR:
            return self._parse_scholar(result.html, num_results)
        elif source == AcademicSource.SEMANTIC_SCHOLAR:
            return self._parse_semantic(result.html, num_results)
        elif source == AcademicSource.PUBMED:
            return self._parse_pubmed(result.html, num_results)
        elif source == AcademicSource.PAPER_WITH_CODE:
            return self._parse_paperwithcode(result.html, num_results)
        else:
            return []

    async def _search_code_source(
        self,
        source: AcademicSource,
        query: str,
        num_results: int,
    ) -> List[CodeProjectResult]:
        """搜索代码项目"""
        url = self.SEARCH_URLS[source].format(
            query=self._encode_query(query),
        )

        result = await self._crawler.fetch(url)
        if not result.success:
            return []

        if source == AcademicSource.GITHUB:
            return self._parse_github(result.html, num_results)
        elif source == AcademicSource.GITEE:
            return self._parse_gitee(result.html, num_results)
        else:
            return []

    async def fetch_abstract(self, url: str) -> Optional[str]:
        """
        爬取论文摘要

        Args:
            url: 论文 URL

        Returns:
            摘要内容
        """
        try:
            result = await self._crawler.fetch_with_retry(url)
            if not result.success:
                return None

            parser = Parser().parse(result.html, url)

            # 尝试多种选择器获取摘要
            abstract_selectors = [
                "meta[name='description']",
                "meta[property='og:description']",
                ".abstract",
                "#abstract",
                "[class*='abstract']",
                "section.abstract",
            ]

            for selector in abstract_selectors:
                element = parser.soup.select_one(selector)
                if element:
                    content = element.get("content") or element.get_text(strip=True)
                    if content and len(content) > 50:
                        return self._clean_abstract(content)

            return None
        except Exception as e:
            logger.warning(f"Error fetching abstract from {url}: {e}")
            return None

    def _encode_query(self, query: str) -> str:
        """编码查询"""
        import urllib.parse
        return urllib.parse.quote(query)

    def _clean_abstract(self, text: str) -> str:
        """清理摘要文本"""
        # 移除多余空白
        text = re.sub(r'\s+', ' ', text)
        # 移除常见后缀
        text = re.sub(r'^(Abstract|摘要)[:：]?\s*', '', text, flags=re.IGNORECASE)
        return text.strip()

    # ========== 解析器 ==========

    def _parse_arxiv(self, html: str, num_results: int) -> List[PaperResult]:
        """解析 arXiv 结果"""
        parser = Parser().parse(html)
        results = []

        for item in parser.soup.select("li.arxiv-result"):
            title_tag = item.find("p", class_="title")
            abstract_tag = item.find("p", class_="abstract")
            authors_tag = item.find("p", class_="authors")

            if title_tag:
                title = title_tag.get_text(strip=True)
                # 移除 "Title:" 前缀
                title = re.sub(r'^Title:\s*', '', title)

                abstract = ""
                if abstract_tag:
                    abstract_text = abstract_tag.get_text(strip=True)
                    abstract = re.sub(r'^Abstract:\s*', '', abstract_text)

                authors = []
                if authors_tag:
                    authors = [a.get_text(strip=True) for a in authors_tag.find_all("a")]

                # 获取 PDF URL
                pdf_tag = item.find("a", title="Download PDF")
                pdf_url = pdf_tag["href"] if pdf_tag else None

                results.append(PaperResult(
                    title=title,
                    url=title_tag.find("a", href=True)["href"] if title_tag.find("a", href=True) else "",
                    abstract=abstract[:2000],
                    authors=authors[:10],
                    source="arxiv",
                    publish_date=None,
                    citations=None,
                    pdf_url=pdf_url,
                    code_url=None,
                ))

                if len(results) >= num_results:
                    break

        return results

    def _parse_scholar(self, html: str, num_results: int) -> List[PaperResult]:
        """解析 Google Scholar 结果"""
        parser = Parser().parse(html)
        results = []

        for item in parser.soup.select("div.gs_ri"):
            title_tag = item.find("h3")
            if not title_tag:
                continue

            url_tag = title_tag.find("a", href=True)
            if not url_tag:
                continue

            snippet_tag = item.find("div", class_="gs_rs")
            authors_tag = item.find("div", class_="gs_a")
            cite_tag = item.find("a", class_=re.compile(r"gs_cit"))

            title = url_tag.get_text(strip=True)
            abstract = snippet_tag.get_text(strip=True) if snippet_tag else ""

            authors = []
            if authors_tag:
                authors_text = authors_tag.get_text(strip=True)
                authors = authors_text.split("-")[0].split(",")[:5] if "-" in authors_text else []

            citations = None
            if cite_tag:
                cite_text = cite_tag.get_text(strip=True)
                if "被引用" in cite_text or "Cited by" in cite_text:
                    citations = cite_text

            results.append(PaperResult(
                title=title,
                url=url_tag["href"],
                abstract=abstract[:2000],
                authors=authors,
                source="google_scholar",
                publish_date=None,
                citations=citations,
                pdf_url=None,
                code_url=None,
            ))

            if len(results) >= num_results:
                break

        return results

    def _parse_semantic(self, html: str, num_results: int) -> List[PaperResult]:
        """解析 Semantic Scholar 结果"""
        parser = Parser().parse(html)
        results = []

        for item in parser.soup.select("[data-layout='result']"):
            title_tag = item.find("[data-slot='title']")
            abstract_tag = item.find("[data-slot='abstract']")
            authors_tag = item.find("[data-slot='authors']")

            if title_tag:
                results.append(PaperResult(
                    title=title_tag.get_text(strip=True),
                    url=title_tag.find("a", href=True)["href"] if title_tag.find("a", href=True) else "",
                    abstract=abstract_tag.get_text(strip=True)[:2000] if abstract_tag else "",
                    authors=[a.get_text(strip=True) for a in (authors_tag.find_all("a") if authors_tag else [])][:10],
                    source="semantic_scholar",
                    publish_date=None,
                    citations=None,
                    pdf_url=None,
                    code_url=None,
                ))

                if len(results) >= num_results:
                    break

        return results

    def _parse_pubmed(self, html: str, num_results: int) -> List[PaperResult]:
        """解析 PubMed 结果"""
        parser = Parser().parse(html)
        results = []

        for item in parser.soup.select(".docsum-content"):
            title_tag = item.find(".docsum-title")
            snippet_tag = item.find(".docsum-text")

            if title_tag:
                results.append(PaperResult(
                    title=title_tag.get_text(strip=True),
                    url=title_tag.find("a", href=True)["href"] if title_tag.find("a", href=True) else "",
                    abstract=snippet_tag.get_text(strip=True)[:2000] if snippet_tag else "",
                    authors=[],
                    source="pubmed",
                    publish_date=None,
                    citations=None,
                    pdf_url=None,
                    code_url=None,
                ))

                if len(results) >= num_results:
                    break

        return results

    def _parse_paperwithcode(self, html: str, num_results: int) -> List[PaperResult]:
        """解析 Papers With Code 结果"""
        parser = Parser().parse(html)
        results = []

        for item in parser.soup.select(".media-item"):
            title_tag = item.find("h3")
            abstract_tag = item.find(".abstract")
            code_link = item.find("a", string=re.compile(r"View Code", re.I))

            if title_tag:
                results.append(PaperResult(
                    title=title_tag.get_text(strip=True),
                    url=title_tag.find("a", href=True)["href"] if title_tag.find("a", href=True) else "",
                    abstract=abstract_tag.get_text(strip=True)[:2000] if abstract_tag else "",
                    authors=[],
                    source="paper_with_code",
                    publish_date=None,
                    citations=None,
                    pdf_url=None,
                    code_url=code_link["href"] if code_link else None,
                ))

                if len(results) >= num_results:
                    break

        return results

    def _parse_github(self, html: str, num_results: int) -> List[CodeProjectResult]:
        """解析 GitHub 搜索结果"""
        parser = Parser().parse(html)
        results = []

        for item in parser.soup.select("ul.repo-list > li"):
            title_tag = item.find("h3 a")
            desc_tag = item.find("p.description")
            meta_tags = item.find_all("span", class_="Counter")
            lang_tag = item.find("span", itemprop="programmingLanguage")

            if title_tag:
                # 提取 star 和 fork 数
                stars = forks = "0"
                if len(meta_tags) >= 1:
                    stars = meta_tags[0].get_text(strip=True)
                if len(meta_tags) >= 2:
                    forks = meta_tags[1].get_text(strip=True)

                topics = [t.get_text(strip=True) for t in item.find_all("a", class_="topic-tag-link")][:5]

                results.append(CodeProjectResult(
                    name=title_tag.get_text(strip=True),
                    url=f"https://github.com{title_tag['href']}",
                    description=desc_tag.get_text(strip=True)[:500] if desc_tag else "",
                    language=lang_tag.get_text(strip=True) if lang_tag else "",
                    stars=stars,
                    forks=forks,
                    source="github",
                    topics=topics,
                    last_updated=None,
                ))

                if len(results) >= num_results:
                    break

        return results

    def _parse_gitee(self, html: str, num_results: int) -> List[CodeProjectResult]:
        """解析 Gitee 搜索结果"""
        parser = Parser().parse(html)
        results = []

        for item in parser.soup.select(".items .item"):
            title_tag = item.find(".title a")
            desc_tag = item.find(".description")
            meta_tag = item.find(".meta")

            if title_tag:
                # 提取语言
                language = ""
                if meta_tag:
                    meta_text = meta_tag.get_text(strip=True)
                    lang_match = re.search(r'(\w+)\s', meta_text)
                    if lang_match:
                        language = lang_match.group(1)

                results.append(CodeProjectResult(
                    name=title_tag.get_text(strip=True),
                    url=title_tag["href"],
                    description=desc_tag.get_text(strip=True)[:500] if desc_tag else "",
                    language=language,
                    stars="0",
                    forks="0",
                    source="gitee",
                    topics=[],
                    last_updated=None,
                ))

                if len(results) >= num_results:
                    break

        return results

    async def close(self):
        """关闭"""
        await self._crawler.close()


def is_academic_query(query: str) -> bool:
    """判断是否为学术查询"""
    academic_keywords = [
        "论文", "research", "paper", "学术", "study",
        "journal", "conference", "arxiv", "scholar",
        "GitHub", "开源", "open source", "代码",
        "project", "工程", "实现", "源码",
        "transformer", "architecture", "model", "algorithm",
        "machine learning", "deep learning", "neural",
    ]
    return any(kw.lower() in query.lower() for kw in academic_keywords)


async def academic_search(
    query: str,
    sources: Optional[List[AcademicSource]] = None,
    num_results: int = 10,
    fetch_abstract: bool = True,
) -> List[PaperResult]:
    """便捷学术搜索函数"""
    engine = AcademicSearchEngine()
    results = await engine.search_papers(query, sources, num_results, fetch_abstract)
    await engine.close()
    return results


async def code_search(
    query: str,
    sources: Optional[List[AcademicSource]] = None,
    num_results: int = 10,
) -> List[CodeProjectResult]:
    """便捷代码搜索函数"""
    engine = AcademicSearchEngine()
    results = await engine.search_code(query, sources, num_results)
    await engine.close()
    return results

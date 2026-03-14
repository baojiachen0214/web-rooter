"""
Academic search engine with robust parsing and citation-oriented metadata.
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from urllib.parse import quote_plus, urljoin, urlparse

try:
    from core.crawler import Crawler
except ModuleNotFoundError as exc:  # pragma: no cover - optional runtime dependency
    Crawler = None  # type: ignore[assignment]
    _CRAWLER_IMPORT_ERROR: Optional[Exception] = exc
else:
    _CRAWLER_IMPORT_ERROR = None

try:
    from core.parser import Parser
except ModuleNotFoundError as exc:  # pragma: no cover - optional runtime dependency
    Parser = None  # type: ignore[assignment]
    _PARSER_IMPORT_ERROR: Optional[Exception] = exc
else:
    _PARSER_IMPORT_ERROR = None


def _build_parser():
    if Parser is None:
        raise RuntimeError(
            "HTML parser runtime is unavailable. Install optional dependencies from requirements.txt."
        ) from _PARSER_IMPORT_ERROR
    return Parser()

logger = logging.getLogger(__name__)


class AcademicSource(Enum):
    ARXIV = "arxiv"
    GOOGLE_SCHOLAR = "google_scholar"
    SEMANTIC_SCHOLAR = "semantic_scholar"
    PUBMED = "pubmed"
    IEEE = "ieee"
    CNKI = "cnki"
    WANFANG = "wanfang"
    GITHUB = "github"
    GITEE = "gitee"
    PAPER_WITH_CODE = "paper_with_code"


@dataclass
class PaperResult:
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
    PAPER_SOURCES = {
        AcademicSource.ARXIV,
        AcademicSource.GOOGLE_SCHOLAR,
        AcademicSource.SEMANTIC_SCHOLAR,
        AcademicSource.PUBMED,
        AcademicSource.IEEE,
        AcademicSource.CNKI,
        AcademicSource.WANFANG,
        AcademicSource.PAPER_WITH_CODE,
    }
    CODE_SOURCES = {AcademicSource.GITHUB, AcademicSource.GITEE}

    SEARCH_URLS = {
        AcademicSource.ARXIV: (
            "http://export.arxiv.org/api/query?"
            "search_query=all:{query}&start=0&max_results={count}&sortBy=relevance&sortOrder=descending"
        ),
        AcademicSource.GOOGLE_SCHOLAR: "https://scholar.google.com/scholar?q={query}&hl=zh-CN&num={count}",
        AcademicSource.SEMANTIC_SCHOLAR: (
            "https://api.semanticscholar.org/graph/v1/paper/search?"
            "query={query}&limit={count}&fields=title,abstract,year,authors,url,citationCount,venue,externalIds,openAccessPdf"
        ),
        AcademicSource.PUBMED: "https://pubmed.ncbi.nlm.nih.gov/?term={query}&size={count}",
        AcademicSource.IEEE: "https://ieeexplore.ieee.org/search/searchresult.jsp?newsearch=true&queryText={query}",
        AcademicSource.CNKI: "https://kns.cnki.net/kns8s/defaultresult/index?kwd={query}",
        AcademicSource.WANFANG: "https://s.wanfangdata.com.cn/paper?q={query}",
        AcademicSource.GITHUB: (
            "https://api.github.com/search/repositories?"
            "q={query}&sort=stars&order=desc&per_page={count}"
        ),
        AcademicSource.GITEE: "https://search.gitee.com/?skin=rec&type=repository&q={query}",
        AcademicSource.PAPER_WITH_CODE: "https://paperswithcode.com/search?q={query}&page=1",
    }

    SOURCE_PRIORITY = {
        AcademicSource.ARXIV.value: 1,
        AcademicSource.SEMANTIC_SCHOLAR.value: 2,
        AcademicSource.PUBMED.value: 3,
        AcademicSource.GOOGLE_SCHOLAR.value: 4,
        AcademicSource.PAPER_WITH_CODE.value: 5,
        AcademicSource.IEEE.value: 6,
        AcademicSource.CNKI.value: 7,
        AcademicSource.WANFANG.value: 8,
    }

    def __init__(self):
        if Crawler is None:
            raise RuntimeError(
                "Academic search runtime is unavailable. Install optional dependencies from requirements.txt."
            ) from _CRAWLER_IMPORT_ERROR
        self._crawler = Crawler()
        self._headers = {
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            ),
        }

    async def search_papers(
        self,
        query: str,
        sources: Optional[List[AcademicSource]] = None,
        num_results: int = 10,
        fetch_abstract: bool = True,
    ) -> List[PaperResult]:
        if sources is None:
            sources = [
                AcademicSource.ARXIV,
                AcademicSource.SEMANTIC_SCHOLAR,
                AcademicSource.GOOGLE_SCHOLAR,
                AcademicSource.PUBMED,
                AcademicSource.PAPER_WITH_CODE,
            ]

        paper_sources = [s for s in sources if s in self.PAPER_SOURCES]
        if not paper_sources:
            paper_sources = [AcademicSource.ARXIV, AcademicSource.SEMANTIC_SCHOLAR]

        per_source = max(2, min(25, num_results // max(1, len(paper_sources)) + 2))
        tasks = [self._search_source(source, query, per_source) for source in paper_sources]
        source_chunks = await asyncio.gather(*tasks, return_exceptions=True)

        all_results: List[PaperResult] = []
        for item in source_chunks:
            if isinstance(item, Exception):
                logger.warning("Academic source failed: %s", item)
                continue
            all_results.extend(item)

        merged = self._deduplicate_papers(all_results)
        if fetch_abstract:
            await self._enrich_abstracts(merged, limit=min(8, len(merged)))
        merged.sort(key=self._paper_sort_key)
        return merged[:num_results]

    async def search_code(
        self,
        query: str,
        sources: Optional[List[AcademicSource]] = None,
        num_results: int = 10,
    ) -> List[CodeProjectResult]:
        if sources is None:
            sources = [AcademicSource.GITHUB, AcademicSource.GITEE]

        code_sources = [s for s in sources if s in self.CODE_SOURCES]
        if not code_sources:
            code_sources = [AcademicSource.GITHUB]

        per_source = max(2, min(25, num_results // max(1, len(code_sources)) + 2))
        tasks = [self._search_code_source(source, query, per_source) for source in code_sources]
        source_chunks = await asyncio.gather(*tasks, return_exceptions=True)

        all_results: List[CodeProjectResult] = []
        for item in source_chunks:
            if isinstance(item, Exception):
                logger.warning("Code source failed: %s", item)
                continue
            all_results.extend(item)
        return all_results[:num_results]

    async def _search_source(
        self,
        source: AcademicSource,
        query: str,
        num_results: int,
    ) -> List[PaperResult]:
        if source == AcademicSource.ARXIV:
            return await self._search_arxiv_api(query, num_results)
        if source == AcademicSource.SEMANTIC_SCHOLAR:
            return await self._search_semantic_api(query, num_results)
        if source == AcademicSource.PUBMED:
            return await self._search_pubmed_api(query, num_results)

        url = self.SEARCH_URLS[source].format(query=self._encode_query(query), count=num_results)
        result = await self._crawler.fetch_with_retry(url, retries=2, use_proxy=False)
        if not result.success:
            return []

        html = result.html or ""
        if source == AcademicSource.GOOGLE_SCHOLAR:
            return self._parse_scholar(html, num_results)
        if source == AcademicSource.PAPER_WITH_CODE:
            return self._parse_paperwithcode(html, num_results)
        if source in {AcademicSource.IEEE, AcademicSource.CNKI, AcademicSource.WANFANG}:
            return self._parse_generic_papers(html, num_results, source, url)
        return []

    async def _search_code_source(
        self,
        source: AcademicSource,
        query: str,
        num_results: int,
    ) -> List[CodeProjectResult]:
        if source == AcademicSource.GITHUB:
            api_results = await self._search_github_api(query, num_results)
            if api_results:
                return api_results

        url = self.SEARCH_URLS[source].format(query=self._encode_query(query), count=num_results)
        result = await self._crawler.fetch_with_retry(url, retries=2, use_proxy=False)
        if not result.success:
            return []

        if source == AcademicSource.GITHUB:
            return self._parse_github(result.html, num_results)
        if source == AcademicSource.GITEE:
            return self._parse_gitee(result.html, num_results)
        return []

    async def _search_arxiv_api(self, query: str, num_results: int) -> List[PaperResult]:
        url = self.SEARCH_URLS[AcademicSource.ARXIV].format(query=self._encode_query(query), count=num_results)
        result = await self._crawler.fetch_with_retry(url, retries=2, use_proxy=False)
        if not result.success:
            return []

        try:
            root = ET.fromstring(result.html)
        except ET.ParseError:
            return []

        ns = {"atom": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom"}
        papers: List[PaperResult] = []
        for entry in root.findall("atom:entry", ns):
            title = self._norm_space(entry.findtext("atom:title", default="", namespaces=ns))
            if not title:
                continue
            abstract = self._norm_space(entry.findtext("atom:summary", default="", namespaces=ns))
            paper_url = self._norm_space(entry.findtext("atom:id", default="", namespaces=ns))
            published = self._norm_space(entry.findtext("atom:published", default="", namespaces=ns))
            authors = [
                self._norm_space(author.findtext("atom:name", default="", namespaces=ns))
                for author in entry.findall("atom:author", ns)
            ]
            pdf_url = None
            for link in entry.findall("atom:link", ns):
                if link.attrib.get("type") == "application/pdf":
                    pdf_url = link.attrib.get("href")
            doi_node = entry.find("arxiv:doi", ns)
            doi = doi_node.text.strip() if doi_node is not None and doi_node.text else None

            papers.append(
                PaperResult(
                    title=title,
                    url=paper_url,
                    abstract=abstract[:4000],
                    authors=[a for a in authors if a][:10],
                    source=AcademicSource.ARXIV.value,
                    publish_date=published[:10] if published else None,
                    citations=None,
                    pdf_url=pdf_url,
                    code_url=None,
                    metadata={
                        "doi": doi,
                        "venue": "arXiv",
                        "citation_count": None,
                        "source_priority": self.SOURCE_PRIORITY[AcademicSource.ARXIV.value],
                    },
                )
            )
            if len(papers) >= num_results:
                break
        return papers

    async def _search_semantic_api(self, query: str, num_results: int) -> List[PaperResult]:
        url = self.SEARCH_URLS[AcademicSource.SEMANTIC_SCHOLAR].format(
            query=self._encode_query(query),
            count=min(50, max(1, num_results)),
        )
        result = await self._crawler.fetch_with_retry(url, retries=2, use_proxy=False)
        if not result.success:
            return []

        payload = self._safe_json(result.html)
        papers = payload.get("data", []) if isinstance(payload, dict) else []
        output: List[PaperResult] = []
        for item in papers:
            title = self._norm_space(item.get("title", ""))
            if not title:
                continue
            authors = [self._norm_space(a.get("name", "")) for a in (item.get("authors") or [])]
            year = item.get("year")
            citation_count = item.get("citationCount")
            external_ids = item.get("externalIds") or {}
            doi = external_ids.get("DOI")
            open_access_pdf = item.get("openAccessPdf") or {}

            output.append(
                PaperResult(
                    title=title,
                    url=item.get("url") or "",
                    abstract=self._norm_space(item.get("abstract", ""))[:4000],
                    authors=[a for a in authors if a][:10],
                    source=AcademicSource.SEMANTIC_SCHOLAR.value,
                    publish_date=str(year) if year else None,
                    citations=f"Cited by {citation_count}" if isinstance(citation_count, int) else None,
                    pdf_url=open_access_pdf.get("url"),
                    code_url=None,
                    metadata={
                        "doi": doi,
                        "venue": self._norm_space(item.get("venue", "")) or None,
                        "citation_count": citation_count,
                        "source_priority": self.SOURCE_PRIORITY[AcademicSource.SEMANTIC_SCHOLAR.value],
                    },
                )
            )
            if len(output) >= num_results:
                break
        return output

    async def _search_pubmed_api(self, query: str, num_results: int) -> List[PaperResult]:
        search_url = (
            "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/"
            f"esearch.fcgi?db=pubmed&retmode=json&retmax={num_results}&term={self._encode_query(query)}"
        )
        search_result = await self._crawler.fetch_with_retry(search_url, retries=2, use_proxy=False)
        if not search_result.success:
            return []

        search_payload = self._safe_json(search_result.html)
        id_list = (((search_payload or {}).get("esearchresult") or {}).get("idlist") or [])
        if not id_list:
            return []

        summary_url = (
            "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/"
            f"esummary.fcgi?db=pubmed&retmode=json&id={','.join(id_list)}"
        )
        summary_result = await self._crawler.fetch_with_retry(summary_url, retries=2, use_proxy=False)
        if not summary_result.success:
            return []

        summary_payload = self._safe_json(summary_result.html)
        entities = (summary_payload or {}).get("result") or {}
        output: List[PaperResult] = []
        for pid in id_list:
            item = entities.get(pid) or {}
            title = self._norm_space(item.get("title", ""))
            if not title:
                continue
            authors = [self._norm_space(a.get("name", "")) for a in (item.get("authors") or [])]
            pubdate = self._norm_space(item.get("pubdate", ""))
            article_ids = item.get("articleids") or []
            doi = None
            for aid in article_ids:
                if (aid.get("idtype") or "").lower() == "doi":
                    doi = aid.get("value")
                    break

            output.append(
                PaperResult(
                    title=title,
                    url=f"https://pubmed.ncbi.nlm.nih.gov/{pid}/",
                    abstract="",
                    authors=[a for a in authors if a][:10],
                    source=AcademicSource.PUBMED.value,
                    publish_date=pubdate or None,
                    citations=None,
                    pdf_url=None,
                    code_url=None,
                    metadata={
                        "doi": doi,
                        "venue": self._norm_space(item.get("source", "")) or None,
                        "citation_count": None,
                        "source_priority": self.SOURCE_PRIORITY[AcademicSource.PUBMED.value],
                        "pubmed_id": pid,
                    },
                )
            )
            if len(output) >= num_results:
                break
        return output

    async def _search_github_api(self, query: str, num_results: int) -> List[CodeProjectResult]:
        url = self.SEARCH_URLS[AcademicSource.GITHUB].format(
            query=self._encode_query(query),
            count=min(50, max(1, num_results)),
        )
        result = await self._crawler.fetch(
            url,
            headers={
                **self._headers,
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
            use_proxy=False,
            use_cache=False,
        )
        if not result.success:
            return []

        payload = self._safe_json(result.html)
        items = payload.get("items", []) if isinstance(payload, dict) else []
        output: List[CodeProjectResult] = []
        for item in items:
            output.append(
                CodeProjectResult(
                    name=item.get("full_name") or item.get("name") or "",
                    url=item.get("html_url") or "",
                    description=self._norm_space(item.get("description", ""))[:500],
                    language=item.get("language") or "",
                    stars=str(item.get("stargazers_count", 0)),
                    forks=str(item.get("forks_count", 0)),
                    source=AcademicSource.GITHUB.value,
                    topics=(item.get("topics") or [])[:8],
                    last_updated=item.get("updated_at"),
                    metadata={
                        "watchers": item.get("watchers_count"),
                        "open_issues": item.get("open_issues_count"),
                    },
                )
            )
            if len(output) >= num_results:
                break
        return output

    async def fetch_abstract(self, url: str) -> Optional[str]:
        try:
            result = await self._crawler.fetch_with_retry(url, retries=2, use_proxy=False)
            if not result.success:
                return None

            parser = _build_parser().parse(result.html, url)
            abstract_selectors = [
                "meta[name='description']",
                "meta[property='og:description']",
                "meta[name='citation_abstract']",
                "blockquote.abstract",
                ".abstract",
                "#abstract",
                "[class*='abstract']",
            ]
            for selector in abstract_selectors:
                element = parser.soup.select_one(selector)
                if not element:
                    continue
                value = element.get("content") if element.has_attr("content") else element.get_text(" ", strip=True)
                cleaned = self._clean_abstract(value)
                if cleaned and len(cleaned) >= 60:
                    return cleaned
            return None
        except Exception as exc:
            logger.warning("Error fetching abstract from %s: %s", url, exc)
            return None

    async def _enrich_abstracts(self, papers: List[PaperResult], limit: int = 8) -> None:
        candidates = [paper for paper in papers if paper.url and len((paper.abstract or "").strip()) < 80]
        if not candidates:
            return
        sem = asyncio.Semaphore(4)

        async def _run(paper: PaperResult) -> None:
            async with sem:
                abstract = await self.fetch_abstract(paper.url)
                if abstract:
                    paper.abstract = abstract[:4000]

        await asyncio.gather(*[_run(paper) for paper in candidates[:limit]], return_exceptions=True)

    def _deduplicate_papers(self, papers: List[PaperResult]) -> List[PaperResult]:
        grouped: Dict[str, PaperResult] = {}
        for paper in papers:
            key = self._paper_key(paper)
            if not key:
                continue
            existing = grouped.get(key)
            if existing is None:
                grouped[key] = paper
                continue
            grouped[key] = self._merge_paper(existing, paper)
        return list(grouped.values())

    def _paper_key(self, paper: PaperResult) -> str:
        doi = str((paper.metadata or {}).get("doi") or "").strip().lower()
        if doi:
            return f"doi:{doi}"
        url = self._normalize_url(paper.url)
        if url:
            return f"url:{url}"
        title = self._normalize_title(paper.title)
        return f"title:{title}" if title else ""

    def _merge_paper(self, base: PaperResult, candidate: PaperResult) -> PaperResult:
        if len(candidate.abstract or "") > len(base.abstract or ""):
            base.abstract = candidate.abstract
        if not base.publish_date and candidate.publish_date:
            base.publish_date = candidate.publish_date
        if not base.pdf_url and candidate.pdf_url:
            base.pdf_url = candidate.pdf_url
        if not base.code_url and candidate.code_url:
            base.code_url = candidate.code_url
        if not base.citations and candidate.citations:
            base.citations = candidate.citations
        if len(candidate.authors) > len(base.authors):
            base.authors = candidate.authors

        base_meta = base.metadata or {}
        cand_meta = candidate.metadata or {}
        if not base_meta.get("doi") and cand_meta.get("doi"):
            base_meta["doi"] = cand_meta["doi"]
        if not base_meta.get("venue") and cand_meta.get("venue"):
            base_meta["venue"] = cand_meta["venue"]

        base_cc = self._safe_int(base_meta.get("citation_count"))
        cand_cc = self._safe_int(cand_meta.get("citation_count"))
        if cand_cc is not None and (base_cc is None or cand_cc > base_cc):
            base_meta["citation_count"] = cand_cc
            base.citations = candidate.citations or f"Cited by {cand_cc}"

        base.metadata = base_meta
        return base

    def _paper_sort_key(self, paper: PaperResult) -> tuple:
        meta = paper.metadata or {}
        citation_count = self._safe_int(meta.get("citation_count")) or 0
        source_priority = int(meta.get("source_priority") or self.SOURCE_PRIORITY.get(paper.source, 99))
        year = self._extract_year(paper.publish_date or "") or 0
        title_len = len(paper.title or "")
        return (-citation_count, source_priority, -year, -title_len)

    def _parse_scholar(self, html: str, num_results: int) -> List[PaperResult]:
        parser = _build_parser().parse(html, "https://scholar.google.com")
        results: List[PaperResult] = []
        for item in parser.soup.select("div.gs_ri"):
            title_anchor = item.select_one("h3.gs_rt a") or item.select_one("h3 a")
            if not title_anchor:
                continue
            title = self._norm_space(title_anchor.get_text(" ", strip=True))
            url = self._abs_url("https://scholar.google.com", title_anchor.get("href", ""))
            snippet_node = item.select_one("div.gs_rs") or item.select_one("div.gs_abs")
            snippet = self._norm_space(snippet_node.get_text(" ", strip=True) if snippet_node else "")
            author_line_node = item.select_one("div.gs_a")
            author_line = self._norm_space(author_line_node.get_text(" ", strip=True) if author_line_node else "")
            citation_count = self._extract_cited_by(item.get_text(" ", strip=True))
            publish_year = self._extract_year(author_line)

            results.append(
                PaperResult(
                    title=title,
                    url=url,
                    abstract=snippet[:4000],
                    authors=self._parse_scholar_authors(author_line),
                    source=AcademicSource.GOOGLE_SCHOLAR.value,
                    publish_date=str(publish_year) if publish_year else None,
                    citations=f"Cited by {citation_count}" if citation_count else None,
                    pdf_url=None,
                    code_url=None,
                    metadata={
                        "doi": self._extract_doi(snippet + " " + author_line),
                        "venue": None,
                        "citation_count": citation_count,
                        "source_priority": self.SOURCE_PRIORITY[AcademicSource.GOOGLE_SCHOLAR.value],
                    },
                )
            )
            if len(results) >= num_results:
                break
        return results

    def _parse_paperwithcode(self, html: str, num_results: int) -> List[PaperResult]:
        parser = _build_parser().parse(html, "https://paperswithcode.com")
        results: List[PaperResult] = []
        for item in parser.soup.select(".infinite-container .row.infinite-item, .paper-card, .media-item"):
            title_anchor = item.select_one("h1 a, h2 a, h3 a")
            if not title_anchor:
                continue
            title = self._norm_space(title_anchor.get_text(" ", strip=True))
            paper_url = self._abs_url("https://paperswithcode.com", title_anchor.get("href", ""))
            abstract_node = item.select_one(".item-strip-abstract, .abstract, p")
            abstract = self._norm_space(abstract_node.get_text(" ", strip=True) if abstract_node else "")
            code_anchor = item.select_one("a[href*='github.com'], a[href*='gitlab.com'], a[href*='bitbucket.org']")
            results.append(
                PaperResult(
                    title=title,
                    url=paper_url,
                    abstract=abstract[:4000],
                    authors=[],
                    source=AcademicSource.PAPER_WITH_CODE.value,
                    publish_date=None,
                    citations=None,
                    pdf_url=None,
                    code_url=self._abs_url("https://paperswithcode.com", code_anchor.get("href", "")) if code_anchor else None,
                    metadata={
                        "doi": self._extract_doi(abstract),
                        "venue": "Papers With Code",
                        "citation_count": None,
                        "source_priority": self.SOURCE_PRIORITY[AcademicSource.PAPER_WITH_CODE.value],
                    },
                )
            )
            if len(results) >= num_results:
                break
        return results

    def _parse_generic_papers(
        self,
        html: str,
        num_results: int,
        source: AcademicSource,
        base_url: str,
    ) -> List[PaperResult]:
        parser = _build_parser().parse(html, base_url)
        results: List[PaperResult] = []
        for item in parser.soup.select("article, .result-item, .search-result, .item, li")[: max(50, num_results * 8)]:
            title_anchor = item.select_one("h1 a, h2 a, h3 a, a[title]")
            if not title_anchor:
                continue
            title = self._norm_space(title_anchor.get_text(" ", strip=True))
            if len(title) < 8:
                continue
            snippet_node = item.select_one("p, .abstract, .summary, .desc")
            snippet = self._norm_space(snippet_node.get_text(" ", strip=True) if snippet_node else "")
            results.append(
                PaperResult(
                    title=title,
                    url=self._abs_url(base_url, title_anchor.get("href", "")),
                    abstract=snippet[:4000],
                    authors=[],
                    source=source.value,
                    publish_date=None,
                    citations=None,
                    pdf_url=None,
                    code_url=None,
                    metadata={
                        "doi": self._extract_doi(snippet),
                        "venue": source.value,
                        "citation_count": self._extract_cited_by(snippet),
                        "source_priority": self.SOURCE_PRIORITY.get(source.value, 99),
                    },
                )
            )
            if len(results) >= num_results:
                break
        return results

    def _parse_github(self, html: str, num_results: int) -> List[CodeProjectResult]:
        parser = _build_parser().parse(html, "https://github.com")
        results: List[CodeProjectResult] = []
        for item in parser.soup.select("ul.repo-list li, div.search-results-container li"):
            title_anchor = item.select_one("a.v-align-middle, h3 a")
            if not title_anchor:
                continue
            desc_node = item.select_one("p, .mb-1")
            lang_node = item.select_one("[itemprop='programmingLanguage']")
            results.append(
                CodeProjectResult(
                    name=self._norm_space(title_anchor.get_text(" ", strip=True)),
                    url=self._abs_url("https://github.com", title_anchor.get("href", "")),
                    description=self._norm_space(desc_node.get_text(" ", strip=True) if desc_node else "")[:500],
                    language=self._norm_space(lang_node.get_text(" ", strip=True) if lang_node else ""),
                    stars="0",
                    forks="0",
                    source=AcademicSource.GITHUB.value,
                    topics=[],
                    last_updated=None,
                )
            )
            if len(results) >= num_results:
                break
        return results

    def _parse_gitee(self, html: str, num_results: int) -> List[CodeProjectResult]:
        parser = _build_parser().parse(html, "https://gitee.com")
        results: List[CodeProjectResult] = []
        for item in parser.soup.select(".items .item, .search-result-item, li"):
            title_anchor = item.select_one(".title a, h3 a, a[href*='/']")
            if not title_anchor:
                continue
            desc_node = item.select_one(".description, p, .desc")
            lang_node = item.select_one(".language, .lang")
            results.append(
                CodeProjectResult(
                    name=self._norm_space(title_anchor.get_text(" ", strip=True)),
                    url=self._abs_url("https://gitee.com", title_anchor.get("href", "")),
                    description=self._norm_space(desc_node.get_text(" ", strip=True) if desc_node else "")[:500],
                    language=self._norm_space(lang_node.get_text(" ", strip=True) if lang_node else ""),
                    stars="0",
                    forks="0",
                    source=AcademicSource.GITEE.value,
                    topics=[],
                    last_updated=None,
                )
            )
            if len(results) >= num_results:
                break
        return results

    def _encode_query(self, query: str) -> str:
        return quote_plus(query or "")

    def _clean_abstract(self, text: str) -> str:
        text = self._norm_space(text)
        return re.sub(r"^(Abstract|摘要)[:：]?\s*", "", text, flags=re.IGNORECASE)

    @staticmethod
    def _norm_space(text: str) -> str:
        return re.sub(r"\s+", " ", text or "").strip()

    @staticmethod
    def _normalize_title(title: str) -> str:
        return re.sub(r"\s+", " ", (title or "").lower()).strip()

    @staticmethod
    def _normalize_url(url: str) -> str:
        parsed = urlparse(url or "")
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            return ""
        normalized = parsed._replace(fragment="", query=parsed.query or "")
        value = normalized.geturl()
        return value[:-1] if value.endswith("/") else value

    @staticmethod
    def _safe_json(raw: str) -> Dict[str, Any]:
        try:
            data = json.loads(raw or "{}")
            return data if isinstance(data, dict) else {}
        except json.JSONDecodeError:
            return {}

    @staticmethod
    def _safe_int(value: Any) -> Optional[int]:
        try:
            if value in {None, ""}:
                return None
            return int(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _extract_year(text: str) -> Optional[int]:
        m = re.search(r"(19|20)\d{2}", text or "")
        if not m:
            return None
        year = int(m.group(0))
        if 1900 <= year <= datetime.now().year + 1:
            return year
        return None

    @staticmethod
    def _extract_doi(text: str) -> Optional[str]:
        m = re.search(r"\b10\.\d{4,9}/[-._;()/:A-Za-z0-9]+\b", text or "")
        return m.group(0) if m else None

    @staticmethod
    def _extract_cited_by(text: str) -> Optional[int]:
        if not text:
            return None
        patterns = [r"Cited by\s+(\d+)", r"被引用[:：]?\s*(\d+)", r"引用[:：]?\s*(\d+)"]
        for pattern in patterns:
            m = re.search(pattern, text, flags=re.IGNORECASE)
            if m:
                try:
                    return int(m.group(1))
                except ValueError:
                    continue
        return None

    @staticmethod
    def _parse_scholar_authors(author_line: str) -> List[str]:
        if not author_line:
            return []
        lead = author_line.split("-")[0]
        return [item.strip() for item in lead.split(",") if item.strip()][:8]

    @staticmethod
    def _abs_url(base_url: str, href: str) -> str:
        if not href:
            return ""
        return urljoin(base_url, href)

    async def close(self):
        await self._crawler.close()


def is_academic_query(query: str) -> bool:
    keywords = [
        "论文",
        "research",
        "paper",
        "学术",
        "study",
        "journal",
        "conference",
        "arxiv",
        "scholar",
        "pubmed",
        "doi",
        "开源",
        "github",
        "模型",
        "algorithm",
        "benchmark",
    ]
    q = (query or "").lower()
    return any(word.lower() in q for word in keywords)


async def academic_search(
    query: str,
    sources: Optional[List[AcademicSource]] = None,
    num_results: int = 10,
    fetch_abstract: bool = True,
) -> List[PaperResult]:
    engine = AcademicSearchEngine()
    try:
        return await engine.search_papers(query, sources, num_results, fetch_abstract)
    finally:
        await engine.close()


async def code_search(
    query: str,
    sources: Optional[List[AcademicSource]] = None,
    num_results: int = 10,
) -> List[CodeProjectResult]:
    engine = AcademicSearchEngine()
    try:
        return await engine.search_code(query, sources, num_results)
    finally:
        await engine.close()

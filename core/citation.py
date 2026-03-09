"""
Citation helpers for AI-friendly, paper-like references.
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse


def _clean_text(value: str, max_len: int = 280) -> str:
    text = re.sub(r"\s+", " ", (value or "")).strip()
    if len(text) <= max_len:
        return text
    return text[: max_len - 3].rstrip() + "..."


def _domain(url: str) -> str:
    host = (urlparse(url or "").hostname or "").lower()
    if host.startswith("www."):
        return host[4:]
    return host


def build_web_citations(
    results: List[Dict[str, Any]],
    query: str,
    prefix: str = "W",
) -> List[Dict[str, Any]]:
    """
    Build standardized references for generic web results.

    Expected fields in each result:
    - title
    - url
    - snippet
    - engine
    - rank
    - metadata (optional: source_engines/source_queries/language)
    """
    citations: List[Dict[str, Any]] = []
    now = datetime.utcnow().isoformat(timespec="seconds") + "Z"
    for idx, item in enumerate(results, 1):
        metadata = item.get("metadata") or {}
        citation_id = f"{prefix}{idx}"
        citations.append(
            {
                "id": citation_id,
                "type": "web",
                "query": query,
                "title": (item.get("title") or "").strip(),
                "url": item.get("url") or "",
                "domain": _domain(item.get("url") or ""),
                "engine": item.get("engine") or "",
                "rank": item.get("rank"),
                "language": item.get("language") or metadata.get("language"),
                "source_engines": metadata.get("source_engines", [item.get("engine")]),
                "source_queries": metadata.get("source_queries", [query]),
                "snippet": _clean_text(item.get("snippet") or ""),
                "retrieved_at": now,
            }
        )
        metadata["citation_id"] = citation_id
    return citations


def build_paper_citations(
    papers: List[Dict[str, Any]],
    query: str,
    prefix: str = "P",
) -> List[Dict[str, Any]]:
    """Build standardized references for paper records."""
    citations: List[Dict[str, Any]] = []
    now = datetime.utcnow().isoformat(timespec="seconds") + "Z"

    for idx, paper in enumerate(papers, 1):
        meta = paper.get("metadata") or {}
        citation_id = f"{prefix}{idx}"
        citations.append(
            {
                "id": citation_id,
                "type": "paper",
                "query": query,
                "title": (paper.get("title") or "").strip(),
                "url": paper.get("url") or "",
                "domain": _domain(paper.get("url") or ""),
                "source": paper.get("source") or "",
                "authors": paper.get("authors") or [],
                "publish_date": paper.get("publish_date"),
                "citations": paper.get("citations"),
                "doi": meta.get("doi"),
                "venue": meta.get("venue"),
                "snippet": _clean_text(paper.get("abstract") or ""),
                "retrieved_at": now,
            }
        )
        meta["citation_id"] = citation_id
    return citations


def build_code_citations(
    projects: List[Dict[str, Any]],
    query: str,
    prefix: str = "C",
) -> List[Dict[str, Any]]:
    """Build standardized references for code project records."""
    citations: List[Dict[str, Any]] = []
    now = datetime.utcnow().isoformat(timespec="seconds") + "Z"

    for idx, project in enumerate(projects, 1):
        meta = project.get("metadata") or {}
        citation_id = f"{prefix}{idx}"
        citations.append(
            {
                "id": citation_id,
                "type": "code",
                "query": query,
                "title": (project.get("name") or "").strip(),
                "url": project.get("url") or "",
                "domain": _domain(project.get("url") or ""),
                "source": project.get("source") or "",
                "language": project.get("language") or "",
                "stars": project.get("stars") or "",
                "forks": project.get("forks") or "",
                "topics": project.get("topics") or [],
                "snippet": _clean_text(project.get("description") or ""),
                "retrieved_at": now,
            }
        )
        meta["citation_id"] = citation_id
    return citations


def format_reference_block(
    citations: List[Dict[str, Any]],
    max_items: int = 30,
) -> str:
    """Render citations as a compact, paper-like reference list."""
    if not citations:
        return ""

    lines = ["参考文献 / References:"]
    for item in citations[:max_items]:
        cid = item.get("id", "?")
        title = item.get("title") or "Untitled"
        url = item.get("url") or ""
        source = item.get("source") or item.get("engine") or "web"
        pub_date = item.get("publish_date")
        date_part = f", {pub_date}" if pub_date else ""
        lines.append(f"[{cid}] {title}{date_part}. ({source}) {url}")
    return "\n".join(lines)


def build_comparison_summary(results: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Generate cross-source comparison metrics for result reliability."""
    by_domain: Dict[str, int] = {}
    by_engine: Dict[str, int] = {}
    corroborated = 0

    for item in results:
        url = item.get("url") or ""
        domain = _domain(url)
        if domain:
            by_domain[domain] = by_domain.get(domain, 0) + 1

        engine = item.get("engine") or ""
        if engine:
            by_engine[engine] = by_engine.get(engine, 0) + 1

        metadata = item.get("metadata") or {}
        source_engines = metadata.get("source_engines") or []
        if len(source_engines) >= 2:
            corroborated += 1

    return {
        "total_results": len(results),
        "corroborated_results": corroborated,
        "single_source_results": max(0, len(results) - corroborated),
        "domain_coverage": len(by_domain),
        "engine_distribution": by_engine,
        "top_domains": sorted(by_domain.items(), key=lambda x: x[1], reverse=True)[:10],
    }


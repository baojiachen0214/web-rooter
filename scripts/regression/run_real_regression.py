"""
真实场景回归脚本：
1) 社交/电商评论与平台抓取链路
2) 学术检索 + 论文关系挖掘链路

输出：JSON + Markdown 报告
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import platform
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple
from urllib.parse import urlparse

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from agents.web_agent import WebAgent
from core.search.advanced import search_social_media, search_commerce


@dataclass
class ScenarioResult:
    name: str
    status: str
    duration_sec: float
    metrics: Dict[str, Any]
    errors: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "status": self.status,
            "duration_sec": round(self.duration_sec, 3),
            "metrics": self.metrics,
            "errors": self.errors,
        }


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _unique_domains(results: List[Dict[str, Any]]) -> List[str]:
    domains: List[str] = []
    for item in results:
        if not isinstance(item, dict):
            continue
        url = str(item.get("url", "")).strip()
        if not url:
            continue
        host = (urlparse(url).hostname or "").lower()
        if host and host not in domains:
            domains.append(host)
    return domains


def _count_high_signal(results: List[Dict[str, Any]], target_domains: List[str]) -> int:
    count = 0
    for item in results:
        if not isinstance(item, dict):
            continue
        url = str(item.get("url", "")).strip().lower()
        if not url:
            continue
        host = (urlparse(url).hostname or "").lower()
        if any(host == d or host.endswith("." + d) for d in target_domains):
            count += 1
    return count


async def run_social_and_commerce() -> ScenarioResult:
    started = asyncio.get_running_loop().time()
    errors: List[str] = []

    social_platforms = ["xiaohongshu", "zhihu", "tieba", "douyin", "bilibili", "weibo"]
    commerce_platforms = ["taobao", "jd", "pinduoduo", "meituan"]

    social = await search_social_media(
        "手机 评测 评论 用户反馈",
        platforms=social_platforms,
    )
    commerce = await search_commerce(
        "手机 价格 评论 购买反馈",
        platforms=commerce_platforms,
    )

    social_results = social.get("results", []) if isinstance(social, dict) else []
    commerce_results = commerce.get("results", []) if isinstance(commerce, dict) else []

    if isinstance(social.get("errors"), list):
        errors.extend([str(e) for e in social.get("errors", [])[:8]])
    if isinstance(commerce.get("errors"), list):
        errors.extend([str(e) for e in commerce.get("errors", [])[:8]])

    social_domains = _unique_domains(social_results)
    commerce_domains = _unique_domains(commerce_results)

    social_target_domains = [
        "xiaohongshu.com",
        "zhihu.com",
        "tieba.baidu.com",
        "douyin.com",
        "bilibili.com",
        "weibo.com",
    ]
    commerce_target_domains = [
        "taobao.com",
        "tmall.com",
        "jd.com",
        "pinduoduo.com",
        "yangkeduo.com",
        "meituan.com",
        "dianping.com",
    ]

    social_high_signal = _count_high_signal(social_results, social_target_domains)
    commerce_high_signal = _count_high_signal(commerce_results, commerce_target_domains)

    social_total = int(social.get("total_results", 0) or 0) if isinstance(social, dict) else 0
    commerce_total = int(commerce.get("total_results", 0) or 0) if isinstance(commerce, dict) else 0

    status = "pass"
    if social_total <= 0 or commerce_total <= 0:
        status = "fail"
    elif social_high_signal < 2 or commerce_high_signal < 2:
        status = "partial"

    metrics = {
        "social_total_results": social_total,
        "social_high_signal_results": social_high_signal,
        "social_domain_coverage": len(social_domains),
        "social_top_domains": social_domains[:12],
        "commerce_total_results": commerce_total,
        "commerce_high_signal_results": commerce_high_signal,
        "commerce_domain_coverage": len(commerce_domains),
        "commerce_top_domains": commerce_domains[:12],
        "social_sample_urls": [
            item.get("url")
            for item in social_results[:8]
            if isinstance(item, dict) and item.get("url")
        ],
        "commerce_sample_urls": [
            item.get("url")
            for item in commerce_results[:8]
            if isinstance(item, dict) and item.get("url")
        ],
    }

    return ScenarioResult(
        name="social_and_commerce_pipeline",
        status=status,
        duration_sec=asyncio.get_running_loop().time() - started,
        metrics=metrics,
        errors=errors,
    )


async def run_academic_and_relation() -> ScenarioResult:
    started = asyncio.get_running_loop().time()
    errors: List[str] = []

    agent = WebAgent()
    await agent._init()
    try:
        academic_resp = await agent.search_academic(
            "retrieval augmented generation evaluation benchmark",
            num_results=8,
            include_code=True,
            fetch_abstracts=True,
        )

        mind_resp = await agent.mindsearch_research(
            query="RAG benchmark and hallucination mitigation research trend",
            max_turns=2,
            max_branches=3,
            num_results=6,
            crawl_top=1,
            use_english=True,
            channel_profiles=["news", "platforms"],
            planner_name="heuristic",
            strict_expand=True,
        )
    finally:
        await agent.close()

    academic_data = academic_resp.data or {}
    mind_data = mind_resp.data or {}

    papers = academic_data.get("papers", []) if isinstance(academic_data.get("papers"), list) else []
    code_projects = academic_data.get("code_projects", []) if isinstance(academic_data.get("code_projects"), list) else []
    academic_citations = academic_data.get("citations", []) if isinstance(academic_data.get("citations"), list) else []

    mind_citations = mind_data.get("citations", []) if isinstance(mind_data.get("citations"), list) else []
    mind_compat = mind_data.get("mindsearch_compat", {}) if isinstance(mind_data.get("mindsearch_compat"), dict) else {}
    adjacency = mind_compat.get("adjacency_list", {}) if isinstance(mind_compat.get("adjacency_list"), dict) else {}
    node_map = mind_compat.get("node", {}) if isinstance(mind_compat.get("node"), dict) else {}

    edge_count = 0
    for edges in adjacency.values():
        if isinstance(edges, list):
            edge_count += len(edges)

    if not academic_resp.success:
        errors.append(academic_resp.error or "academic_failed")
    if not mind_resp.success:
        errors.append(mind_resp.error or "mindsearch_failed")

    status = "pass"
    if not papers or not mind_citations:
        status = "fail"
    elif edge_count <= 0 or len(node_map) <= 1:
        status = "partial"

    metrics = {
        "academic_paper_count": len(papers),
        "academic_code_count": len(code_projects),
        "academic_citation_count": len(academic_citations),
        "mindsearch_citation_count": len(mind_citations),
        "mindsearch_node_count": len(node_map),
        "mindsearch_edge_count": edge_count,
        "mindsearch_references_text_length": len(str(mind_data.get("references_text", ""))),
        "mindsearch_sample_urls": [
            item.get("url")
            for item in (mind_data.get("results", []) if isinstance(mind_data.get("results"), list) else [])[:10]
            if isinstance(item, dict) and item.get("url")
        ],
    }

    return ScenarioResult(
        name="academic_and_relation_pipeline",
        status=status,
        duration_sec=asyncio.get_running_loop().time() - started,
        metrics=metrics,
        errors=errors,
    )


def _make_markdown(report: Dict[str, Any]) -> str:
    lines: List[str] = []
    lines.append("# Real Regression Report")
    lines.append("")
    lines.append(f"- Timestamp (UTC): {report.get('timestamp_utc', '')}")
    lines.append(f"- Python: {report.get('python', '')}")
    lines.append(f"- Platform: {report.get('platform', '')}")
    lines.append(f"- Search Timeout Env: {report.get('search_timeout_sec', '')}")
    lines.append(f"- Overall: **{report.get('overall_status', '')}**")
    lines.append("")

    for scenario in report.get("scenarios", []):
        name = scenario.get("name", "")
        status = scenario.get("status", "")
        duration = scenario.get("duration_sec", 0)
        metrics = scenario.get("metrics", {})
        errors = scenario.get("errors", [])

        lines.append(f"## {name}")
        lines.append("")
        lines.append(f"- Status: **{status}**")
        lines.append(f"- Duration: {duration}s")
        if isinstance(metrics, dict):
            for key, value in metrics.items():
                lines.append(f"- {key}: {value}")
        if errors:
            lines.append("- errors:")
            for err in errors[:10]:
                lines.append(f"  - {err}")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


async def run(json_out: Path, md_out: Path) -> Dict[str, Any]:
    os.environ.setdefault("WEB_ROOTER_SEARCH_TIMEOUT_SEC", "85")

    scenarios: List[ScenarioResult] = []
    scenarios.append(await run_social_and_commerce())
    scenarios.append(await run_academic_and_relation())

    status_rank = {"pass": 2, "partial": 1, "fail": 0}
    overall = "pass"
    for item in scenarios:
        if status_rank[item.status] < status_rank[overall]:
            overall = item.status

    report = {
        "timestamp_utc": _now_iso(),
        "python": sys.version.replace("\n", " "),
        "platform": f"{platform.system()} {platform.release()}",
        "search_timeout_sec": os.getenv("WEB_ROOTER_SEARCH_TIMEOUT_SEC", ""),
        "overall_status": overall,
        "scenarios": [item.to_dict() for item in scenarios],
    }

    json_out.parent.mkdir(parents=True, exist_ok=True)
    md_out.parent.mkdir(parents=True, exist_ok=True)

    json_out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    md_out.write_text(_make_markdown(report), encoding="utf-8")

    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Run real regression scenarios for web-rooter")
    parser.add_argument(
        "--json-out",
        default=f"temp/real_regression_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
        help="JSON report output path",
    )
    parser.add_argument(
        "--md-out",
        default=f"docs/reports/REAL_REGRESSION_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md",
        help="Markdown report output path",
    )
    args = parser.parse_args()

    json_out = Path(args.json_out).resolve()
    md_out = Path(args.md_out).resolve()

    report = asyncio.run(run(json_out=json_out, md_out=md_out))
    print(json.dumps({
        "overall_status": report.get("overall_status"),
        "json_out": str(json_out),
        "md_out": str(md_out),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

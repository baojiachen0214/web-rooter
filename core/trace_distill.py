"""
Distill verbose workflow execution payload into compact memory-friendly traces.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional
from urllib.parse import urlparse


def distill_workflow_trace(
    payload: Dict[str, Any],
    ir: Optional[Dict[str, Any]] = None,
    max_timeline: int = 24,
    max_domains: int = 12,
) -> Dict[str, Any]:
    if not isinstance(payload, dict):
        return {
            "success": False,
            "summary": "invalid_workflow_payload",
            "timeline": [],
        }

    reports = payload.get("reports") if isinstance(payload.get("reports"), list) else []
    steps = payload.get("steps") if isinstance(payload.get("steps"), dict) else {}
    urls = payload.get("urls") if isinstance(payload.get("urls"), list) else []

    timeline: List[Dict[str, Any]] = []
    completed = 0
    soft_failed = 0
    hard_failed = 0
    for item in reports[:max_timeline]:
        if not isinstance(item, dict):
            continue
        status = str(item.get("status") or "")
        if status == "completed":
            completed += 1
        elif status == "soft_failed":
            soft_failed += 1
        elif status == "failed":
            hard_failed += 1
        timeline.append(
            {
                "id": item.get("id"),
                "tool": item.get("tool"),
                "status": status,
                "duration_ms": int(item.get("duration_ms", 0) or 0),
                "error": item.get("error"),
            }
        )

    loop_stats: List[Dict[str, Any]] = []
    for step_id, data in list(steps.items())[:24]:
        if not isinstance(data, dict):
            continue
        if "count" not in data:
            continue
        loop_stats.append(
            {
                "step": step_id,
                "count": int(data.get("count", 0) or 0),
                "success_count": int(data.get("success_count", 0) or 0),
                "failed_count": int(data.get("failed_count", 0) or 0),
            }
        )

    domains: List[str] = []
    for url in urls:
        if not isinstance(url, str):
            continue
        host = (urlparse(url).hostname or "").lower()
        if not host or host in domains:
            continue
        domains.append(host)
        if len(domains) >= max_domains:
            break

    suggestions = _build_suggestions(
        success=bool(payload.get("success")),
        failed_step=str(payload.get("failed_step") or ""),
        soft_failed_steps=int(payload.get("soft_failed_steps", 0) or 0),
        url_count=len(urls),
    )

    name = str(payload.get("name") or "workflow")
    summary = (
        f"{name}: success={bool(payload.get('success'))}, "
        f"completed={completed}, soft_failed={soft_failed}, hard_failed={hard_failed}, "
        f"urls={len(urls)}"
    )

    trace: Dict[str, Any] = {
        "name": name,
        "success": bool(payload.get("success")),
        "route": (ir or {}).get("route"),
        "skill": (ir or {}).get("skill"),
        "duration_ms": int(payload.get("duration_ms", 0) or 0),
        "failed_step": payload.get("failed_step"),
        "soft_failed_steps": int(payload.get("soft_failed_steps", 0) or 0),
        "step_counts": {
            "total": len(reports),
            "completed": completed,
            "soft_failed": soft_failed,
            "failed": hard_failed,
        },
        "timeline": timeline,
        "loop_stats": loop_stats,
        "url_count": len(urls),
        "top_domains": domains,
        "summary": summary,
        "suggestions": suggestions,
    }
    return trace


def _build_suggestions(
    success: bool,
    failed_step: str,
    soft_failed_steps: int,
    url_count: int,
) -> List[str]:
    hints: List[str] = []
    step = failed_step.lower()
    if "auth" in step or "login" in step:
        hints.append("Call auth-hint/auth-template first, then retry with local login profile.")
    if not success and ("read_" in step or "visit" in step or "fetch" in step):
        hints.append("Retry with --js or enable crawl-assist for dynamic/challenge pages.")
    if url_count == 0:
        hints.append("Expand channels or increase top results to improve source recall.")
    if soft_failed_steps > 0:
        hints.append("Inspect soft-failed steps in timeline and tighten skill constraints.")
    return hints[:3]

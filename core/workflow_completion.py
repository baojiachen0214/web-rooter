from __future__ import annotations

from typing import Any, Dict, List, Tuple


def evaluate_completion_contract(payload: Dict[str, Any], contract: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(payload, dict):
        return _empty_report("invalid_payload")
    if not isinstance(contract, dict) or not contract:
        return _empty_report("missing_contract")

    required = [str(item).strip() for item in (contract.get("required_outputs") or []) if str(item).strip()]
    gates = contract.get("quality_gates") if isinstance(contract.get("quality_gates"), dict) else {}
    fallback_chain = [str(item).strip() for item in (contract.get("fallback_chain") or []) if str(item).strip()]
    evidence = _collect_evidence(payload)

    output_checks: Dict[str, Dict[str, Any]] = {}
    satisfied_required = 0
    missing_outputs: List[str] = []
    for key in required:
        ok, detail = _check_output(key, evidence)
        output_checks[key] = {"ok": ok, "detail": detail}
        if ok:
            satisfied_required += 1
        else:
            missing_outputs.append(key)

    gate_checks: Dict[str, Dict[str, Any]] = {}
    gate_failures: List[str] = []
    for key, expected in gates.items():
        ok, detail = _check_gate(key, expected, evidence)
        gate_checks[key] = {"ok": ok, "detail": detail, "expected": expected}
        if not ok:
            gate_failures.append(key)

    required_total = len(required)
    completion_ratio = (satisfied_required / required_total) if required_total else 1.0
    completion_percent = int(round(completion_ratio * 100))
    if gate_failures and not missing_outputs and completion_percent == 100:
        completion_percent = max(80, 100 - min(20, 10 * len(gate_failures)))

    if missing_outputs:
        status = "partial" if satisfied_required > 0 else "incomplete"
    else:
        status = "complete" if not gate_failures else "partial"

    summary = _build_summary(status, completion_percent, missing_outputs, gate_failures)
    return {
        "status": status,
        "completion_percent": completion_percent,
        "required_outputs": required,
        "outputs": output_checks,
        "quality_gates": gate_checks,
        "missing_outputs": missing_outputs,
        "gate_failures": gate_failures,
        "fallback_chain": fallback_chain,
        "should_fallback": bool((missing_outputs or gate_failures) and fallback_chain),
        "evidence": evidence,
        "summary": summary,
    }


def summarize_completion_report(report: Dict[str, Any]) -> str:
    if not isinstance(report, dict):
        return "完成度：未知"
    status = str(report.get("status") or "unknown")
    percent = int(report.get("completion_percent") or 0)
    missing = report.get("missing_outputs") if isinstance(report.get("missing_outputs"), list) else []
    gate_failures = report.get("gate_failures") if isinstance(report.get("gate_failures"), list) else []
    parts = [f"完成度：{percent}%", f"状态：{status}"]
    if missing:
        parts.append("缺失：" + ", ".join(str(item) for item in missing))
    if gate_failures:
        parts.append("质量门未过：" + ", ".join(str(item) for item in gate_failures))
    return "；".join(parts)


def _empty_report(reason: str) -> Dict[str, Any]:
    return {
        "status": "unknown",
        "completion_percent": 0,
        "required_outputs": [],
        "outputs": {},
        "quality_gates": {},
        "missing_outputs": [],
        "gate_failures": [],
        "fallback_chain": [],
        "should_fallback": False,
        "evidence": {},
        "summary": f"completion_unavailable:{reason}",
    }


def _build_summary(status: str, percent: int, missing_outputs: List[str], gate_failures: List[str]) -> str:
    parts = [f"status={status}", f"completion={percent}%"]
    if missing_outputs:
        parts.append("missing=" + ",".join(missing_outputs))
    if gate_failures:
        parts.append("gates=" + ",".join(gate_failures))
    return " | ".join(parts)


def _collect_evidence(payload: Dict[str, Any]) -> Dict[str, Any]:
    steps = payload.get("steps") if isinstance(payload.get("steps"), dict) else {}
    reports = payload.get("reports") if isinstance(payload.get("reports"), list) else []
    evidence = {
        "step_ids": list(steps.keys()),
        "report_statuses": {str(item.get("id")): str(item.get("status")) for item in reports if isinstance(item, dict)},
        "search_hits": 0,
        "auth_hint_checked": False,
        "browser_used": False,
        "body_present": False,
        "author_present": False,
        "engagement_present": False,
        "comments_present": False,
        "comments_count": 0,
        "captured_platform": "",
    }

    for step_id, data in steps.items():
        if not isinstance(data, dict):
            continue
        if step_id == "auth_hint":
            evidence["auth_hint_checked"] = True
        if step_id == "social_search":
            results = data.get("results") if isinstance(data.get("results"), list) else []
            evidence["search_hits"] = max(evidence["search_hits"], len(results))
        if step_id in {"read_target", "extract_social_signals"}:
            _merge_read_extract_evidence(data, evidence)
        if "items" in data and isinstance(data.get("items"), list):
            for item in data.get("items") or []:
                if not isinstance(item, dict):
                    continue
                result = item.get("result") if isinstance(item.get("result"), dict) else {}
                _merge_read_extract_evidence(result, evidence)
    return evidence


def _merge_read_extract_evidence(data: Dict[str, Any], evidence: Dict[str, Any]) -> None:
    if not isinstance(data, dict):
        return
    metadata = data.get("metadata") if isinstance(data.get("metadata"), dict) else {}
    payload_data = data.get("data") if isinstance(data.get("data"), dict) else data
    if metadata.get("fetch_mode") or payload_data.get("fetch_mode"):
        mode = str(metadata.get("fetch_mode") or payload_data.get("fetch_mode") or "")
        if "browser" in mode:
            evidence["browser_used"] = True
    platform = str(payload_data.get("platform") or metadata.get("platform") or "").strip()
    if platform:
        evidence["captured_platform"] = platform

    detail = None
    for key in ("note_detail", "video_detail", "social_detail"):
        candidate = payload_data.get(key)
        if isinstance(candidate, dict):
            detail = candidate
            break
    if detail is None and isinstance(payload_data.get("social_detail"), dict):
        detail = payload_data.get("social_detail")
    if detail is None:
        detail = {}

    body = _first_text(
        detail.get("body"),
        detail.get("desc"),
        payload_data.get("text_preview"),
        payload_data.get("extracted"),
    )
    if body:
        evidence["body_present"] = True
    author = _first_text(
        detail.get("author_name"),
        detail.get("owner_name"),
        detail.get("author"),
    )
    if author:
        evidence["author_present"] = True
    if _has_engagement(detail) or _has_engagement(payload_data):
        evidence["engagement_present"] = True

    comments = payload_data.get("comments") if isinstance(payload_data.get("comments"), list) else []
    if not comments and isinstance(detail, dict):
        comments = detail.get("comments") if isinstance(detail.get("comments"), list) else []
    comment_count = len([item for item in comments if isinstance(item, dict)])
    if comment_count > 0:
        evidence["comments_present"] = True
        evidence["comments_count"] = max(int(evidence.get("comments_count") or 0), comment_count)

    extracted_text = _first_text(payload_data.get("extracted"))
    if extracted_text and not evidence["body_present"]:
        evidence["body_present"] = True
    if extracted_text and ("评论" in extracted_text or "comment" in extracted_text.lower()) and not evidence["comments_present"]:
        evidence["comments_present"] = True


def _has_engagement(detail: Dict[str, Any]) -> bool:
    if not isinstance(detail, dict):
        return False
    keys = [
        "liked_count", "comment_count", "reply_count", "view_count", "like_count",
        "share_count", "favorite_count", "danmaku_count", "collected_count",
    ]
    for key in keys:
        value = detail.get(key)
        if value not in (None, "", 0, "0"):
            return True
    stat = detail.get("stat")
    if isinstance(stat, dict) and any(v not in (None, "", 0, "0") for v in stat.values()):
        return True
    return False


def _first_text(*values: Any) -> str:
    for value in values:
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _check_output(key: str, evidence: Dict[str, Any]) -> Tuple[bool, str]:
    mapping = {
        "body": (bool(evidence.get("body_present")), "body_present"),
        "author": (bool(evidence.get("author_present")), "author_present"),
        "engagement": (bool(evidence.get("engagement_present")), "engagement_present"),
        "comments": (bool(evidence.get("comments_present")), f"comments_count={int(evidence.get('comments_count') or 0)}"),
    }
    return mapping.get(key, (False, "unsupported_output"))


def _check_gate(key: str, expected: Any, evidence: Dict[str, Any]) -> Tuple[bool, str]:
    if key == "search_hits_required":
        actual = int(evidence.get("search_hits") or 0)
        minimum = int(expected or 0)
        return actual >= minimum, f"search_hits={actual}"
    if key == "comment_capture_preferred":
        actual = int(evidence.get("comments_count") or 0)
        if not expected:
            return True, f"comments_count={actual}"
        return actual > 0, f"comments_count={actual}"
    if key == "browser_required":
        actual = bool(evidence.get("browser_used"))
        return (actual if expected else True), f"browser_used={actual}"
    if key == "auth_hint_checked":
        actual = bool(evidence.get("auth_hint_checked"))
        return actual if expected else True, f"auth_hint_checked={actual}"
    return True, "gate_not_implemented"

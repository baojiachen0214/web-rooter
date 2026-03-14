"""
Declarative workflow runner for AI-driven crawl orchestration.

Goal:
- avoid hard-coded crawler scripts for every website
- expose stable, composable crawl/search primitives
- let outer AI decide what to crawl, how to crawl, and in what order
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import time
from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from core.academic_search import AcademicSource
from core.search.advanced import (
    AdvancedSearchEngine,
    DeepSearchEngine,
    search_commerce,
    search_social_media,
    search_tech,
)

if TYPE_CHECKING:
    from agents.web_agent import WebAgent

logger = logging.getLogger(__name__)


_FULL_TOKEN_PATTERN = re.compile(r"^\$\{([^}]+)\}$")
_TOKEN_PATTERN = re.compile(r"\$\{([^}]+)\}")
_SEGMENT_PATTERN = re.compile(r"^([^\[\]]+)?(?:\[(\d+)\])?$")


def _as_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "on"}:
        return True
    if text in {"0", "false", "no", "off"}:
        return False
    return default


def _as_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _as_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _normalize_result(result: Any) -> Any:
    if hasattr(result, "to_dict"):
        try:
            return result.to_dict()
        except Exception:
            return result
    return result


def _looks_success(payload: Any) -> bool:
    if isinstance(payload, dict):
        if "success" in payload:
            return bool(payload.get("success"))
        error = payload.get("error")
        if isinstance(error, str) and error.strip():
            return False
    return True


def _extract_output_error(payload: Any) -> Optional[str]:
    if isinstance(payload, dict):
        error = payload.get("error")
        if isinstance(error, str) and error.strip():
            return error.strip()
        content = payload.get("content")
        if isinstance(content, str) and "失败" in content:
            return content.strip()[:240]
    return None


def _collect_urls(payload: Any, max_urls: int = 200) -> List[str]:
    urls: List[str] = []
    seen: set[str] = set()

    def _push(value: Any) -> None:
        if not isinstance(value, str):
            return
        url = value.strip()
        if not url.startswith(("http://", "https://")):
            return
        if url in seen:
            return
        seen.add(url)
        urls.append(url)

    def _walk(value: Any) -> None:
        if len(urls) >= max_urls:
            return
        if isinstance(value, dict):
            for key, item in value.items():
                if key in {"url", "href"}:
                    _push(item)
                elif key == "urls" and isinstance(item, list):
                    for entry in item:
                        _push(entry)
                else:
                    _walk(item)
        elif isinstance(value, list):
            for item in value:
                _walk(item)

    _walk(payload)
    return urls


def available_workflow_templates() -> List[str]:
    return [
        "social_comments",
        "academic_relations",
    ]


def build_workflow_template(scenario: str = "social_comments") -> Dict[str, Any]:
    normalized = str(scenario or "").strip().lower()
    if normalized in {"social", "social_comments", "social-comment", "social-comment-mining"}:
        return {
            "name": "social-comment-mining",
            "description": "Search social platforms, visit top hits, then extract comment evidence.",
            "variables": {
                "topic": "手机 续航 评测",
                "platforms": ["xiaohongshu", "zhihu", "weibo", "bilibili", "tieba", "douyin"],
                "top_hits": 6,
                "use_browser": True,
            },
            "steps": [
                {
                    "id": "social_search",
                    "tool": "social",
                    "args": {
                        "query": "${vars.topic} 评论 用户反馈",
                        "platforms": "${vars.platforms}",
                    },
                },
                {
                    "id": "visit_top_hits",
                    "tool": "fetch_html",
                    "for_each": "${steps.social_search.results}",
                    "item_alias": "hit",
                    "max_items": "${vars.top_hits}",
                    "continue_on_error": True,
                    "args": {
                        "url": "${local.hit.url}",
                        "use_browser": "${vars.use_browser}",
                        "auto_fallback": True,
                        "max_chars": 60000,
                    },
                },
                {
                    "id": "extract_comment_signals",
                    "tool": "extract",
                    "for_each": "${steps.visit_top_hits.items}",
                    "item_alias": "page",
                    "max_items": "${vars.top_hits}",
                    "continue_on_error": True,
                    "args": {
                        "url": "${local.page.input.url}",
                        "target": "提取评论区观点、情绪倾向、代表性原句、作者信息、互动数据",
                    },
                },
            ],
        }

    if normalized in {"academic", "academic_relations", "paper-relations", "paper_relation"}:
        return {
            "name": "paper-relation-mining",
            "description": "Search papers and relation context, then visit top paper pages for evidence.",
            "variables": {
                "topic": "retrieval augmented generation evaluation benchmark",
                "paper_sources": ["arxiv"],
                "num_results": 6,
                "crawl_top_papers": 5,
            },
            "runtime": {
                "budget_sec": 180,
                "min_optional_remaining_sec": 30,
                "early_stop_soft_failed_steps": 2,
            },
            "steps": [
                {
                    "id": "academic_search",
                    "tool": "academic",
                    "timeout_sec": 60,
                    "degrade_below_sec": 120,
                    "degrade_args": {
                        "sources": ["arxiv"],
                        "num_results": 4,
                        "fetch_abstracts": False,
                        "include_code": False,
                    },
                    "args": {
                        "query": "${vars.topic}",
                        "num_results": "${vars.num_results}",
                        "include_code": False,
                        "fetch_abstracts": True,
                        "sources": "${vars.paper_sources}",
                    },
                },
                {
                    "id": "visit_top_papers",
                    "tool": "fetch_html",
                    "for_each": "${steps.academic_search.data.papers}",
                    "item_alias": "paper",
                    "max_items": "${vars.crawl_top_papers}",
                    "timeout_sec": 40,
                    "item_timeout_sec": 12,
                    "continue_on_error": True,
                    "args": {
                        "url": "${local.paper.url}",
                        "use_browser": False,
                        "auto_fallback": True,
                        "max_chars": 60000,
                    },
                },
                {
                    "id": "mindsearch_relation",
                    "tool": "mindsearch",
                    "continue_on_error": True,
                    "timeout_sec": 45,
                    "degrade_below_sec": 35,
                    "degrade_args": {
                        "max_turns": 1,
                        "max_branches": 2,
                        "num_results": 4,
                        "crawl_top": 0,
                        "channel_profiles": ["news"],
                    },
                    "args": {
                        "query": "${vars.topic}",
                        "max_turns": 1,
                        "max_branches": 4,
                        "num_results": 6,
                        "crawl_top": 0,
                        "planner_name": "heuristic",
                        "strict_expand": True,
                        "channel_profiles": ["news", "platforms"],
                    },
                },
            ],
        }

    raise ValueError(
        f"Unknown workflow template scenario: {scenario}. "
        f"Supported: {', '.join(available_workflow_templates())}"
    )


def get_workflow_schema() -> Dict[str, Any]:
    return {
        "version": "1.0",
        "placeholders": {
            "vars": "${vars.<key>}",
            "steps": "${steps.<step_id>.<path>}",
            "last": "${last.<path>}",
            "local": "${local.<alias>.<path>}",
            "env": "${env.<ENV_NAME>}",
        },
        "step_fields": {
            "id": "unique step id",
            "tool": "tool name, see tools below",
            "args": "tool arguments (supports placeholders)",
            "for_each": "optional list expression to run the step for each item",
            "item_alias": "loop variable name for for_each (default: item)",
            "max_items": "optional per-step cap for for_each",
            "item_timeout_sec": "optional per-item timeout in for_each loops",
            "timeout_sec": "optional per-step timeout (seconds)",
            "continue_on_error": "when true, workflow continues after this step fails",
            "degrade_below_sec": "when remaining global budget below this threshold, apply degrade_args before execute",
            "degrade_args": "optional args patch for degraded execution",
            "save_as": "optional variable key to save this step result into vars",
        },
        "runtime_fields": {
            "budget_sec": "optional global workflow budget (seconds), 0 means disabled",
            "min_optional_remaining_sec": "skip optional step when remaining budget below this threshold",
            "early_stop_soft_failed_steps": "early-stop when soft-failed steps reach this threshold (0 disables)",
            "min_step_timeout_sec": "minimum step timeout cap in low-budget mode",
        },
        "tools": {
            "visit": {"args": ["url", "use_browser", "auto_fallback"]},
            "fetch_html": {"args": ["url", "use_browser", "auto_fallback", "max_chars"]},
            "search_internet": {"args": ["query", "num_results", "auto_crawl", "crawl_pages"]},
            "deep_search": {"args": ["query", "num_results", "use_english", "crawl_top", "query_variants", "channel_profiles", "engines"]},
            "mindsearch": {"args": ["query", "max_turns", "max_branches", "num_results", "crawl_top", "use_english", "channel_profiles", "planner_name", "strict_expand"]},
            "social": {"args": ["query", "platforms"]},
            "commerce": {"args": ["query", "platforms"]},
            "tech": {"args": ["query", "sources"]},
            "academic": {"args": ["query", "sources", "num_results", "fetch_abstracts", "include_code"]},
            "crawl": {"args": ["url", "max_pages", "max_depth", "pattern", "allow_external", "allow_subdomains"]},
            "extract": {"args": ["url", "target"]},
            "auth_hint": {"args": ["url"]},
            "auth_profiles": {"args": []},
            "challenge_profiles": {"args": []},
            "context_snapshot": {"args": ["limit", "event_type"]},
            "artifact_snapshot": {"args": ["node_limit", "edge_limit", "node_kind"]},
            "runtime_events_snapshot": {"args": ["limit", "event_type", "source", "since_seq"]},
            "runtime_pressure_snapshot": {"args": ["refresh"]},
            "budget_telemetry_snapshot": {"args": ["refresh"]},
            "echo": {"args": ["value"]},
            "sleep": {"args": ["seconds"]},
        },
        "templates": available_workflow_templates(),
    }


@dataclass
class WorkflowStepReport:
    id: str
    tool: str
    status: str
    duration_ms: int
    continue_on_error: bool = False
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        data: Dict[str, Any] = {
            "id": self.id,
            "tool": self.tool,
            "status": self.status,
            "duration_ms": self.duration_ms,
            "continue_on_error": self.continue_on_error,
        }
        if self.error:
            data["error"] = self.error
        if self.metadata:
            data["metadata"] = self.metadata
        return data


@dataclass
class WorkflowRuntime:
    variables: Dict[str, Any] = field(default_factory=dict)
    steps: Dict[str, Any] = field(default_factory=dict)
    last: Any = None


class WorkflowRunner:
    """Execute a declarative workflow spec with placeholder resolution."""

    _ACADEMIC_SOURCE_MAP = {
        "arxiv": AcademicSource.ARXIV,
        "google_scholar": AcademicSource.GOOGLE_SCHOLAR,
        "scholar": AcademicSource.GOOGLE_SCHOLAR,
        "semantic_scholar": AcademicSource.SEMANTIC_SCHOLAR,
        "semantic": AcademicSource.SEMANTIC_SCHOLAR,
        "pubmed": AcademicSource.PUBMED,
        "ieee": AcademicSource.IEEE,
        "cnki": AcademicSource.CNKI,
        "wanfang": AcademicSource.WANFANG,
        "paper_with_code": AcademicSource.PAPER_WITH_CODE,
        "pwc": AcademicSource.PAPER_WITH_CODE,
        "github": AcademicSource.GITHUB,
        "gitee": AcademicSource.GITEE,
    }

    _ENGINE_ALIAS = {item.value.lower(): item for item in AdvancedSearchEngine}
    _DEFAULT_STEP_TIMEOUT_SEC = 180
    _DEFAULT_MIN_OPTIONAL_REMAINING_SEC = 25
    _DEFAULT_MIN_STEP_TIMEOUT_SEC = 5

    def __init__(self, agent: "WebAgent"):
        self._agent = agent

    async def run_spec(
        self,
        spec: Dict[str, Any],
        variable_overrides: Optional[Dict[str, Any]] = None,
        strict: bool = False,
    ) -> Dict[str, Any]:
        if not isinstance(spec, dict):
            raise ValueError("workflow spec must be a JSON object")
        steps = spec.get("steps")
        if not isinstance(steps, list) or not steps:
            raise ValueError("workflow spec must include non-empty 'steps'")

        runtime = WorkflowRuntime(
            variables=deepcopy(spec.get("variables", {})) if isinstance(spec.get("variables"), dict) else {},
            steps={},
            last=None,
        )
        if isinstance(variable_overrides, dict):
            runtime.variables.update(variable_overrides)

        runtime_cfg = spec.get("runtime") if isinstance(spec.get("runtime"), dict) else {}

        def _resolve_runtime_int(raw_value: Any, default: int) -> int:
            if raw_value is None:
                return default
            try:
                resolved = self._resolve_value(raw_value, runtime, local_scope={})
            except Exception:
                return default
            return _as_int(resolved, default)

        budget_default = _as_int(os.getenv("WEB_ROOTER_WORKFLOW_BUDGET_SEC", "0"), 0)
        min_optional_default = _as_int(
            os.getenv("WEB_ROOTER_WORKFLOW_MIN_OPTIONAL_STEP_SEC", str(self._DEFAULT_MIN_OPTIONAL_REMAINING_SEC)),
            self._DEFAULT_MIN_OPTIONAL_REMAINING_SEC,
        )
        early_stop_soft_default = _as_int(os.getenv("WEB_ROOTER_WORKFLOW_EARLY_STOP_SOFT_FAILS", "0"), 0)
        min_step_timeout_default = _as_int(
            os.getenv("WEB_ROOTER_WORKFLOW_MIN_STEP_TIMEOUT_SEC", str(self._DEFAULT_MIN_STEP_TIMEOUT_SEC)),
            self._DEFAULT_MIN_STEP_TIMEOUT_SEC,
        )

        budget_sec = max(0, _resolve_runtime_int(runtime_cfg.get("budget_sec"), budget_default))
        min_optional_remaining_sec = max(
            0,
            _resolve_runtime_int(runtime_cfg.get("min_optional_remaining_sec"), min_optional_default),
        )
        early_stop_soft_failed_steps = max(
            0,
            _resolve_runtime_int(runtime_cfg.get("early_stop_soft_failed_steps"), early_stop_soft_default),
        )
        min_step_timeout_sec = max(
            1,
            _resolve_runtime_int(runtime_cfg.get("min_step_timeout_sec"), min_step_timeout_default),
        )

        reports: List[WorkflowStepReport] = []
        failed_step: Optional[str] = None
        started_at = time.time()
        hard_fail = False
        early_stop_reason: Optional[str] = None

        for index, raw_step in enumerate(steps):
            if not isinstance(raw_step, dict):
                raise ValueError(f"workflow step #{index + 1} must be an object")

            step_id = str(raw_step.get("id") or f"step_{index + 1}").strip()
            tool = str(raw_step.get("tool") or "").strip().lower()
            if not tool:
                raise ValueError(f"workflow step '{step_id}' missing 'tool'")
            continue_on_error = _as_bool(raw_step.get("continue_on_error"), default=False)

            start_monotonic = time.perf_counter()
            status = "completed"
            error_text: Optional[str] = None
            report_meta: Dict[str, Any] = {}

            remaining_sec: Optional[float] = None
            if budget_sec > 0:
                elapsed = time.time() - started_at
                remaining_sec = max(0.0, float(budget_sec) - elapsed)
                report_meta["remaining_sec_before"] = round(remaining_sec, 3)

            if remaining_sec is not None and remaining_sec <= 0:
                error_text = f"budget_exhausted:{budget_sec}s"
                runtime.steps[step_id] = {
                    "success": False,
                    "error": error_text,
                    "skipped": True,
                    "reason": "budget_exhausted",
                    "remaining_sec": 0,
                }
                runtime.last = runtime.steps[step_id]
                if continue_on_error:
                    status = "soft_failed"
                    early_stop_reason = "budget_exhausted"
                else:
                    status = "failed"
                    failed_step = step_id
                    hard_fail = True

                duration_ms = int((time.perf_counter() - start_monotonic) * 1000)
                reports.append(
                    WorkflowStepReport(
                        id=step_id,
                        tool=tool,
                        status=status,
                        duration_ms=duration_ms,
                        continue_on_error=continue_on_error,
                        error=error_text,
                        metadata=report_meta,
                    )
                )
                break

            if (
                remaining_sec is not None
                and continue_on_error
                and min_optional_remaining_sec > 0
                and remaining_sec < float(min_optional_remaining_sec)
            ):
                error_text = (
                    f"budget_low_skip_optional:remaining={remaining_sec:.1f}s"
                    f"<{min_optional_remaining_sec}s"
                )
                runtime.steps[step_id] = {
                    "success": False,
                    "error": error_text,
                    "skipped": True,
                    "reason": "budget_low_skip_optional",
                    "remaining_sec": round(remaining_sec, 3),
                }
                runtime.last = runtime.steps[step_id]
                status = "soft_failed"
                report_meta["skipped_optional_due_budget"] = True

                duration_ms = int((time.perf_counter() - start_monotonic) * 1000)
                reports.append(
                    WorkflowStepReport(
                        id=step_id,
                        tool=tool,
                        status=status,
                        duration_ms=duration_ms,
                        continue_on_error=continue_on_error,
                        error=error_text,
                        metadata=report_meta,
                    )
                )

                if (
                    early_stop_soft_failed_steps > 0
                    and sum(1 for item in reports if item.status == "soft_failed") >= early_stop_soft_failed_steps
                ):
                    early_stop_reason = f"soft_failed_threshold:{early_stop_soft_failed_steps}"
                    break
                continue

            try:
                step_payload = raw_step
                if remaining_sec is not None:
                    degrade_threshold = max(
                        0,
                        _as_int(
                            self._resolve_value(
                                raw_step.get("degrade_below_sec"),
                                runtime,
                                local_scope={},
                            ),
                            0,
                        ),
                    )
                    degrade_args = raw_step.get("degrade_args")
                    if (
                        degrade_threshold > 0
                        and remaining_sec < float(degrade_threshold)
                        and isinstance(degrade_args, dict)
                    ):
                        resolved_degrade_args = self._resolve_value(degrade_args, runtime, local_scope={})
                        if isinstance(resolved_degrade_args, dict):
                            step_payload = deepcopy(raw_step)
                            step_args = step_payload.get("args")
                            if not isinstance(step_args, dict):
                                step_args = {}
                            step_args.update(resolved_degrade_args)
                            step_payload["args"] = step_args
                            report_meta["degraded"] = True
                            report_meta["degrade_threshold_sec"] = degrade_threshold

                timeout_sec = max(
                    5,
                    _as_int(
                        self._resolve_value(
                            step_payload.get("timeout_sec"),
                            runtime,
                            local_scope={},
                        ),
                        int(os.getenv("WEB_ROOTER_WORKFLOW_STEP_TIMEOUT_SEC", str(self._DEFAULT_STEP_TIMEOUT_SEC))),
                    ),
                )
                effective_timeout = timeout_sec
                if remaining_sec is not None:
                    budget_timeout_cap = max(1, int(remaining_sec))
                    effective_timeout = min(timeout_sec, budget_timeout_cap)
                    if continue_on_error and effective_timeout < min_step_timeout_sec:
                        error_text = (
                            f"budget_low_skip_optional_timeout:remaining={remaining_sec:.1f}s"
                            f", timeout_cap={effective_timeout}s"
                        )
                        runtime.steps[step_id] = {
                            "success": False,
                            "error": error_text,
                            "skipped": True,
                            "reason": "budget_low_skip_optional_timeout",
                            "remaining_sec": round(remaining_sec, 3),
                        }
                        runtime.last = runtime.steps[step_id]
                        status = "soft_failed"
                        report_meta["skipped_optional_due_timeout_cap"] = True
                        duration_ms = int((time.perf_counter() - start_monotonic) * 1000)
                        reports.append(
                            WorkflowStepReport(
                                id=step_id,
                                tool=tool,
                                status=status,
                                duration_ms=duration_ms,
                                continue_on_error=continue_on_error,
                                error=error_text,
                                metadata=report_meta,
                            )
                        )
                        if (
                            early_stop_soft_failed_steps > 0
                            and sum(1 for item in reports if item.status == "soft_failed")
                            >= early_stop_soft_failed_steps
                        ):
                            early_stop_reason = f"soft_failed_threshold:{early_stop_soft_failed_steps}"
                            break
                        continue

                report_meta["timeout_sec"] = effective_timeout
                output = await asyncio.wait_for(
                    self._run_step(step_payload, runtime),
                    timeout=effective_timeout,
                )
                runtime.steps[step_id] = output
                runtime.last = output

                save_as = str(step_payload.get("save_as") or "").strip()
                if save_as:
                    runtime.variables[save_as] = output

                step_ok = _looks_success(output)
                if not step_ok and not error_text:
                    error_text = _extract_output_error(output)
                if not step_ok:
                    # strict 模式不再覆盖 continue_on_error：
                    # 可选步骤（continue_on_error=true）在 strict 下仍按 soft_failed 处理，
                    # 避免外部网络/反爬波动导致整条 workflow 误判失败。
                    if not continue_on_error:
                        status = "failed"
                        failed_step = step_id
                        hard_fail = True
                    else:
                        status = "soft_failed"

            except asyncio.TimeoutError:
                error_text = f"step_timeout:{report_meta.get('timeout_sec', 'unknown')}s"
                runtime.steps[step_id] = {
                    "success": False,
                    "error": error_text,
                }
                runtime.last = runtime.steps[step_id]
                if continue_on_error:
                    status = "soft_failed"
                else:
                    status = "failed"
                    failed_step = step_id
                    hard_fail = True
                logger.warning("workflow step timeout (%s): %s", step_id, error_text)
            except Exception as exc:
                error_text = str(exc)
                runtime.steps[step_id] = {"success": False, "error": error_text}
                runtime.last = runtime.steps[step_id]

                if not continue_on_error:
                    status = "failed"
                    failed_step = step_id
                    hard_fail = True
                else:
                    status = "soft_failed"
                logger.warning("workflow step failed (%s): %s", step_id, exc)

            duration_ms = int((time.perf_counter() - start_monotonic) * 1000)
            reports.append(
                WorkflowStepReport(
                    id=step_id,
                    tool=tool,
                    status=status,
                    duration_ms=duration_ms,
                    continue_on_error=continue_on_error,
                    error=error_text,
                    metadata=report_meta,
                )
            )

            if hard_fail:
                break
            if (
                early_stop_soft_failed_steps > 0
                and sum(1 for item in reports if item.status == "soft_failed") >= early_stop_soft_failed_steps
            ):
                early_stop_reason = f"soft_failed_threshold:{early_stop_soft_failed_steps}"
                break

        finished_at = time.time()
        report_dicts = [item.to_dict() for item in reports]
        soft_failed = sum(1 for item in reports if item.status == "soft_failed")
        urls = _collect_urls(runtime.steps)

        result: Dict[str, Any] = {
            "success": not hard_fail,
            "name": str(spec.get("name") or "workflow"),
            "description": str(spec.get("description") or ""),
            "strict": strict,
            "started_at": started_at,
            "finished_at": finished_at,
            "duration_ms": int((finished_at - started_at) * 1000),
            "failed_step": failed_step,
            "soft_failed_steps": soft_failed,
            "early_stop_reason": early_stop_reason,
            "budget_sec": budget_sec,
            "budget_remaining_sec": (
                max(0.0, round(float(budget_sec) - (finished_at - started_at), 3))
                if budget_sec > 0
                else None
            ),
            "variables": runtime.variables,
            "steps": runtime.steps,
            "reports": report_dicts,
            "urls": urls[:200],
            "schema_version": "1.0",
        }
        return result

    async def _run_step(self, step: Dict[str, Any], runtime: WorkflowRuntime) -> Any:
        tool = str(step.get("tool") or "").strip().lower()
        args_template = step.get("args", {})
        if args_template is None:
            args_template = {}
        if not isinstance(args_template, dict):
            raise ValueError(f"step args must be an object for tool: {tool}")

        loop_expr = step.get("for_each")
        if loop_expr is None:
            args = self._resolve_value(args_template, runtime, local_scope={})
            return await self._invoke_tool(tool, args)

        loop_items = self._resolve_value(loop_expr, runtime, local_scope={})
        if not isinstance(loop_items, list):
            raise ValueError(f"for_each expects a list, got: {type(loop_items).__name__}")

        max_items_raw = step.get("max_items", len(loop_items))
        max_items = max(0, _as_int(self._resolve_value(max_items_raw, runtime, local_scope={}), len(loop_items)))
        item_alias = str(step.get("item_alias") or "item").strip() or "item"
        stop_on_item_error = _as_bool(step.get("stop_on_item_error"), default=False)
        item_timeout_sec = max(
            0,
            _as_int(
                self._resolve_value(step.get("item_timeout_sec"), runtime, local_scope={}),
                0,
            ),
        )

        items: List[Dict[str, Any]] = []
        success_count = 0
        failed_count = 0

        for index, item in enumerate(loop_items[:max_items]):
            local_scope = {
                item_alias: item,
                "index": index,
            }
            call_args = self._resolve_value(args_template, runtime, local_scope=local_scope)
            try:
                if item_timeout_sec > 0:
                    call_result = await asyncio.wait_for(
                        self._invoke_tool(tool, call_args),
                        timeout=item_timeout_sec,
                    )
                else:
                    call_result = await self._invoke_tool(tool, call_args)
                ok = _looks_success(call_result)
                if ok:
                    success_count += 1
                else:
                    failed_count += 1
                items.append(
                    {
                        "index": index,
                        "success": ok,
                        "input": call_args,
                        "result": call_result,
                    }
                )
                if not ok and stop_on_item_error:
                    break
            except asyncio.TimeoutError:
                failed_count += 1
                items.append(
                    {
                        "index": index,
                        "success": False,
                        "input": call_args,
                        "error": f"item_timeout:{item_timeout_sec}s",
                    }
                )
                if stop_on_item_error:
                    break
            except Exception as exc:
                failed_count += 1
                items.append(
                    {
                        "index": index,
                        "success": False,
                        "input": call_args,
                        "error": str(exc),
                    }
                )
                if stop_on_item_error:
                    break

        return {
            "success": failed_count == 0,
            "count": len(items),
            "success_count": success_count,
            "failed_count": failed_count,
            "items": items,
        }

    async def _invoke_tool(self, tool: str, args: Dict[str, Any]) -> Any:
        if not isinstance(args, dict):
            raise ValueError("tool args must resolve to an object")

        name = tool.lower()
        if name in {"visit", "fetch", "web_fetch"}:
            url = str(args.get("url") or "").strip()
            if not url:
                raise ValueError("visit requires args.url")
            result = await self._agent.visit(
                url=url,
                use_browser=_as_bool(args.get("use_browser"), default=False),
                auto_fallback=_as_bool(args.get("auto_fallback"), default=True),
            )
            return _normalize_result(result)

        if name in {"fetch_html", "web_fetch_html", "html"}:
            url = str(args.get("url") or "").strip()
            if not url:
                raise ValueError("fetch_html requires args.url")
            result = await self._agent.fetch_html(
                url=url,
                use_browser=_as_bool(args.get("use_browser"), default=False),
                auto_fallback=_as_bool(args.get("auto_fallback"), default=True),
                max_chars=max(1000, _as_int(args.get("max_chars"), 80000)),
            )
            return _normalize_result(result)

        if name in {"search_internet", "web", "search", "web_search"}:
            query = str(args.get("query") or "").strip()
            if not query:
                raise ValueError("search_internet requires args.query")
            result = await self._agent.search_internet(
                query=query,
                num_results=max(1, _as_int(args.get("num_results"), 10)),
                auto_crawl=_as_bool(args.get("auto_crawl"), default=False),
                crawl_pages=max(0, _as_int(args.get("crawl_pages"), 3)),
            )
            return _normalize_result(result)

        if name in {"deep_search", "deep"}:
            query = str(args.get("query") or "").strip()
            if not query:
                raise ValueError("deep_search requires args.query")
            deep_search = DeepSearchEngine()
            try:
                raw_engines = args.get("engines")
                engines = self._normalize_engines(raw_engines)
                payload = await deep_search.deep_search(
                    query=query,
                    num_results=max(1, _as_int(args.get("num_results"), 10)),
                    use_english=_as_bool(args.get("use_english"), default=False),
                    crawl_top=max(0, _as_int(args.get("crawl_top"), 0)),
                    query_variants=max(1, _as_int(args.get("query_variants"), 1)),
                    channel_profiles=args.get("channel_profiles"),
                    engines=engines,
                )
                return _normalize_result(payload)
            finally:
                await deep_search.close()

        if name in {"mindsearch", "ms"}:
            query = str(args.get("query") or "").strip()
            if not query:
                raise ValueError("mindsearch requires args.query")
            result = await self._agent.mindsearch_research(
                query=query,
                max_turns=max(1, _as_int(args.get("max_turns"), 3)),
                max_branches=max(1, _as_int(args.get("max_branches"), 4)),
                num_results=max(1, _as_int(args.get("num_results"), 8)),
                crawl_top=max(0, _as_int(args.get("crawl_top"), 1)),
                use_english=_as_bool(args.get("use_english"), default=False),
                channel_profiles=args.get("channel_profiles"),
                planner_name=(str(args.get("planner_name")).strip() if args.get("planner_name") is not None else None),
                strict_expand=args.get("strict_expand"),
            )
            return _normalize_result(result)

        if name in {"social", "search_social", "web_search_social"}:
            query = str(args.get("query") or "").strip()
            if not query:
                raise ValueError("social requires args.query")
            return await search_social_media(query=query, platforms=args.get("platforms"))

        if name in {"commerce", "shopping", "search_commerce", "web_search_commerce"}:
            query = str(args.get("query") or "").strip()
            if not query:
                raise ValueError("commerce requires args.query")
            return await search_commerce(query=query, platforms=args.get("platforms"))

        if name in {"tech", "search_tech", "web_search_tech"}:
            query = str(args.get("query") or "").strip()
            if not query:
                raise ValueError("tech requires args.query")
            return await search_tech(query=query, sources=args.get("sources"))

        if name in {"academic", "search_academic", "web_search_academic"}:
            query = str(args.get("query") or "").strip()
            if not query:
                raise ValueError("academic requires args.query")
            sources = self._normalize_academic_sources(args.get("sources"))
            result = await self._agent.search_academic(
                query=query,
                sources=sources or None,
                num_results=max(1, _as_int(args.get("num_results"), 10)),
                fetch_abstracts=_as_bool(args.get("fetch_abstracts"), default=True),
                include_code=_as_bool(args.get("include_code"), default=True),
            )
            return _normalize_result(result)

        if name in {"crawl", "web_crawl"}:
            url = str(args.get("url") or args.get("start_url") or "").strip()
            if not url:
                raise ValueError("crawl requires args.url/start_url")
            result = await self._agent.crawl(
                url=url,
                max_pages=max(1, _as_int(args.get("max_pages"), 10)),
                max_depth=max(1, _as_int(args.get("max_depth"), 3)),
                pattern=(str(args.get("pattern")).strip() if args.get("pattern") is not None else None),
                allow_external=_as_bool(args.get("allow_external"), default=False),
                allow_subdomains=_as_bool(args.get("allow_subdomains"), default=True),
            )
            return _normalize_result(result)

        if name in {"extract", "web_extract"}:
            url = str(args.get("url") or "").strip()
            target = str(args.get("target") or "").strip()
            if not url or not target:
                raise ValueError("extract requires args.url and args.target")
            result = await self._agent.extract(url=url, target=target)
            return _normalize_result(result)

        if name in {"auth_hint", "web_auth_hint"}:
            url = str(args.get("url") or "").strip()
            if not url:
                raise ValueError("auth_hint requires args.url")
            return self._agent.get_auth_hint(url)

        if name in {"auth_profiles", "web_auth_profiles"}:
            return self._agent.get_auth_profiles()

        if name in {"challenge_profiles", "web_challenge_profiles"}:
            return self._agent.get_challenge_profiles()

        if name in {"context_snapshot", "web_context_snapshot"}:
            limit = max(1, _as_int(args.get("limit"), 20))
            event_type = str(args.get("event_type") or "").strip() or None
            return self._agent.get_global_context_snapshot(limit=limit, event_type=event_type)

        if name in {"artifact_snapshot", "web_artifact_snapshot"}:
            node_limit = max(1, _as_int(args.get("node_limit"), 80))
            edge_limit = max(1, _as_int(args.get("edge_limit"), 200))
            node_kind = str(args.get("node_kind") or "").strip() or None
            return self._agent.get_artifact_graph_snapshot(
                node_limit=node_limit,
                edge_limit=edge_limit,
                node_kind=node_kind,
            )

        if name in {"runtime_events_snapshot", "web_runtime_events"}:
            limit = max(1, _as_int(args.get("limit"), 50))
            event_type = str(args.get("event_type") or "").strip() or None
            source = str(args.get("source") or "").strip() or None
            since_seq = _as_int(args.get("since_seq"), 0)
            return self._agent.get_runtime_events_snapshot(
                limit=limit,
                event_type=event_type,
                source=source,
                since_seq=(since_seq if since_seq > 0 else None),
            )

        if name in {"runtime_pressure_snapshot", "web_runtime_pressure"}:
            refresh = _as_bool(args.get("refresh"), default=True)
            return self._agent.get_runtime_pressure_snapshot(refresh=refresh)

        if name in {"budget_telemetry_snapshot", "web_budget_telemetry"}:
            refresh = _as_bool(args.get("refresh"), default=True)
            return self._agent.get_budget_telemetry_snapshot(refresh=refresh)

        if name in {"echo"}:
            return {"success": True, "value": args.get("value")}

        if name in {"sleep", "wait"}:
            seconds = max(0.0, _as_float(args.get("seconds"), 0.5))
            await asyncio.sleep(seconds)
            return {"success": True, "slept_seconds": seconds}

        raise ValueError(f"Unknown workflow tool: {tool}")

    def _normalize_academic_sources(self, raw_sources: Any) -> List[AcademicSource]:
        if not isinstance(raw_sources, list):
            return []
        normalized: List[AcademicSource] = []
        for item in raw_sources:
            key = str(item or "").strip().lower()
            enum_value = self._ACADEMIC_SOURCE_MAP.get(key)
            if enum_value and enum_value not in normalized:
                normalized.append(enum_value)
        return normalized

    def _normalize_engines(self, raw_engines: Any) -> Optional[List[AdvancedSearchEngine]]:
        if raw_engines is None:
            return None
        if not isinstance(raw_engines, list):
            return None
        normalized: List[AdvancedSearchEngine] = []
        for item in raw_engines:
            key = str(item or "").strip().lower()
            enum_value = self._ENGINE_ALIAS.get(key)
            if enum_value and enum_value not in normalized:
                normalized.append(enum_value)
        return normalized or None

    def _resolve_value(
        self,
        value: Any,
        runtime: WorkflowRuntime,
        local_scope: Dict[str, Any],
    ) -> Any:
        if isinstance(value, dict):
            return {k: self._resolve_value(v, runtime, local_scope) for k, v in value.items()}
        if isinstance(value, list):
            return [self._resolve_value(item, runtime, local_scope) for item in value]
        if not isinstance(value, str):
            return value

        full_match = _FULL_TOKEN_PATTERN.match(value)
        if full_match:
            expression = full_match.group(1).strip()
            return self._resolve_expression(expression, runtime, local_scope)

        def _replace(match: re.Match[str]) -> str:
            expression = match.group(1).strip()
            resolved = self._resolve_expression(expression, runtime, local_scope)
            if isinstance(resolved, (dict, list)):
                return json.dumps(resolved, ensure_ascii=False)
            return str(resolved)

        return _TOKEN_PATTERN.sub(_replace, value)

    def _resolve_expression(
        self,
        expression: str,
        runtime: WorkflowRuntime,
        local_scope: Dict[str, Any],
    ) -> Any:
        if not expression:
            return ""

        if expression == "vars":
            return runtime.variables
        if expression.startswith("vars."):
            return self._walk_path(runtime.variables, expression[5:])

        if expression == "steps":
            return runtime.steps
        if expression.startswith("steps."):
            rest = expression[6:]
            step_id, _, path = rest.partition(".")
            if not step_id:
                raise KeyError("invalid steps expression")
            if step_id not in runtime.steps:
                raise KeyError(f"step '{step_id}' not found")
            return self._walk_path(runtime.steps[step_id], path)

        if expression == "last":
            return runtime.last
        if expression.startswith("last."):
            return self._walk_path(runtime.last, expression[5:])

        if expression == "local":
            return local_scope
        if expression.startswith("local."):
            return self._walk_path(local_scope, expression[6:])

        if expression.startswith("env."):
            env_key = expression[4:].strip()
            return os.getenv(env_key, "")

        # fallback: local first, then vars
        if expression in local_scope:
            return local_scope[expression]
        if expression in runtime.variables:
            return runtime.variables[expression]

        raise KeyError(f"cannot resolve expression: {expression}")

    def _walk_path(self, root: Any, path: str) -> Any:
        if path == "" or path is None:
            return root
        current = root
        for segment in path.split("."):
            if segment == "":
                continue
            match = _SEGMENT_PATTERN.match(segment)
            if not match:
                raise KeyError(f"invalid path segment: {segment}")
            key_part, index_part = match.groups()
            if key_part is not None and key_part != "":
                current = self._get_by_key(current, key_part)
            if index_part is not None:
                current = self._get_by_index(current, int(index_part))
        return current

    @staticmethod
    def _get_by_key(container: Any, key: str) -> Any:
        if isinstance(container, dict):
            if key not in container:
                raise KeyError(key)
            return container[key]
        if hasattr(container, key):
            return getattr(container, key)
        raise KeyError(key)

    @staticmethod
    def _get_by_index(container: Any, index: int) -> Any:
        if not isinstance(container, list):
            raise KeyError(index)
        if index < 0 or index >= len(container):
            raise IndexError(index)
        return container[index]

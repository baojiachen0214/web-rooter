from __future__ import annotations

import re
from copy import deepcopy
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Sequence
from urllib.parse import urlparse

from core.academic_search import is_academic_query
from core.social import is_bilibili_detail_url, is_bilibili_video_url, is_xiaohongshu_detail_url

_SOCIAL_PLATFORM_KEYWORDS: List[tuple[str, List[str]]] = [
    ("xiaohongshu", ["xiaohongshu", "xhs", "小红书", "xhslink.com"]),
    ("zhihu", ["zhihu", "知乎"]),
    ("weibo", ["weibo", "微博"]),
    ("douyin", ["douyin", "抖音"]),
    ("bilibili", ["bilibili", "b站", "bilibili.com", "b23.tv"]),
    ("tieba", ["tieba", "贴吧", "tieba.baidu.com"]),
    ("reddit", ["reddit"]),
    ("twitter", ["twitter", "x.com"]),
]

_SOCIAL_DOMAINS: Dict[str, str] = {
    "xiaohongshu.com": "xiaohongshu",
    "xhslink.com": "xiaohongshu",
    "zhihu.com": "zhihu",
    "weibo.com": "weibo",
    "douyin.com": "douyin",
    "bilibili.com": "bilibili",
    "b23.tv": "bilibili",
    "tieba.baidu.com": "tieba",
    "reddit.com": "reddit",
    "twitter.com": "twitter",
    "x.com": "twitter",
}

_AUTH_HEAVY_PLATFORMS = {"xiaohongshu", "douyin", "weibo"}
_BROWSER_FRIENDLY_SOCIAL = {"xiaohongshu", "douyin", "weibo", "bilibili"}

_COMMENT_INTENT_TOKENS = ["评论", "comment", "comments", "反馈", "discussion", "reply", "回复", "弹幕"]


@dataclass
class PlannerOptions:
    html_first: bool = True
    top_results: int = 5
    use_browser: bool = False
    crawl_assist: bool = False
    crawl_pages: int = 2


@dataclass
class TaskSpec:
    raw_task: str
    normalized_task: str
    target_url: str = ""
    domain: str = ""
    platform: str = ""
    platforms: List[str] = field(default_factory=list)
    route_family: str = "general"
    target_kind: str = "general_query"
    intent: str = "analyze_web"
    comment_intent: bool = False
    needs_auth: bool = False
    browser_preferred: bool = False
    outputs: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class PlanDecision:
    route: str
    workflow_spec: Dict[str, Any]
    strategy_name: str
    task_spec: TaskSpec
    completion_contract: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "route": self.route,
            "strategy_name": self.strategy_name,
            "task_spec": self.task_spec.to_dict(),
            "completion_contract": deepcopy(self.completion_contract),
            "metadata": deepcopy(self.metadata),
        }


class BaseDoStrategy:
    name = "base"
    supported_routes: Sequence[str] = ("general",)
    priority: int = 0

    def can_handle(self, task_spec: TaskSpec) -> float:
        return 0.0

    def build(self, task_spec: TaskSpec, options: PlannerOptions) -> PlanDecision:
        raise NotImplementedError


class XiaohongshuDetailStrategy(BaseDoStrategy):
    name = "xiaohongshu_detail"
    supported_routes = ("social",)
    priority = 120

    def can_handle(self, task_spec: TaskSpec) -> float:
        if task_spec.route_family != "social":
            return 0.0
        if task_spec.target_kind != "social_detail":
            return 0.0
        if task_spec.platform != "xiaohongshu":
            return 0.0
        return 1.0

    def build(self, task_spec: TaskSpec, options: PlannerOptions) -> PlanDecision:
        spec = _build_social_detail_spec(
            task_spec,
            options,
            name="direct-social-detail-analysis",
            description="Use dedicated Xiaohongshu detail routing before generic social extraction.",
            completion_contract={
                "required_outputs": ["body", "author", "engagement"] + (["comments"] if task_spec.comment_intent else []),
                "quality_gates": {
                    "comment_capture_preferred": bool(task_spec.comment_intent),
                    "browser_required": True,
                },
                "fallback_chain": ["xhs_initial_state", "xhs_xhr_capture", "xhs_dom_comments", "generic_extract"],
            },
        )
        spec.setdefault("variables", {})["platform"] = "xiaohongshu"
        return PlanDecision(
            route="social",
            workflow_spec=spec,
            strategy_name=self.name,
            task_spec=task_spec,
            completion_contract=spec.pop("completion_contract", {}),
            metadata={
                "planner": "registry",
                "reason": "dedicated_social_detail",
                "platform": "xiaohongshu",
                "detail_reader": "core.social.xiaohongshu_reader",
            },
        )




class BilibiliDetailStrategy(BaseDoStrategy):
    name = "bilibili_detail"
    supported_routes = ("social",)
    priority = 110

    def can_handle(self, task_spec: TaskSpec) -> float:
        if task_spec.route_family != "social":
            return 0.0
        if task_spec.target_kind != "social_detail":
            return 0.0
        if task_spec.platform != "bilibili":
            return 0.0
        if not is_bilibili_detail_url(task_spec.target_url or ""):
            return 0.0
        return 0.98 if is_bilibili_video_url(task_spec.target_url or "") else 0.88

    def build(self, task_spec: TaskSpec, options: PlannerOptions) -> PlanDecision:
        spec = _build_social_detail_spec(
            task_spec,
            options,
            name="direct-social-detail-analysis",
            description="Use dedicated Bilibili detail routing before generic social extraction.",
            completion_contract={
                "required_outputs": ["body", "author", "engagement"] + (["comments"] if task_spec.comment_intent else []),
                "quality_gates": {
                    "comment_capture_preferred": bool(task_spec.comment_intent),
                    "browser_required": True,
                },
                "fallback_chain": ["bili_initial_state", "bili_api_comments", "bili_dom_comments", "generic_extract"],
            },
        )
        spec.setdefault("variables", {})["platform"] = "bilibili"
        return PlanDecision(
            route="social",
            workflow_spec=spec,
            strategy_name=self.name,
            task_spec=task_spec,
            completion_contract=spec.pop("completion_contract", {}),
            metadata={
                "planner": "registry",
                "reason": "dedicated_social_detail",
                "platform": "bilibili",
                "detail_reader": "core.social.bilibili_reader",
            },
        )

class SocialDetailStrategy(BaseDoStrategy):
    name = "social_detail"
    supported_routes = ("social",)
    priority = 100

    def can_handle(self, task_spec: TaskSpec) -> float:
        if task_spec.route_family != "social" or task_spec.target_kind != "social_detail":
            return 0.0
        return 0.92

    def build(self, task_spec: TaskSpec, options: PlannerOptions) -> PlanDecision:
        spec = _build_social_detail_spec(
            task_spec,
            options,
            name="direct-social-detail-analysis",
            description="Read a concrete social detail URL first, then extract body and comments.",
            completion_contract={
                "required_outputs": ["body", "author", "engagement"] + (["comments"] if task_spec.comment_intent else []),
                "quality_gates": {"comment_capture_preferred": bool(task_spec.comment_intent)},
                "fallback_chain": ["html_extract", "generic_extract"],
            },
        )
        return PlanDecision(
            route="social",
            workflow_spec=spec,
            strategy_name=self.name,
            task_spec=task_spec,
            completion_contract=spec.pop("completion_contract", {}),
            metadata={
                "planner": "registry",
                "reason": "social_detail_url",
                "platform": task_spec.platform,
            },
        )


class SocialSearchStrategy(BaseDoStrategy):
    name = "social_search"
    supported_routes = ("social",)
    priority = 80

    def can_handle(self, task_spec: TaskSpec) -> float:
        if task_spec.route_family != "social" or task_spec.target_kind != "social_search":
            return 0.0
        return 0.82

    def build(self, task_spec: TaskSpec, options: PlannerOptions) -> PlanDecision:
        top_hits = max(1, min(int(options.top_results), 20))
        assist_pages = max(1, min(int(options.crawl_pages), 10))
        query = task_spec.raw_task if task_spec.comment_intent else f"{task_spec.raw_task} 评论 用户反馈"
        spec: Dict[str, Any] = {
            "name": "default-social-analysis",
            "description": "Search social platforms then inspect top pages in HTML-first mode.",
            "variables": {
                "query": query,
                "platforms": task_spec.platforms,
                "top_hits": top_hits,
                "use_browser": bool(options.use_browser or task_spec.browser_preferred),
            },
            "steps": [
                {
                    "id": "social_search",
                    "tool": "social",
                    "args": {
                        "query": "${vars.query}",
                        "platforms": "${vars.platforms}",
                    },
                },
                {
                    "id": "read_top_pages",
                    "tool": "fetch_html" if options.html_first else "visit",
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
                    "id": "extract_social_signals",
                    "tool": "extract",
                    "for_each": "${steps.read_top_pages.items}",
                    "item_alias": "page",
                    "max_items": "${vars.top_hits}",
                    "continue_on_error": True,
                    "args": {
                        "url": "${local.page.input.url}",
                        "target": _social_extract_target(task_spec.comment_intent),
                    },
                },
            ],
            "completion_contract": {
                "required_outputs": ["body", "author", "engagement"],
                "quality_gates": {
                    "search_hits_required": 1,
                    "comment_capture_preferred": bool(task_spec.comment_intent),
                },
                "fallback_chain": ["social_search", "html_read", "generic_extract"],
            },
        }
        if options.crawl_assist:
            spec["steps"].append(
                {
                    "id": "crawl_assist",
                    "tool": "crawl",
                    "for_each": "${steps.read_top_pages.items}",
                    "item_alias": "page",
                    "max_items": 1,
                    "continue_on_error": True,
                    "args": {
                        "url": "${local.page.input.url}",
                        "max_pages": assist_pages,
                        "max_depth": 2,
                        "allow_external": False,
                        "allow_subdomains": True,
                    },
                }
            )
        return PlanDecision(
            route="social",
            workflow_spec=spec,
            strategy_name=self.name,
            task_spec=task_spec,
            completion_contract=spec.pop("completion_contract", {}),
            metadata={"planner": "registry", "reason": "social_search_query"},
        )


class AcademicStrategy(BaseDoStrategy):
    name = "academic_query"
    supported_routes = ("academic",)
    priority = 70

    def can_handle(self, task_spec: TaskSpec) -> float:
        return 0.85 if task_spec.route_family == "academic" else 0.0

    def build(self, task_spec: TaskSpec, options: PlannerOptions) -> PlanDecision:
        top_hits = max(1, min(int(options.top_results), 20))
        spec: Dict[str, Any] = {
            "name": "default-academic-analysis",
            "description": "Search academic sources then inspect top papers.",
            "variables": {
                "topic": task_spec.raw_task,
                "num_results": top_hits,
                "use_browser": False,
            },
            "steps": [
                {
                    "id": "academic_search",
                    "tool": "academic",
                    "args": {
                        "query": "${vars.topic}",
                        "sources": ["arxiv", "semantic_scholar", "paper_with_code"],
                        "num_results": "${vars.num_results}",
                        "fetch_abstracts": True,
                        "include_code": True,
                    },
                },
                {
                    "id": "read_top_papers_html",
                    "tool": "fetch_html" if options.html_first else "visit",
                    "for_each": "${steps.academic_search.data.papers}",
                    "item_alias": "paper",
                    "max_items": "${vars.num_results}",
                    "continue_on_error": True,
                    "args": {
                        "url": "${local.paper.url}",
                        "use_browser": False,
                        "auto_fallback": True,
                        "max_chars": 60000,
                    },
                },
            ],
            "completion_contract": {
                "required_outputs": ["papers"],
                "quality_gates": {"search_hits_required": 1},
                "fallback_chain": ["academic_search", "paper_html_read"],
            },
        }
        return PlanDecision(
            route="academic",
            workflow_spec=spec,
            strategy_name=self.name,
            task_spec=task_spec,
            completion_contract=spec.pop("completion_contract", {}),
            metadata={"planner": "registry", "reason": "academic_query"},
        )


class CommerceStrategy(BaseDoStrategy):
    name = "commerce_query"
    supported_routes = ("commerce",)
    priority = 60

    def can_handle(self, task_spec: TaskSpec) -> float:
        return 0.8 if task_spec.route_family == "commerce" else 0.0

    def build(self, task_spec: TaskSpec, options: PlannerOptions) -> PlanDecision:
        top_hits = max(1, min(int(options.top_results), 20))
        assist_pages = max(1, min(int(options.crawl_pages), 10))
        lower = task_spec.normalized_task.lower()
        commerce_query = task_spec.raw_task if any(k in lower for k in ("价格", "评价", "review", "price")) else f"{task_spec.raw_task} 价格 评价"
        spec: Dict[str, Any] = {
            "name": "default-commerce-analysis",
            "description": "Search commerce platforms then inspect top pages in HTML-first mode.",
            "variables": {
                "query": commerce_query,
                "platforms": ["taobao", "jd", "pinduoduo", "meituan"],
                "top_hits": top_hits,
                "use_browser": bool(options.use_browser),
            },
            "steps": [
                {
                    "id": "commerce_search",
                    "tool": "commerce",
                    "args": {
                        "query": "${vars.query}",
                        "platforms": "${vars.platforms}",
                    },
                },
                {
                    "id": "read_top_pages",
                    "tool": "fetch_html" if options.html_first else "visit",
                    "for_each": "${steps.commerce_search.results}",
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
            ],
            "completion_contract": {
                "required_outputs": ["offers"],
                "quality_gates": {"search_hits_required": 1},
                "fallback_chain": ["commerce_search", "html_read"],
            },
        }
        if options.crawl_assist:
            spec["steps"].append(
                {
                    "id": "crawl_assist",
                    "tool": "crawl",
                    "for_each": "${steps.read_top_pages.items}",
                    "item_alias": "page",
                    "max_items": 1,
                    "continue_on_error": True,
                    "args": {
                        "url": "${local.page.input.url}",
                        "max_pages": assist_pages,
                        "max_depth": 2,
                        "allow_external": False,
                        "allow_subdomains": True,
                    },
                }
            )
        return PlanDecision(
            route="commerce",
            workflow_spec=spec,
            strategy_name=self.name,
            task_spec=task_spec,
            completion_contract=spec.pop("completion_contract", {}),
            metadata={"planner": "registry", "reason": "commerce_query"},
        )


class UrlStrategy(BaseDoStrategy):
    name = "url_detail"
    supported_routes = ("url",)
    priority = 50

    def can_handle(self, task_spec: TaskSpec) -> float:
        if task_spec.route_family == "url" and task_spec.target_kind == "url":
            return 0.78
        return 0.0

    def build(self, task_spec: TaskSpec, options: PlannerOptions) -> PlanDecision:
        top_hits = max(1, min(int(options.top_results), 20))
        assist_pages = max(1, min(int(options.crawl_pages), 10))
        spec: Dict[str, Any] = {
            "name": "default-url-analysis",
            "description": "Analyze a target URL with auth hint and HTML-first reading.",
            "variables": {
                "target_url": task_spec.target_url,
                "use_browser": bool(options.use_browser or task_spec.browser_preferred),
                "top_hits": top_hits,
            },
            "steps": [
                {
                    "id": "auth_hint",
                    "tool": "auth_hint",
                    "continue_on_error": True,
                    "args": {"url": "${vars.target_url}"},
                },
                {
                    "id": "read_target",
                    "tool": "fetch_html" if options.html_first else "visit",
                    "args": {
                        "url": "${vars.target_url}",
                        "use_browser": "${vars.use_browser}",
                        "auto_fallback": True,
                        "max_chars": 80000,
                    },
                },
            ],
            "completion_contract": {
                "required_outputs": ["body"],
                "quality_gates": {"auth_hint_checked": True},
                "fallback_chain": ["auth_hint", "html_read"],
            },
        }
        if options.crawl_assist:
            spec["steps"].append(
                {
                    "id": "crawl_assist",
                    "tool": "crawl",
                    "continue_on_error": True,
                    "args": {
                        "url": "${vars.target_url}",
                        "max_pages": assist_pages,
                        "max_depth": 2,
                        "allow_external": False,
                        "allow_subdomains": True,
                    },
                }
            )
        return PlanDecision(
            route="url",
            workflow_spec=spec,
            strategy_name=self.name,
            task_spec=task_spec,
            completion_contract=spec.pop("completion_contract", {}),
            metadata={"planner": "registry", "reason": "generic_url"},
        )


class GeneralResearchStrategy(BaseDoStrategy):
    name = "general_query"
    supported_routes = ("general",)
    priority = 10

    def can_handle(self, task_spec: TaskSpec) -> float:
        return 0.5

    def build(self, task_spec: TaskSpec, options: PlannerOptions) -> PlanDecision:
        top_hits = max(1, min(int(options.top_results), 20))
        assist_pages = max(1, min(int(options.crawl_pages), 10))
        spec: Dict[str, Any] = {
            "name": "default-general-analysis",
            "description": "General web analysis with search + HTML-first reading.",
            "variables": {
                "query": task_spec.raw_task,
                "top_hits": top_hits,
                "num_results": max(8, top_hits * 2),
                "use_browser": bool(options.use_browser),
            },
            "steps": [
                {
                    "id": "web_search",
                    "tool": "search_internet",
                    "args": {
                        "query": "${vars.query}",
                        "num_results": "${vars.num_results}",
                        "auto_crawl": False,
                    },
                },
                {
                    "id": "read_top_pages",
                    "tool": "fetch_html" if options.html_first else "visit",
                    "for_each": "${steps.web_search.data.results}",
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
            ],
            "completion_contract": {
                "required_outputs": ["search_results"],
                "quality_gates": {"search_hits_required": 1},
                "fallback_chain": ["web_search", "html_read"],
            },
        }
        if options.crawl_assist:
            spec["steps"].append(
                {
                    "id": "crawl_assist",
                    "tool": "crawl",
                    "for_each": "${steps.read_top_pages.items}",
                    "item_alias": "page",
                    "max_items": 1,
                    "continue_on_error": True,
                    "args": {
                        "url": "${local.page.input.url}",
                        "max_pages": assist_pages,
                        "max_depth": 2,
                        "allow_external": False,
                        "allow_subdomains": True,
                    },
                }
            )
        return PlanDecision(
            route="general",
            workflow_spec=spec,
            strategy_name=self.name,
            task_spec=task_spec,
            completion_contract=spec.pop("completion_contract", {}),
            metadata={"planner": "registry", "reason": "general_search"},
        )


class DoPlannerRegistry:
    def __init__(self) -> None:
        self._strategies: List[BaseDoStrategy] = [
            XiaohongshuDetailStrategy(),
            BilibiliDetailStrategy(),
            SocialDetailStrategy(),
            SocialSearchStrategy(),
            AcademicStrategy(),
            CommerceStrategy(),
            UrlStrategy(),
            GeneralResearchStrategy(),
        ]

    def analyze_task(self, task: str) -> TaskSpec:
        value = str(task or "").strip()
        lower = value.lower()
        target_url = resolve_task_target_url(value)
        domain = extract_domain(target_url)
        platform = detect_platform(value, target_url=target_url)
        platforms = detect_social_platforms(value)
        comment_intent = has_comment_intent(value)
        route_family = classify_task_route(value, target_url=target_url)
        target_kind = infer_target_kind(route_family=route_family, target_url=target_url)
        outputs = ["body", "author", "engagement"]
        if comment_intent:
            outputs.append("comments")
        if route_family == "academic":
            outputs = ["papers", "citations"]
        elif route_family == "commerce":
            outputs = ["offers", "reviews"]
        elif route_family == "general":
            outputs = ["search_results", "evidence"]
        browser_preferred = bool((platform in _BROWSER_FRIENDLY_SOCIAL and target_kind == "social_detail") or is_xiaohongshu_detail_url(target_url) or is_bilibili_detail_url(target_url))
        needs_auth = bool(platform in _AUTH_HEAVY_PLATFORMS and target_kind in {"social_detail", "url"})
        intent = infer_intent(route_family=route_family, target_kind=target_kind, comment_intent=comment_intent)
        return TaskSpec(
            raw_task=value,
            normalized_task=value,
            target_url=target_url,
            domain=domain,
            platform=platform,
            platforms=platforms,
            route_family=route_family,
            target_kind=target_kind,
            intent=intent,
            comment_intent=comment_intent,
            needs_auth=needs_auth,
            browser_preferred=browser_preferred,
            outputs=outputs,
            metadata={
                "has_url": bool(target_url),
                "social_platforms_detected": platforms,
            },
        )

    def plan(
        self,
        task_spec: TaskSpec,
        options: PlannerOptions,
        route_override: Optional[str] = None,
    ) -> PlanDecision:
        effective_task_spec = deepcopy(task_spec)
        if route_override:
            effective_task_spec.route_family = str(route_override).strip().lower()
            if effective_task_spec.route_family == "social" and effective_task_spec.target_url:
                effective_task_spec.target_kind = "social_detail"
            elif effective_task_spec.route_family == "url" and effective_task_spec.target_url:
                effective_task_spec.target_kind = "url"
            elif effective_task_spec.route_family == "social":
                effective_task_spec.target_kind = "social_search"
            elif effective_task_spec.route_family == "academic":
                effective_task_spec.target_kind = "academic_query"
            elif effective_task_spec.route_family == "commerce":
                effective_task_spec.target_kind = "commerce_query"
            else:
                effective_task_spec.target_kind = "general_query"

        candidates: List[tuple[float, int, BaseDoStrategy]] = []
        for strategy in self._strategies:
            if effective_task_spec.route_family not in set(strategy.supported_routes):
                continue
            score = float(strategy.can_handle(effective_task_spec))
            if score <= 0:
                continue
            candidates.append((score, int(strategy.priority), strategy))

        if not candidates:
            fallback = GeneralResearchStrategy()
            return fallback.build(effective_task_spec, options)

        candidates.sort(key=lambda item: (item[0], item[1]), reverse=True)
        _, _, selected = candidates[0]
        return selected.build(effective_task_spec, options)

    def describe_strategies(self) -> List[Dict[str, Any]]:
        payload: List[Dict[str, Any]] = []
        for strategy in self._strategies:
            payload.append(
                {
                    "name": strategy.name,
                    "supported_routes": list(strategy.supported_routes),
                    "priority": strategy.priority,
                }
            )
        return payload


_REGISTRY: Optional[DoPlannerRegistry] = None


def get_do_planner_registry() -> DoPlannerRegistry:
    global _REGISTRY
    if _REGISTRY is None:
        _REGISTRY = DoPlannerRegistry()
    return _REGISTRY


def extract_urls_from_text(text: str) -> List[str]:
    if not text:
        return []
    return re.findall(r"https?://[^\s\"'<>]+", str(text))


def looks_like_url(text: str) -> bool:
    normalized = str(text or "").strip().lower()
    return normalized.startswith(("http://", "https://", "www."))


def resolve_task_target_url(task: str) -> str:
    urls = extract_urls_from_text(task)
    if urls:
        return urls[0]
    value = str(task or "").strip()
    return value if looks_like_url(value) else ""


def extract_domain(url: str) -> str:
    if not url:
        return ""
    try:
        return (urlparse(url).netloc or "").lower()
    except Exception:
        return ""


def has_comment_intent(task: str) -> bool:
    lower = str(task or "").lower()
    return any(token in lower for token in _COMMENT_INTENT_TOKENS)


def detect_social_platforms(task: str) -> List[str]:
    lower = str(task or "").lower()
    selected: List[str] = []
    for platform, tokens in _SOCIAL_PLATFORM_KEYWORDS:
        if any(token in lower for token in tokens):
            selected.append(platform)
    return selected or ["xiaohongshu", "zhihu", "tieba", "douyin", "bilibili", "weibo"]


def detect_platform(task: str, *, target_url: str = "") -> str:
    domain = extract_domain(target_url)
    if domain:
        for host, platform in _SOCIAL_DOMAINS.items():
            if domain == host or domain.endswith(f".{host}"):
                return platform
    lower = str(task or "").lower()
    for platform, tokens in _SOCIAL_PLATFORM_KEYWORDS:
        if any(token in lower for token in tokens):
            return platform
    return ""


def classify_task_route(task: str, *, target_url: str = "") -> str:
    value = str(task or "").strip()
    lower = value.lower()
    resolved_url = target_url or resolve_task_target_url(value)
    if resolved_url:
        platform = detect_platform(value, target_url=resolved_url)
        if platform:
            return "social"
        return "url"

    if is_academic_query(value) or any(
        token in lower
        for token in [
            "paper", "arxiv", "doi", "citation", "benchmark", "ablation",
            "论文", "文献", "引文", "引用", "基准", "实验",
        ]
    ):
        return "academic"

    if any(
        token in lower
        for token in [
            "xiaohongshu", "zhihu", "weibo", "douyin", "bilibili", "tieba", "reddit", "twitter",
            "小红书", "知乎", "微博", "抖音", "b站", "贴吧", "评论区", "弹幕", "话题", "帖子正文",
        ]
    ):
        return "social"

    if any(
        token in lower
        for token in [
            "taobao", "jd", "jingdong", "pinduoduo", "meituan", "dianping",
            "淘宝", "京东", "拼多多", "美团", "点评", "价格", "促销", "购买", "比价",
        ]
    ):
        return "commerce"

    return "general"


def infer_target_kind(route_family: str, target_url: str) -> str:
    if route_family == "social" and target_url:
        return "social_detail"
    if route_family == "url" and target_url:
        return "url"
    if route_family == "social":
        return "social_search"
    if route_family == "academic":
        return "academic_query"
    if route_family == "commerce":
        return "commerce_query"
    return "general_query"


def infer_intent(route_family: str, target_kind: str, comment_intent: bool) -> str:
    if route_family == "social" and target_kind == "social_detail":
        return "read_social_post_with_comments" if comment_intent else "read_social_post"
    if route_family == "social":
        return "search_social_discussion"
    if route_family == "academic":
        return "research_papers"
    if route_family == "commerce":
        return "research_products"
    if route_family == "url":
        return "read_target_url"
    return "general_web_research"


def _social_extract_target(comment_intent: bool) -> str:
    if comment_intent:
        return "提取帖子正文、作者、互动数据、评论区观点、代表性原句、评论作者与点赞数据"
    return "提取帖子正文、作者、互动数据、代表性评论与用户反馈"


def _build_social_detail_spec(
    task_spec: TaskSpec,
    options: PlannerOptions,
    *,
    name: str,
    description: str,
    completion_contract: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    spec: Dict[str, Any] = {
        "name": name,
        "description": description,
        "variables": {
            "target_url": task_spec.target_url,
            "use_browser": bool(options.use_browser or task_spec.browser_preferred),
            "platform": task_spec.platform,
            "platforms": ([task_spec.platform] if task_spec.platform else list(task_spec.platforms)),
        },
        "steps": [
            {
                "id": "auth_hint",
                "tool": "auth_hint",
                "continue_on_error": True,
                "args": {"url": "${vars.target_url}"},
            },
            {
                "id": "read_target",
                "tool": "fetch_html" if options.html_first else "visit",
                "args": {
                    "url": "${vars.target_url}",
                    "use_browser": "${vars.use_browser}",
                    "auto_fallback": True,
                    "max_chars": 80000,
                },
            },
            {
                "id": "extract_social_signals",
                "tool": "extract",
                "args": {
                    "url": "${vars.target_url}",
                    "target": _social_extract_target(task_spec.comment_intent),
                },
            },
        ],
    }
    if completion_contract:
        spec["completion_contract"] = deepcopy(completion_contract)
    return spec


__all__ = [
    "DoPlannerRegistry",
    "PlanDecision",
    "PlannerOptions",
    "TaskSpec",
    "classify_task_route",
    "detect_platform",
    "detect_social_platforms",
    "extract_urls_from_text",
    "get_do_planner_registry",
    "has_comment_intent",
    "looks_like_url",
    "resolve_task_target_url",
]

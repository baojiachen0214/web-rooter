from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional


def _project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _micro_skills_dir() -> Path:
    return _project_root() / "profiles" / "micro_skills"


@dataclass
class MicroSkillHint:
    id: str
    title: str
    message: str
    commands: List[str] = field(default_factory=list)
    keywords: List[str] = field(default_factory=list)
    prefer_tools: List[str] = field(default_factory=list)
    avoid_tools: List[str] = field(default_factory=list)
    prefer_commands: List[str] = field(default_factory=list)
    examples: List[str] = field(default_factory=list)
    priority: int = 50

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> Optional["MicroSkillHint"]:
        if not isinstance(data, dict):
            return None
        hint_id = str(data.get("id") or "").strip()
        title = str(data.get("title") or "").strip()
        message = str(data.get("message") or "").strip()
        if not hint_id or not title or not message:
            return None
        return cls(
            id=hint_id,
            title=title,
            message=message,
            commands=[str(x).strip().lower() for x in data.get("commands", []) if str(x).strip()],
            keywords=[str(x).strip().lower() for x in data.get("keywords", []) if str(x).strip()],
            prefer_tools=[str(x).strip() for x in data.get("prefer_tools", []) if str(x).strip()],
            avoid_tools=[str(x).strip() for x in data.get("avoid_tools", []) if str(x).strip()],
            prefer_commands=[str(x).strip() for x in data.get("prefer_commands", []) if str(x).strip()],
            examples=[str(x).strip() for x in data.get("examples", []) if str(x).strip()],
            priority=int(data.get("priority", 50) or 50),
        )

    def score(self, command: str, text: str) -> float:
        command_token = str(command or "").strip().lower()
        normalized_text = str(text or "").strip().lower()
        score = 0.0
        if self.commands:
            if command_token not in self.commands:
                return -1.0
            score += 1.0
        keyword_hits = 0
        for keyword in self.keywords:
            if keyword and keyword in normalized_text:
                keyword_hits += 1
        if self.keywords and keyword_hits == 0:
            return -1.0
        score += keyword_hits * 1.5
        score += max(0, min(self.priority, 100)) / 100.0
        return score

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "message": self.message,
            "prefer_tools": self.prefer_tools,
            "avoid_tools": self.avoid_tools,
            "prefer_commands": self.prefer_commands,
            "examples": self.examples,
            "priority": self.priority,
        }


class MicroSkillRegistry:
    def __init__(self, micro_dir: Optional[Path] = None):
        self._micro_dir = micro_dir or _micro_skills_dir()
        self._hints: List[MicroSkillHint] = []
        self._loaded = False

    def _builtin_hints(self) -> List[MicroSkillHint]:
        raw = [
            {
                "id": "orchestration-first",
                "title": "Prefer orchestration entrypoints",
                "message": "优先走 `wr skills --resolve` -> `wr do-plan` -> `wr do --dry-run` -> `wr do`；不要一上来就拼 `crawl` / `extract`。",
                "commands": ["do", "do-plan", "quick", "task", "orchestrate", "auto"],
                "prefer_tools": ["do", "skills", "do-plan"],
                "avoid_tools": ["crawl", "extract", "site"],
                "prefer_commands": ["wr skills --resolve \"<goal>\" --compact", "wr do-plan \"<goal>\""],
                "priority": 95,
            },
            {
                "id": "social-detail-direct-read",
                "title": "Social detail pages need direct detail readers",
                "message": "遇到社交详情页/评论区任务，优先 `wr do` 或 `wr social`，并在需要时先给出 `wr auth-hint <url>`；不要把详情页先当普通搜索页处理。",
                "commands": ["do", "do-plan", "quick", "social", "task"],
                "keywords": ["小红书", "xiaohongshu", "bilibili", "b站", "知乎", "weibo", "微博", "评论", "评论区", "帖子", "视频"],
                "prefer_tools": ["do", "social", "auth-hint", "fetch_html"],
                "avoid_tools": ["crawl", "site"],
                "prefer_commands": ["wr auth-hint <url>", "wr do \"<goal>\" --dry-run"],
                "priority": 98,
            },
            {
                "id": "academic-route",
                "title": "Academic tasks should stay on academic rails",
                "message": "论文/benchmark/citation 任务优先 `wr academic` 或 `wr do --skill=academic_relation_mining`；不要误用 social / shopping。",
                "commands": ["do", "do-plan", "quick", "research", "academic"],
                "keywords": ["论文", "paper", "benchmark", "citation", "arxiv", "scholar", "doi"],
                "prefer_tools": ["academic", "do", "mindsearch"],
                "avoid_tools": ["social", "shopping"],
                "prefer_commands": ["wr academic \"<topic>\"", "wr do \"<goal>\" --skill=academic_relation_mining --dry-run"],
                "priority": 90,
            },
            {
                "id": "commerce-route",
                "title": "Commerce review tasks should stay on commerce rails",
                "message": "商品评价/比价任务优先 `wr shopping` 或 `wr do --skill=commerce_review_mining`；不要走 academic / social 模板。",
                "commands": ["do", "do-plan", "quick", "shopping"],
                "keywords": ["淘宝", "京东", "拼多多", "比价", "价格", "评价", "review", "price"],
                "prefer_tools": ["shopping", "do"],
                "avoid_tools": ["academic"],
                "prefer_commands": ["wr shopping \"<query>\" --platform=taobao --platform=jd"],
                "priority": 88,
            },
            {
                "id": "auth-first",
                "title": "Challenge/login sensitive sites need auth hints",
                "message": "如果任务涉及登录态或反爬敏感平台，先跑 `wr auth-hint <url>` 或检查 `wr challenge-profiles`，再执行主体抓取。",
                "commands": ["do", "do-plan", "social", "shopping", "quick", "task"],
                "keywords": ["登录", "cookie", "评论区", "小红书", "bilibili", "知乎", "微博", "douyin", "weibo"],
                "prefer_tools": ["auth-hint", "challenge-profiles", "do"],
                "avoid_tools": [],
                "prefer_commands": ["wr challenge-profiles", "wr auth-hint <url>"],
                "priority": 86,
            },
        ]
        hints = []
        for item in raw:
            hint = MicroSkillHint.from_dict(item)
            if hint is not None:
                hints.append(hint)
        return hints

    def ensure_loaded(self) -> None:
        if self._loaded:
            return
        hints: List[MicroSkillHint] = []
        if self._micro_dir.exists():
            for file in sorted(self._micro_dir.glob("*.json")):
                try:
                    data = json.loads(file.read_text(encoding="utf-8"))
                except Exception:
                    continue
                if isinstance(data, list):
                    for item in data:
                        hint = MicroSkillHint.from_dict(item)
                        if hint is not None:
                            hints.append(hint)
                elif isinstance(data, dict):
                    hint = MicroSkillHint.from_dict(data)
                    if hint is not None:
                        hints.append(hint)
        if not hints:
            hints = self._builtin_hints()
        self._hints = sorted(hints, key=lambda item: item.priority, reverse=True)
        self._loaded = True

    def resolve(self, command: str, text: str = "", limit: int = 3) -> List[Dict[str, Any]]:
        self.ensure_loaded()
        scored: List[tuple[float, MicroSkillHint]] = []
        for hint in self._hints:
            score = hint.score(command, text)
            if score >= 0:
                scored.append((score, hint))
        scored.sort(key=lambda item: item[0], reverse=True)
        return [
            {**hint.to_dict(), "score": round(score, 4)}
            for score, hint in scored[: max(0, int(limit))]
        ]


_registry: Optional[MicroSkillRegistry] = None


def get_micro_skill_registry() -> MicroSkillRegistry:
    global _registry
    if _registry is None:
        _registry = MicroSkillRegistry()
    return _registry


def build_micro_skill_hints(command: str, text: str = "", limit: int = 3) -> List[Dict[str, Any]]:
    return get_micro_skill_registry().resolve(command=command, text=text, limit=limit)

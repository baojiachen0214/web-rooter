"""
Skill profile registry for AI-orchestrated CLI routing.

The purpose is to keep site/task strategy configurable in JSON, so outer AI
can choose a skill contract first, then execute concrete crawl/search steps.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


def _project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _skills_dir() -> Path:
    return _project_root() / "profiles" / "skills"


@dataclass
class SkillProfile:
    name: str
    description: str
    route: str = "auto"
    workflow_template: Optional[str] = None
    aliases: List[str] = field(default_factory=list)
    intent_keywords: List[str] = field(default_factory=list)
    priority: int = 50
    default_variables: Dict[str, Any] = field(default_factory=dict)
    default_options: Dict[str, Any] = field(default_factory=dict)
    examples: List[str] = field(default_factory=list)
    source: str = "builtin"

    @classmethod
    def from_dict(cls, data: Dict[str, Any], source: str) -> Optional["SkillProfile"]:
        if not isinstance(data, dict):
            return None
        name = str(data.get("name") or "").strip()
        description = str(data.get("description") or "").strip()
        if not name or not description:
            return None
        route = str(data.get("route") or "auto").strip().lower() or "auto"
        aliases = [str(item).strip() for item in (data.get("aliases") or []) if str(item).strip()]
        keywords = [str(item).strip().lower() for item in (data.get("intent_keywords") or []) if str(item).strip()]
        examples = [str(item).strip() for item in (data.get("examples") or []) if str(item).strip()]
        default_variables = data.get("default_variables") if isinstance(data.get("default_variables"), dict) else {}
        default_options = data.get("default_options") if isinstance(data.get("default_options"), dict) else {}
        try:
            priority = int(data.get("priority", 50))
        except (TypeError, ValueError):
            priority = 50
        priority = max(0, min(100, priority))
        workflow_template = data.get("workflow_template")
        if workflow_template is not None:
            workflow_template = str(workflow_template).strip() or None
        return cls(
            name=name,
            description=description,
            route=route,
            workflow_template=workflow_template,
            aliases=aliases,
            intent_keywords=keywords,
            priority=priority,
            default_variables=default_variables,
            default_options=default_options,
            examples=examples,
            source=source,
        )

    def matches_name(self, value: str) -> bool:
        target = str(value or "").strip().lower()
        if not target:
            return False
        if self.name.lower() == target:
            return True
        return target in {item.lower() for item in self.aliases}

    def score(self, task: str) -> float:
        text = str(task or "").strip().lower()
        if not text:
            return 0.0
        score = 0.0
        for keyword in self.intent_keywords:
            if keyword and keyword in text:
                score += 1.0 + min(len(keyword), 16) / 32.0
        if score > 0:
            score += float(self.priority) / 1000.0
        return score

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "route": self.route,
            "workflow_template": self.workflow_template,
            "aliases": self.aliases,
            "intent_keywords": self.intent_keywords,
            "priority": self.priority,
            "default_variables": self.default_variables,
            "default_options": self.default_options,
            "examples": self.examples,
            "source": self.source,
        }


class SkillRegistry:
    def __init__(self, profile_dir: Optional[Path] = None):
        self._profile_dir = profile_dir or _skills_dir()
        self._profiles: List[SkillProfile] = []
        self._loaded = False

    @property
    def default_profile_name(self) -> str:
        self.ensure_loaded()
        for profile in self._profiles:
            if profile.name == "default_general_research":
                return profile.name
        if not self._profiles:
            return "default_general_research"
        return self._profiles[0].name

    def ensure_loaded(self) -> None:
        if self._loaded:
            return
        self._profiles = self._load_profiles()
        self._loaded = True

    def reload(self) -> None:
        self._loaded = False
        self._profiles = []
        self.ensure_loaded()

    def list_profiles(self) -> List[SkillProfile]:
        self.ensure_loaded()
        return list(self._profiles)

    def describe_profiles(self) -> List[Dict[str, Any]]:
        return [item.to_dict() for item in self.list_profiles()]

    def get(self, name_or_alias: str) -> Optional[SkillProfile]:
        self.ensure_loaded()
        for profile in self._profiles:
            if profile.matches_name(name_or_alias):
                return profile
        return None

    def resolve(
        self,
        task: str,
        explicit_skill: Optional[str] = None,
    ) -> Tuple[Optional[SkillProfile], Dict[str, Any]]:
        self.ensure_loaded()
        text = str(task or "").strip()
        if explicit_skill:
            selected = self.get(explicit_skill)
            if selected:
                return selected, {
                    "mode": "explicit",
                    "requested": explicit_skill,
                    "selected": selected.name,
                }
            return None, {
                "mode": "explicit",
                "requested": explicit_skill,
                "selected": None,
                "error": f"skill_not_found:{explicit_skill}",
            }

        scored: List[Tuple[SkillProfile, float]] = []
        for profile in self._profiles:
            scored.append((profile, profile.score(text)))
        scored.sort(key=lambda pair: pair[1], reverse=True)

        selected = scored[0][0] if scored else None
        if scored and scored[0][1] <= 0:
            default_profile = self.get(self.default_profile_name)
            if default_profile is not None:
                selected = default_profile
        return selected, {
            "mode": "inferred",
            "selected": selected.name if selected else None,
            "top_scores": [
                {"name": profile.name, "score": round(score, 4)}
                for profile, score in scored[:5]
            ],
        }

    def _load_profiles(self) -> List[SkillProfile]:
        profiles: List[SkillProfile] = []
        if not self._profile_dir.exists():
            return self._builtin_profiles()

        files = sorted(self._profile_dir.glob("*.json"))
        for file in files:
            try:
                data = json.loads(file.read_text(encoding="utf-8"))
            except Exception as exc:
                logger.warning("failed to read skill profile %s: %s", file, exc)
                continue

            if isinstance(data, list):
                for idx, item in enumerate(data):
                    profile = SkillProfile.from_dict(item, source=f"{file.name}#{idx}")
                    if profile:
                        profiles.append(profile)
                continue

            profile = SkillProfile.from_dict(data, source=file.name)
            if profile:
                profiles.append(profile)

        if not profiles:
            return self._builtin_profiles()

        profiles.sort(key=lambda item: item.priority, reverse=True)
        return profiles

    @staticmethod
    def _builtin_profiles() -> List[SkillProfile]:
        fallback: List[SkillProfile] = []
        fallback.append(
            SkillProfile(
                name="default_general_research",
                description="General web research with search + HTML-first reading.",
                route="general",
                priority=30,
                intent_keywords=["研究", "research", "analysis", "总结", "trend"],
                default_options={"html_first": True, "crawl_assist": False},
                source="builtin",
            )
        )
        fallback.append(
            SkillProfile(
                name="social_comment_mining",
                description="Social-platform comment mining and evidence extraction.",
                route="social",
                workflow_template="social_comments",
                priority=80,
                intent_keywords=["评论", "评论区", "小红书", "知乎", "微博", "抖音", "弹幕", "discussion", "feedback"],
                default_options={"html_first": True, "crawl_assist": True},
                source="builtin",
            )
        )
        fallback.append(
            SkillProfile(
                name="academic_relation_mining",
                description="Paper search, citation relation mining, and cross-web discussion linkage.",
                route="academic",
                workflow_template="academic_relations",
                priority=85,
                intent_keywords=["论文", "文献", "arxiv", "citation", "benchmark", "scholar", "paper"],
                default_options={"html_first": True, "crawl_assist": False},
                source="builtin",
            )
        )
        fallback.sort(key=lambda item: item.priority, reverse=True)
        return fallback


_registry: Optional[SkillRegistry] = None


def get_skill_registry() -> SkillRegistry:
    global _registry
    if _registry is None:
        _registry = SkillRegistry()
    return _registry

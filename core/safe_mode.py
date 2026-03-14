"""
Safe mode policy for AI-driven CLI usage.

Goal:
- reduce wrong/unsafe command usage in short-context AI sessions
- force high-level entrypoints (`do` / `do-plan`) in strict mode
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from core.cli_entry import build_cli_command


def _project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _default_state_path() -> Path:
    return _project_root() / ".web-rooter" / "safe_mode.json"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class SafeModeState:
    enabled: bool = False
    policy: str = "strict"
    updated_at: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "enabled": bool(self.enabled),
            "policy": str(self.policy or "strict"),
            "updated_at": str(self.updated_at or _utc_now_iso()),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SafeModeState":
        enabled = bool(data.get("enabled", False))
        policy = str(data.get("policy") or "strict").strip().lower() or "strict"
        updated_at = str(data.get("updated_at") or _utc_now_iso())
        return cls(enabled=enabled, policy=policy, updated_at=updated_at)


class SafeModeManager:
    def __init__(self, state_path: Optional[Path] = None):
        self._state_path = state_path or _default_state_path()
        self._state_path.parent.mkdir(parents=True, exist_ok=True)
        self._state = self._load()

    def _load(self) -> SafeModeState:
        if not self._state_path.exists():
            return SafeModeState(enabled=False, policy="strict", updated_at=_utc_now_iso())
        try:
            data = json.loads(self._state_path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return SafeModeState.from_dict(data)
        except Exception:
            pass
        return SafeModeState(enabled=False, policy="strict", updated_at=_utc_now_iso())

    def _save(self) -> None:
        self._state.updated_at = _utc_now_iso()
        self._state_path.write_text(
            json.dumps(self._state.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def get_state(self) -> SafeModeState:
        # env has priority for non-persistent emergency overrides.
        env_force = str(os.getenv("WEB_ROOTER_SAFE_MODE", "")).strip().lower()
        if env_force in {"1", "true", "yes", "on"}:
            return SafeModeState(
                enabled=True,
                policy=str(os.getenv("WEB_ROOTER_SAFE_MODE_POLICY", self._state.policy or "strict")).strip().lower() or "strict",
                updated_at=self._state.updated_at,
            )
        if env_force in {"0", "false", "no", "off"}:
            return SafeModeState(
                enabled=False,
                policy=str(os.getenv("WEB_ROOTER_SAFE_MODE_POLICY", self._state.policy or "strict")).strip().lower() or "strict",
                updated_at=self._state.updated_at,
            )
        return SafeModeState(
            enabled=self._state.enabled,
            policy=self._state.policy,
            updated_at=self._state.updated_at,
        )

    def set_enabled(self, enabled: bool, policy: Optional[str] = None) -> Dict[str, Any]:
        self._state.enabled = bool(enabled)
        if policy is not None:
            normalized = str(policy or "").strip().lower()
            if normalized:
                self._state.policy = normalized
        self._save()
        return self.describe()

    def set_policy(self, policy: str) -> Dict[str, Any]:
        normalized = str(policy or "").strip().lower() or "strict"
        self._state.policy = normalized
        self._save()
        return self.describe()

    def describe(self) -> Dict[str, Any]:
        state = self.get_state()
        return {
            "enabled": state.enabled,
            "policy": state.policy,
            "updated_at": state.updated_at,
            "path": str(self._state_path),
        }


STRICT_LOW_LEVEL_BLOCKED = {
    "visit",
    "html",
    "dom",
    "search",
    "extract",
    "crawl",
    "links",
    "kb",
    "knowledge",
    "fetch",
    "web",
    "deep",
    "research",
    "mindsearch",
    "social",
    "shopping",
    "shop",
    "commerce",
    "tech",
    "academic",
    "site",
    "export",
}

STRICT_ALWAYS_ALLOWED = {
    "do",
    "do-plan",
    "do_plan",
    "plan",
    "do-submit",
    "do_submit",
    "jobs",
    "jobs-clean",
    "jobs_clean",
    "job-clean",
    "job_clean",
    "job-status",
    "job_status",
    "job-result",
    "job_result",
    "skills",
    "skill-profiles",
    "skill_profiles",
    "ir-lint",
    "ir_lint",
    "lint-ir",
    "lint_ir",
    "workflow-schema",
    "workflow_schema",
    "flow-schema",
    "flow_schema",
    "workflow-template",
    "workflow_template",
    "flow-template",
    "flow_template",
    "workflow",
    "flow",
    "safe-mode",
    "safe_mode",
    "guard",
    "doctor",
    "context",
    "challenge-profiles",
    "challenge_profiles",
    "challenges",
    "auth-profiles",
    "auth_profiles",
    "login-profiles",
    "login_profiles",
    "auth-hint",
    "auth_hint",
    "login-hint",
    "login_hint",
    "auth-template",
    "auth_template",
    "login-template",
    "login_template",
    "help",
    "quit",
    "exit",
    "job-worker",
    "job_worker",
}


def evaluate_safe_mode_command(
    command: str,
    args: List[str],
    state: SafeModeState,
) -> Dict[str, Any]:
    normalized = str(command or "").strip().lower()
    policy = str(state.policy or "strict").strip().lower() or "strict"
    if not state.enabled:
        return {
            "allowed": True,
            "policy": policy,
            "reason": "safe_mode_disabled",
        }

    if normalized in {"safe-mode", "safe_mode", "guard"}:
        return {
            "allowed": True,
            "policy": policy,
            "reason": "self_management",
        }

    if policy != "strict":
        return {
            "allowed": True,
            "policy": policy,
            "reason": "non_strict_policy",
        }

    if normalized in STRICT_LOW_LEVEL_BLOCKED:
        return {
            "allowed": False,
            "policy": policy,
            "reason": f"blocked_low_level_command:{normalized}",
            "hint": "Use `do-plan` first, then `do` for execution.",
            "recommended": [
                build_cli_command('do-plan "<goal>"'),
                build_cli_command('do "<goal>" --dry-run'),
                build_cli_command('do "<goal>"'),
            ],
        }

    if normalized in {"workflow", "flow"} and "--dry-run" not in set(args):
        return {
            "allowed": False,
            "policy": policy,
            "reason": "workflow_execute_blocked_in_safe_mode",
            "hint": "In safe mode strict, run workflow with --dry-run or use `do`.",
            "recommended": [
                build_cli_command("workflow <spec> --dry-run"),
                build_cli_command('do "<goal>"'),
            ],
        }

    if normalized in STRICT_ALWAYS_ALLOWED:
        return {
            "allowed": True,
            "policy": policy,
            "reason": "allowlisted",
        }

    return {
        "allowed": False,
        "policy": policy,
        "reason": f"unknown_command_blocked:{normalized}",
        "hint": "Use `do-plan` / `do` instead of unknown direct commands.",
        "recommended": [
            build_cli_command('do-plan "<goal>"'),
            build_cli_command('do "<goal>" --dry-run'),
        ],
    }


_manager: Optional[SafeModeManager] = None


def get_safe_mode_manager() -> SafeModeManager:
    global _manager
    if _manager is None:
        _manager = SafeModeManager()
    return _manager

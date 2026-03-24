from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


SKILL_MARKER = "Web-Rooter CLI Skills"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _config_dir(repo_root: Optional[Path] = None) -> Path:
    root = (repo_root or _project_root()).resolve()
    return root / ".web-rooter" / "ai-skills"


def _config_path(repo_root: Optional[Path] = None) -> Path:
    return _config_dir(repo_root) / "config.json"


@dataclass(frozen=True)
class InstallTarget:
    tool: str
    path: Path
    content_kind: str
    origin: str = "builtin"


def _write_text(path: Path, content: str) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    old = path.read_text(encoding="utf-8") if path.exists() else None
    if old == content:
        return "unchanged"
    path.write_text(content, encoding="utf-8")
    return "updated" if old is not None else "created"


def _load_config(repo_root: Optional[Path] = None) -> Dict[str, Any]:
    path = _config_path(repo_root)
    if not path.exists():
        return {"custom_targets": []}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"custom_targets": []}
    if not isinstance(data, dict):
        return {"custom_targets": []}
    custom = data.get("custom_targets")
    if not isinstance(custom, list):
        data["custom_targets"] = []
    return data


def _save_config(config: Dict[str, Any], repo_root: Optional[Path] = None) -> Path:
    path = _config_path(repo_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def _skill_markdown(repo_root: Path) -> str:
    repo_text = str(repo_root.resolve())
    return f"""# {SKILL_MARKER}

## Goal
- Treat Web-Rooter as a CLI-first orchestration layer.
- Prefer staged usage: `wr skills --resolve` -> `wr do-plan` -> `wr do --dry-run` -> `wr do`.
- Avoid using low-level commands (`crawl`, `extract`, `site`) as the first step for detail-page tasks.

## Fast Route
1. Resolve skill:
   - `wr skills --resolve "<goal>" --compact`
2. Get staged playbook:
   - `wr do-plan "<goal>"`
3. Compile and lint:
   - `wr do "<goal>" --dry-run`
4. Execute:
   - `wr do "<goal>"`

## Platform Notes
- Social detail pages (小红书 / Bilibili / 知乎 / 微博): prefer `wr do` or `wr social`; surface `wr auth-hint <url>` first when login may matter.
- Academic tasks: prefer `wr academic` or `wr do --skill=academic_relation_mining`.
- Commerce review tasks: prefer `wr shopping` or `wr do --skill=commerce_review_mining`.
- Long jobs: prefer `wr do-submit`, then inspect with `wr jobs` / `wr job-status <id>`.

## High-Signal Commands
- `wr help`
- `wr doctor`
- `wr skills --resolve "<goal>" --compact`
- `wr do-plan "<goal>"`
- `wr do "<goal>" --dry-run`
- `wr do "<goal>"`
- `wr auth-hint <url>`
- `wr add-skills-dir <path> --tool=<tool>`
- `wr skills-install`

## Repo
- Root: `{repo_text}`
- Primary docs: `README.md`, `README.zh-CN.md`, `docs/guide/CLI.md`
"""


def _cursor_rule(skill_md: str) -> str:
    return f"""---
description: Web-Rooter CLI orchestration rules
alwaysApply: true
---
{skill_md}
"""


def _agents_md(skill_md: str) -> str:
    return f"""# Web-Rooter Agent Skill Pack

This file is managed by Web-Rooter skill installers.

{skill_md}
"""


def _content_for_kind(kind: str, repo_root: Path) -> str:
    skill_md = _skill_markdown(repo_root)
    if kind == "skill_md":
        return skill_md
    if kind == "cursor_rule":
        return _cursor_rule(skill_md)
    if kind == "agents_md":
        return _agents_md(skill_md)
    raise ValueError(f"unsupported content kind: {kind}")


def builtin_targets(repo_root: Optional[Path] = None, include_home: bool = True) -> List[InstallTarget]:
    root = (repo_root or _project_root()).resolve()
    home = Path.home()
    targets: List[InstallTarget] = [
        InstallTarget("web-rooter", root / ".web-rooter" / "ai-skills" / "web-rooter" / "SKILL.md", "skill_md"),
        InstallTarget("claude", root / ".claude" / "skills" / "web-rooter" / "SKILL.md", "skill_md"),
        InstallTarget("codex", root / "AGENTS.md", "agents_md"),
        InstallTarget("codex", root / ".agents" / "skills" / "web-rooter" / "SKILL.md", "skill_md"),
        InstallTarget("cursor", root / ".cursor" / "rules" / "web-rooter-cli.mdc", "cursor_rule"),
        InstallTarget("opencode", root / ".opencode" / "AGENTS.md", "agents_md"),
        InstallTarget("openclaw", root / ".openclaw" / "AGENTS.md", "agents_md"),
    ]
    if include_home:
        targets.extend(
            [
                InstallTarget("claude", home / ".claude" / "skills" / "web-rooter" / "SKILL.md", "skill_md", origin="home"),
                InstallTarget("codex", home / ".codex" / "AGENTS.md", "agents_md", origin="home"),
                InstallTarget("codex", home / ".agents" / "skills" / "web-rooter" / "SKILL.md", "skill_md", origin="home"),
                InstallTarget("cursor", home / ".cursor" / "rules" / "web-rooter-cli.mdc", "cursor_rule", origin="home"),
                InstallTarget("opencode", home / ".opencode" / "AGENTS.md", "agents_md", origin="home"),
                InstallTarget("openclaw", home / ".openclaw" / "AGENTS.md", "agents_md", origin="home"),
            ]
        )
    return targets


_SUPPORTED_CUSTOM_TOOLS = {
    "generic": "skill_md",
    "claude": "skill_md",
    "cursor": "cursor_rule",
    "codex": "agents_md",
    "agents": "agents_md",
    "opencode": "agents_md",
    "openclaw": "agents_md",
}


def _resolve_custom_target_path(base_path: Path, tool: str) -> tuple[Path, str]:
    normalized_tool = str(tool or "generic").strip().lower() or "generic"
    content_kind = _SUPPORTED_CUSTOM_TOOLS.get(normalized_tool, "skill_md")
    if base_path.suffix.lower() in {".md", ".mdc"}:
        return base_path, content_kind
    if normalized_tool == "cursor":
        return base_path / "web-rooter-cli.mdc", content_kind
    if normalized_tool in {"codex", "agents", "opencode", "openclaw"}:
        return base_path / "AGENTS.md", content_kind
    return base_path / "web-rooter" / "SKILL.md", content_kind


def custom_targets(repo_root: Optional[Path] = None) -> List[InstallTarget]:
    config = _load_config(repo_root)
    targets: List[InstallTarget] = []
    for item in config.get("custom_targets", []):
        if not isinstance(item, dict):
            continue
        raw_path = str(item.get("path") or "").strip()
        if not raw_path:
            continue
        tool = str(item.get("tool") or "generic").strip().lower() or "generic"
        target_path = Path(raw_path).expanduser()
        content_kind = str(item.get("content_kind") or "").strip()
        if not content_kind or target_path.suffix.lower() not in {".md", ".mdc"}:
            target_path, resolved_kind = _resolve_custom_target_path(target_path, tool)
            if not content_kind:
                content_kind = resolved_kind
        targets.append(InstallTarget(tool=tool, path=target_path, content_kind=content_kind or "skill_md", origin="custom"))
    return targets


def install_skills(repo_root: Optional[Path] = None, include_home: bool = True) -> Dict[str, Any]:
    root = (repo_root or _project_root()).resolve()
    records: List[Dict[str, Any]] = []
    all_targets = builtin_targets(root, include_home=include_home) + custom_targets(root)
    seen: set[tuple[str, str]] = set()
    for target in all_targets:
        key = (target.tool, str(target.path))
        if key in seen:
            continue
        seen.add(key)
        status = _write_text(target.path, _content_for_kind(target.content_kind, root))
        records.append(
            {
                "tool": target.tool,
                "path": str(target.path),
                "status": status,
                "content_kind": target.content_kind,
                "origin": target.origin,
            }
        )
    manifest = {
        "updated_at": _utc_now_iso(),
        "repo_root": str(root),
        "include_home": bool(include_home),
        "files": records,
    }
    manifest_path = _config_dir(root) / "manifest.json"
    _write_text(manifest_path, json.dumps(manifest, ensure_ascii=False, indent=2))
    return {"files": records, "manifest": str(manifest_path)}


def register_skills_dir(repo_root: Optional[Path], path: str, tool: str = "generic", write_now: bool = True) -> Dict[str, Any]:
    root = (repo_root or _project_root()).resolve()
    raw_base = Path(str(path)).expanduser()
    resolved_path, content_kind = _resolve_custom_target_path(raw_base, tool)

    config = _load_config(root)
    custom_targets = [item for item in config.get("custom_targets", []) if isinstance(item, dict)]
    record = {
        "tool": str(tool or "generic").strip().lower() or "generic",
        "path": str(raw_base),
        "content_kind": content_kind,
    }
    exists = any(
        str(item.get("tool") or "").strip().lower() == record["tool"]
        and str(item.get("path") or "").strip() == record["path"]
        for item in custom_targets
    )
    if not exists:
        custom_targets.append(record)
    config["custom_targets"] = custom_targets
    config_path = _save_config(config, root)

    write_status = "registered"
    final_target = InstallTarget(tool=record["tool"], path=resolved_path, content_kind=content_kind, origin="custom")
    if write_now:
        write_status = _write_text(final_target.path, _content_for_kind(final_target.content_kind, root))

    return {
        "success": True,
        "config_path": str(config_path),
        "registered": not exists,
        "tool": final_target.tool,
        "raw_path": str(raw_base),
        "target_path": str(final_target.path),
        "content_kind": final_target.content_kind,
        "write_status": write_status,
    }


def doctor_skills(repo_root: Optional[Path] = None, include_home: bool = True) -> Dict[str, Any]:
    root = (repo_root or _project_root()).resolve()
    checks: List[Dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for target in builtin_targets(root, include_home=include_home) + custom_targets(root):
        key = (target.tool, str(target.path))
        if key in seen:
            continue
        seen.add(key)
        exists = target.path.exists()
        marker_ok = False
        if exists:
            try:
                marker_ok = SKILL_MARKER in target.path.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                marker_ok = False
        checks.append(
            {
                "tool": target.tool,
                "path": str(target.path),
                "exists": exists,
                "marker_ok": marker_ok,
                "origin": target.origin,
                "content_kind": target.content_kind,
                "ok": bool(exists and marker_ok),
                "fix": (
                    "run `wr skills-install` or `python scripts/setup_ai_skills.py`"
                    if not (exists and marker_ok)
                    else ""
                ),
            }
        )
    ok_count = sum(1 for item in checks if item.get("ok"))
    return {
        "success": True,
        "repo_root": str(root),
        "check_count": len(checks),
        "ok_count": ok_count,
        "checks": checks,
        "config_path": str(_config_path(root)),
    }

#!/usr/bin/env python3
"""
Install Web-Rooter CLI operation skills into mainstream AI coding tools.

Targets (best-effort):
- Claude Code / Claude Desktop
- Cursor
- OpenCode
- OpenClaw
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Tuple


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _skill_markdown(repo_root: Path) -> str:
    repo_text = str(repo_root)
    return f"""# Web-Rooter CLI Skills

## Goal
- Treat Web-Rooter as a CLI-first capability layer.
- Prefer stable staged orchestration (`skills -> do-plan -> do --dry-run -> do`) instead of ad-hoc low-level commands.
- Use `wr` commands by default for end users.

## Fast Route
1. Resolve route and skill:
   - `wr skills --resolve "<goal>" --compact`
2. Build staged playbook:
   - `wr do-plan "<goal>"`
3. Compile and lint before execution:
   - `wr do "<goal>" --dry-run`
4. Execute:
   - `wr do "<goal>"`

Fallback when `wr` is unavailable:
- run the same command with `python main.py ...` inside repo root.

## When Site Needs Login / Anti-Bot Handling
- Check auth hints first:
  - `wr auth-template`
  - `wr auth-hint <url>`
  - `wr challenge-profiles`
- Then run `do-plan` and `do`.

## High-Signal Commands
- Search:
  - `wr web "<query>" --engine=quark --num-results=8 --no-crawl`
  - `wr deep "<query>" --variants=3 --crawl=2 --channel=news,platforms`
- Social/commerce:
  - `wr social "<query>" --platform=zhihu --platform=xiaohongshu`
  - `wr shopping "<query>" --platform=taobao --platform=jd`
- Academic:
  - `wr academic "<topic>" --papers-only --source=arxiv --source=semantic_scholar`

## Guardrails
- Prefer `do` / `do-plan` in short-context AI sessions.
- If command typo occurs, use suggestions and recover with skill-guided `do-plan`.
- For long jobs, submit async:
  - `wr do-submit "<goal>" --timeout-sec=1200`
  - `wr jobs`
  - `wr job-result <job_id>`

## Project Path
- Repo root: `{repo_text}`
- Primary docs: `docs/guide/CLI.md`, `docs/guide/INSTALLATION.md`
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

This file is managed by `scripts/setup_ai_skills.py`.

{skill_md}
"""


def _write_text(path: Path, content: str) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    old = path.read_text(encoding="utf-8") if path.exists() else None
    if old == content:
        return "unchanged"
    path.write_text(content, encoding="utf-8")
    return "updated" if old is not None else "created"


def install_skills(repo_root: Path, include_home: bool) -> Dict[str, List[Dict[str, str]]]:
    repo_root = repo_root.resolve()
    home = Path.home()
    skill_md = _skill_markdown(repo_root)
    cursor_rule = _cursor_rule(skill_md)
    agents_doc = _agents_md(skill_md)

    records: Dict[str, List[Dict[str, str]]] = {"files": []}

    def record(path: Path, status: str, tool: str) -> None:
        records["files"].append(
            {
                "tool": tool,
                "path": str(path),
                "status": status,
            }
        )

    # Canonical skill source in project.
    canonical = repo_root / ".web-rooter" / "ai-skills" / "web-rooter-cli-skills.md"
    record(canonical, _write_text(canonical, skill_md), "web-rooter")

    # Project-local files are written only when a tool folder already exists.
    project_targets: List[Tuple[str, Path, str]] = [
        ("claude", repo_root / ".claude" / "skills" / "web-rooter-cli.md", skill_md),
        ("cursor", repo_root / ".cursor" / "rules" / "web-rooter-cli.mdc", cursor_rule),
        ("opencode", repo_root / ".opencode" / "AGENTS.md", agents_doc),
        ("openclaw", repo_root / ".openclaw" / "AGENTS.md", agents_doc),
    ]
    for tool, path, content in project_targets:
        if path.parent.exists():
            record(path, _write_text(path, content), tool)
        else:
            record(path, "skipped_missing_parent", tool)

    if include_home:
        # Global best-effort files.
        claude_home_skill = home / ".claude" / "skills" / "web-rooter-cli.md"
        record(claude_home_skill, _write_text(claude_home_skill, skill_md), "claude")

        cursor_home = home / ".cursor" / "rules" / "web-rooter-cli.mdc"
        record(cursor_home, _write_text(cursor_home, cursor_rule), "cursor")

        opencode_home = home / ".opencode" / "AGENTS.md"
        record(opencode_home, _write_text(opencode_home, agents_doc), "opencode")

        openclaw_home = home / ".openclaw" / "AGENTS.md"
        record(openclaw_home, _write_text(openclaw_home, agents_doc), "openclaw")

    manifest = repo_root / ".web-rooter" / "ai-skills" / "manifest.json"
    manifest_payload = {
        "updated_at": _utc_now_iso(),
        "repo_root": str(repo_root),
        "include_home": include_home,
        "files": records["files"],
    }
    record(manifest, _write_text(manifest, json.dumps(manifest_payload, ensure_ascii=False, indent=2)), "web-rooter")
    return records


def main() -> int:
    parser = argparse.ArgumentParser(description="Install Web-Rooter CLI skills to AI coding tools.")
    parser.add_argument(
        "--repo-root",
        default=str(Path(__file__).resolve().parents[1]),
        help="Path to repository root (default: auto-detected).",
    )
    parser.add_argument(
        "--no-home",
        action="store_true",
        help="Do not write global home-directory tool skill files.",
    )
    args = parser.parse_args()

    repo_root = Path(str(args.repo_root)).expanduser().resolve()
    if not (repo_root / "main.py").exists():
        raise SystemExit(f"invalid repo root: {repo_root} (main.py not found)")

    result = install_skills(repo_root=repo_root, include_home=not bool(args.no_home))
    print(json.dumps({"success": True, **result}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

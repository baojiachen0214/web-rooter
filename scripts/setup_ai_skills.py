#!/usr/bin/env python3
"""
Install Web-Rooter CLI skills into mainstream AI coding tools.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


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
    parser.add_argument(
        "--skip-doctor-check",
        action="store_true",
        help="Skip the pre-installation doctor check (not recommended).",
    )
    args = parser.parse_args()

    repo_root = Path(str(args.repo_root)).expanduser().resolve()
    if not (repo_root / "main.py").exists():
        raise SystemExit(f"invalid repo root: {repo_root} (main.py not found)")

    # Pre-installation check
    if not args.skip_doctor_check:
        print("=" * 60, file=sys.stderr)
        print("【重要提醒】安装 Skills 前，请先确保 Web-Rooter 环境就绪", file=sys.stderr)
        print("=" * 60, file=sys.stderr)
        print("", file=sys.stderr)
        print("在安装 skills 之前，强烈建议先执行以下检查：", file=sys.stderr)
        print("", file=sys.stderr)
        print("  1. wr doctor          - 检查环境是否就绪", file=sys.stderr)
        print("  2. wr help            - 确认命令可用", file=sys.stderr)
        print("", file=sys.stderr)
        print("如果 wr doctor 未通过，请先修复环境问题再安装 skills。", file=sys.stderr)
        print("如果跳过此检查，可以使用 --skip-doctor-check 参数", file=sys.stderr)
        print("=" * 60, file=sys.stderr)
        print("", file=sys.stderr)

    # Import here after path validation
    from core.ai_tool_skills import install_skills

    result = install_skills(repo_root=repo_root, include_home=not bool(args.no_home))
    
    # Post-installation reminder
    print("", file=sys.stderr)
    print("=" * 60, file=sys.stderr)
    print("【Skills 安装完成】", file=sys.stderr)
    print("=" * 60, file=sys.stderr)
    print("", file=sys.stderr)
    print("重要提醒：", file=sys.stderr)
    print("  • 使用 WR 前，务必先执行: wr doctor", file=sys.stderr)
    print("  • 遇到错误时，先执行: wr help <命令>", file=sys.stderr)
    print("  • 平台任务前，务必: wr auth-hint <URL>", file=sys.stderr)
    print("  • 如需登录，执行: wr cookie <平台>", file=sys.stderr)
    print("", file=sys.stderr)
    print("详细使用指南：", file=sys.stderr)
    print(f"  - {repo_root}/.agents/skills/web-rooter/SKILL.md", file=sys.stderr)
    print(f"  - {repo_root}/.agents/skills/web-rooter/TROUBLESHOOTING.md", file=sys.stderr)
    print("=" * 60, file=sys.stderr)
    
    print(json.dumps({"success": True, **result}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

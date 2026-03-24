#!/usr/bin/env python3
"""
Install Web-Rooter CLI skills into mainstream AI coding tools.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from core.ai_tool_skills import install_skills


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

"""
Render project LOGO.png into terminal-friendly text.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core.terminal_logo import print_logo


def main() -> int:
    parser = argparse.ArgumentParser(description="Render LOGO.png as terminal unicode art.")
    parser.add_argument("--logo", default=str(Path.cwd() / "LOGO.png"), help="Path to logo PNG.")
    parser.add_argument("--width", type=int, default=46, help="Output width in terminal columns.")
    parser.add_argument("--max-height", type=int, default=18, help="Max output height (rows).")
    parser.add_argument("--no-color", action="store_true", help="Disable ANSI color output.")
    parser.add_argument("--style", choices=["braille", "blocks"], default="blocks", help="Render style.")
    args = parser.parse_args()

    print_logo(
        image_path=args.logo,
        width=max(8, int(args.width)),
        max_height=max(4, int(args.max_height)),
        color=not bool(args.no_color),
        style=str(args.style),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

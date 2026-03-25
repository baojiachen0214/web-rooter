"""
Entry point for `python -m core.social.xiaohongshu_cli`

Usage:
    python -m core.social.xiaohongshu_cli search "杭州"
    python -m core.social.xiaohongshu_cli login
    python -m core.social.xiaohongshu_cli read <note_id>
"""

from __future__ import annotations

import sys

from .cli import handle_xhs_command


def main() -> None:
    """Main entry point."""
    sys.exit(handle_xhs_command(sys.argv[1:]))


if __name__ == "__main__":
    main()

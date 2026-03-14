"""
Helpers for rendering user-facing CLI commands.

Installed users should see `wr ...` by default. Source-checkout workflows can
override this with WEB_ROOTER_CLI_ENTRYPOINT, e.g. `python main.py`.
"""
from __future__ import annotations

import os


def get_cli_entrypoint(default: str = "wr") -> str:
    value = str(os.getenv("WEB_ROOTER_CLI_ENTRYPOINT", default)).strip()
    return value or default


def build_cli_command(command: str, default: str = "wr") -> str:
    entrypoint = get_cli_entrypoint(default=default)
    normalized = str(command or "").strip()
    if not normalized:
        return entrypoint
    return f"{entrypoint} {normalized}"

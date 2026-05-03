"""
Console/stdout encoding helpers.

These helpers harden CLI entry points against Windows consoles that default to
GBK/CP936 or other non-UTF-8 encodings. The goal is to prevent Unicode output
from crashing the process while still preferring UTF-8 when available.
"""
from __future__ import annotations

import os
import sys
from typing import Any


def _reconfigure_stream(stream: Any, *, encoding: str = "utf-8", errors: str = "replace") -> None:
    reconfigure = getattr(stream, "reconfigure", None)
    if not callable(reconfigure):
        return
    try:
        reconfigure(encoding=encoding, errors=errors)
    except Exception:
        # Best effort only. If the host stream refuses reconfiguration we
        # keep the original stream rather than failing startup.
        pass


def configure_stdio(*, encoding: str = "utf-8", errors: str = "replace") -> None:
    """
    Reconfigure stdio for Unicode-safe output.

    The encoding override is intentionally best-effort. Even if the platform
    console is still using a legacy code page, ``errors='replace'`` prevents
    hard crashes caused by unsupported symbols.
    """
    _reconfigure_stream(sys.stdout, encoding=encoding, errors=errors)
    _reconfigure_stream(sys.stderr, encoding=encoding, errors=errors)

    # Make the preference explicit for child processes spawned after startup.
    os.environ.setdefault("PYTHONUTF8", "1")
    os.environ.setdefault("PYTHONIOENCODING", f"{encoding}:{errors}")


def stream_supports_utf8(stream: Any = None) -> bool:
    probe = stream if stream is not None else sys.stdout
    encoding = str(getattr(probe, "encoding", "") or "").strip().lower()
    return encoding.startswith("utf-8") or encoding == "utf8"


#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

if command -v python3 >/dev/null 2>&1; then
  PYTHON_BIN="$(command -v python3)"
elif command -v python >/dev/null 2>&1; then
  PYTHON_BIN="$(command -v python)"
else
  echo "[error] python/python3 not found in PATH"
  exit 1
fi

"${PYTHON_BIN}" - <<PY
import json
from pathlib import Path

repo_root = Path(r"${REPO_ROOT}")
targets = [
    Path.home() / ".config" / "Claude" / "config.json",                  # Linux Claude Desktop
    Path.home() / "Library" / "Application Support" / "Claude" / "config.json",  # macOS Claude Desktop
]

for path in targets:
    if not path.exists():
        continue
    try:
        cfg = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        continue
    servers = cfg.get("mcpServers") or {}
    if "web-rooter" in servers:
        del servers["web-rooter"]
        cfg["mcpServers"] = servers
        path.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[ok] updated {path}")

mcp_json = repo_root / ".mcp.json"
if mcp_json.exists():
    try:
        cfg = json.loads(mcp_json.read_text(encoding="utf-8"))
    except Exception:
        cfg = {}
    servers = cfg.get("mcpServers") or {}
    if "web-rooter" in servers:
        del servers["web-rooter"]
        cfg["mcpServers"] = servers
        mcp_json.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[ok] updated {mcp_json}")
PY

echo "Web-Rooter MCP uninstall complete."

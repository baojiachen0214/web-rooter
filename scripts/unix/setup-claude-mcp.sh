#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
MAIN_PY="${REPO_ROOT}/main.py"

if [[ ! -f "${MAIN_PY}" ]]; then
  echo "[error] main.py not found: ${MAIN_PY}"
  exit 1
fi

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

python_path = r"${PYTHON_BIN}"
main_py = r"${MAIN_PY}"
repo_root = r"${REPO_ROOT}"

targets = [
    Path.home() / ".config" / "Claude" / "config.json",                  # Linux Claude Desktop
    Path.home() / "Library" / "Application Support" / "Claude" / "config.json",  # macOS Claude Desktop
]

payload = {
    "command": python_path,
    "args": [main_py, "--mcp"],
    "cwd": repo_root,
    "env": {
        "PYTHONUNBUFFERED": "1",
        "PYTHONIOENCODING": "utf-8",
    },
}

for path in targets:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        try:
            cfg = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            cfg = {}
    else:
        cfg = {}
    cfg.setdefault("mcpServers", {})["web-rooter"] = payload
    cfg.setdefault("toolPreferences", {})["preferMcpTools"] = True
    path.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[ok] updated {path}")

mcp_json = Path(repo_root) / ".mcp.json"
mcp_json.write_text(
    json.dumps(
        {
            "$schema": "https://json.schemastore.org/mcp-settings",
            "mcpServers": {
                "web-rooter": {
                    "command": python_path,
                    "args": [main_py, "--mcp"],
                    "env": {
                        "PYTHONUNBUFFERED": "1",
                        "PYTHONIOENCODING": "utf-8",
                    },
                }
            },
        },
        ensure_ascii=False,
        indent=2,
    ),
    encoding="utf-8",
)
print(f"[ok] wrote {mcp_json}")
PY

echo "========================================"
echo "Web-Rooter MCP setup complete"
echo "========================================"
echo "project: ${REPO_ROOT}"
echo "python : ${PYTHON_BIN}"
echo
echo "next:"
echo "1. restart Claude Desktop / Claude Code"
echo "2. run /tools to verify web-rooter"

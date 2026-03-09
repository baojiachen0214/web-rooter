#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
MAIN_PY="${REPO_ROOT}/main.py"

USER_BIN_DIR="${HOME}/.local/bin"
WR_SCRIPT="${USER_BIN_DIR}/wr"

if [[ -f "${WR_SCRIPT}" ]]; then
  rm -f "${WR_SCRIPT}"
  echo "[ok] removed ${WR_SCRIPT}"
else
  echo "[info] ${WR_SCRIPT} not found"
fi

remove_line() {
  local file="$1"
  local line="$2"
  if [[ ! -f "${file}" ]]; then
    return
  fi
  awk -v l="${line}" '$0 != l' "${file}" >"${file}.tmp" && mv "${file}.tmp" "${file}"
}

PATH_LINE='export PATH="$HOME/.local/bin:$PATH"'
remove_line "${HOME}/.bashrc" "${PATH_LINE}"
remove_line "${HOME}/.zshrc" "${PATH_LINE}"

PYTHON_BIN="${PYTHON_BIN:-}"
if [[ -z "${PYTHON_BIN}" ]]; then
  if command -v python3 >/dev/null 2>&1; then
    PYTHON_BIN="$(command -v python3)"
  elif command -v python >/dev/null 2>&1; then
    PYTHON_BIN="$(command -v python)"
  else
    echo "[warn] python/python3 not found; skipped Claude permission cleanup"
    echo "Web-Rooter CLI uninstall complete."
    exit 0
  fi
fi

"${PYTHON_BIN}" - <<PY
import json
from pathlib import Path

main_py = r"${MAIN_PY}"
items = [
    "Bash(wr:*)",
    "Bash(web*:*)",
    f"Bash(python:{main_py}:*)",
]

targets = [
    ("desktop", Path.home() / ".config" / "Claude" / "settings.json"),
    ("desktop", Path.home() / "Library" / "Application Support" / "Claude" / "settings.json"),
    ("code", Path.home() / ".claude" / "settings.json"),
]

for mode, path in targets:
    if not path.exists():
        continue
    try:
        cfg = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        continue
    if mode == "desktop":
        allow = ((cfg.get("permissions") or {}).get("allow") or [])
        cfg.setdefault("permissions", {})["allow"] = [a for a in allow if a not in items]
    else:
        allow = cfg.get("allow") or []
        cfg["allow"] = [a for a in allow if a not in items]
    path.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[ok] updated {path}")
PY

echo "Web-Rooter CLI uninstall complete."

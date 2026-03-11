#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
MAIN_PY="${REPO_ROOT}/main.py"

if [[ ! -f "${MAIN_PY}" ]]; then
  echo "[error] main.py not found: ${MAIN_PY}"
  exit 1
fi

PYTHON_BIN="${PYTHON_BIN:-}"
if [[ -z "${PYTHON_BIN}" ]]; then
  if command -v python3 >/dev/null 2>&1; then
    PYTHON_BIN="$(command -v python3)"
  elif command -v python >/dev/null 2>&1; then
    PYTHON_BIN="$(command -v python)"
  else
    echo "[error] python/python3 not found in PATH"
    exit 1
  fi
fi

USER_BIN_DIR="${HOME}/.local/bin"
WR_SCRIPT="${USER_BIN_DIR}/wr"
mkdir -p "${USER_BIN_DIR}"

cat >"${WR_SCRIPT}" <<EOF
#!/usr/bin/env bash
exec "${PYTHON_BIN}" "${MAIN_PY}" "\$@"
EOF
chmod +x "${WR_SCRIPT}"

append_once() {
  local file="$1"
  local line="$2"
  if [[ ! -f "${file}" ]]; then
    touch "${file}"
  fi
  if ! grep -Fq "${line}" "${file}"; then
    printf "\n%s\n" "${line}" >>"${file}"
  fi
}

PATH_LINE='export PATH="$HOME/.local/bin:$PATH"'
append_once "${HOME}/.bashrc" "${PATH_LINE}"
append_once "${HOME}/.zshrc" "${PATH_LINE}"

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
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        try:
            cfg = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            cfg = {}
    else:
        cfg = {}

    if mode == "desktop":
        perms = cfg.setdefault("permissions", {})
        allow = perms.setdefault("allow", [])
        for item in items:
            if item not in allow:
                allow.append(item)
    else:
        allow = cfg.setdefault("allow", [])
        for item in items:
            if item not in allow:
                allow.append(item)

    path.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[ok] updated {path}")
PY

if "${PYTHON_BIN}" "${REPO_ROOT}/scripts/setup_ai_skills.py" --repo-root "${REPO_ROOT}"; then
  echo "[ok] AI tool skills installed"
else
  echo "[warn] failed to install AI tool skills; retry manually:"
  echo "       ${PYTHON_BIN} ${REPO_ROOT}/scripts/setup_ai_skills.py --repo-root ${REPO_ROOT}"
fi

echo "========================================"
echo "Web-Rooter CLI install complete"
echo "========================================"
echo "project: ${REPO_ROOT}"
echo "python : ${PYTHON_BIN}"
echo "binary : ${WR_SCRIPT}"
echo
echo "next:"
echo "1. restart terminal"
echo "2. run: wr doctor"
echo "3. in Claude Code run: /tools"

#!/usr/bin/env bash
set -euo pipefail

WITH_MCP=0

for arg in "$@"; do
  case "$arg" in
    --with-mcp)
      WITH_MCP=1
      ;;
  esac
done

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="${SCRIPT_DIR}"
MAIN_PY="${REPO_ROOT}/main.py"
VENV_DIR="${REPO_ROOT}/.venv312"

echo "========================================"
echo "Web-Rooter One-Click Install (CLI First)"
echo "========================================"
echo

if [[ ! -f "${MAIN_PY}" ]]; then
  echo "[error] main.py not found: ${MAIN_PY}"
  exit 1
fi

PY_BOOTSTRAP="${PY_BOOTSTRAP:-}"
if [[ -z "${PY_BOOTSTRAP}" ]]; then
  if command -v python3 >/dev/null 2>&1; then
    PY_BOOTSTRAP="$(command -v python3)"
  elif command -v python >/dev/null 2>&1; then
    PY_BOOTSTRAP="$(command -v python)"
  else
    echo "[error] python/python3 not found in PATH (requires Python 3.10+)"
    exit 1
  fi
fi

echo "[info] bootstrap python: ${PY_BOOTSTRAP}"
"${PY_BOOTSTRAP}" - <<'PY'
import sys
if sys.version_info < (3, 10):
    raise SystemExit("Python 3.10+ is required.")
PY

if [[ ! -x "${VENV_DIR}/bin/python" ]]; then
  echo "[1/7] creating virtualenv: ${VENV_DIR}"
  "${PY_BOOTSTRAP}" -m venv "${VENV_DIR}"
else
  echo "[1/7] reusing virtualenv: ${VENV_DIR}"
fi

PYTHON_BIN="${VENV_DIR}/bin/python"
echo "[info] runtime python: ${PYTHON_BIN}"

echo "[2/7] upgrading pip..."
"${PYTHON_BIN}" -m pip install --upgrade pip

echo "[3/7] installing requirements..."
"${PYTHON_BIN}" -m pip install -r "${REPO_ROOT}/requirements.txt"
"${PYTHON_BIN}" "${REPO_ROOT}/scripts/render_terminal_logo.py" --logo "${REPO_ROOT}/LOGO.png" --style blocks --width 64 --max-height 22 || true

echo "[4/7] installing Playwright Chromium..."
if ! "${PYTHON_BIN}" -m playwright install chromium; then
  echo "[warn] Playwright install failed; you can retry later:"
  echo "       ${PYTHON_BIN} -m playwright install chromium"
fi

echo "[5/7] running doctor..."
if ! "${PYTHON_BIN}" "${MAIN_PY}" --doctor; then
  echo "[warn] doctor reported issues; review logs above"
fi

echo "[6/7] installing global wr command..."
bash "${REPO_ROOT}/scripts/unix/install-system-cli.sh"

echo "[7/7] installing AI tool skills (Claude/Cursor/OpenCode/OpenClaw)..."
"${PYTHON_BIN}" "${REPO_ROOT}/scripts/setup_ai_skills.py" --repo-root "${REPO_ROOT}" || {
  echo "[warn] AI skill install failed; retry manually:"
  echo "       ${PYTHON_BIN} ${REPO_ROOT}/scripts/setup_ai_skills.py --repo-root ${REPO_ROOT}"
}

if [[ "${WITH_MCP}" == "1" ]]; then
  echo "[extra] setting up Claude MCP..."
  bash "${REPO_ROOT}/scripts/unix/setup-claude-mcp.sh"
fi

echo
echo "========================================"
echo "Install complete"
echo "========================================"
echo
echo "Try:"
echo "  wr doctor"
echo "  wr do \"Analyze RAG benchmark paper relations with citations\" --dry-run"
echo "  wr skills --resolve \"Mine Zhihu comments with citations\" --compact"
echo
echo "Optional MCP setup:"
echo "  bash scripts/unix/setup-claude-mcp.sh"

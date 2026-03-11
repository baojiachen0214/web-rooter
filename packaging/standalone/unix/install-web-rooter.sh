#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
EXE_SRC="${SCRIPT_DIR}/web-rooter"
TARGET_ROOT="${HOME}/.local/share/web-rooter/standalone"
TARGET_EXE="${TARGET_ROOT}/web-rooter"
BIN_DIR="${HOME}/.local/bin"
WR_LINK="${BIN_DIR}/wr"

echo "========================================"
echo "Web-Rooter Standalone Install (Unix)"
echo "========================================"
echo

if [[ ! -f "${EXE_SRC}" ]]; then
  echo "[error] web-rooter binary not found next to installer."
  exit 1
fi

mkdir -p "${TARGET_ROOT}" "${BIN_DIR}"
cp -f "${EXE_SRC}" "${TARGET_EXE}"
chmod +x "${TARGET_EXE}"

cat >"${WR_LINK}" <<EOF
#!/usr/bin/env bash
exec "${TARGET_EXE}" "\$@"
EOF
chmod +x "${WR_LINK}"

append_once() {
  local file="$1"
  local line="$2"
  touch "${file}"
  if ! grep -Fq "${line}" "${file}"; then
    printf "\n%s\n" "${line}" >>"${file}"
  fi
}

PATH_LINE='export PATH="$HOME/.local/bin:$PATH"'
append_once "${HOME}/.bashrc" "${PATH_LINE}"
append_once "${HOME}/.zshrc" "${PATH_LINE}"

SKILL_TEXT='# Web-Rooter CLI Skills
Use `wr skills --resolve "<goal>" --compact`, then `wr do-plan`, then `wr do --dry-run`, then `wr do`.'

mkdir -p "${HOME}/.claude/skills" "${HOME}/.cursor/rules" "${HOME}/.opencode" "${HOME}/.openclaw"
printf "%s\n" "${SKILL_TEXT}" > "${HOME}/.claude/skills/web-rooter-cli.md"
printf "%s\n" "${SKILL_TEXT}" > "${HOME}/.cursor/rules/web-rooter-cli.mdc"
printf "%s\n" "${SKILL_TEXT}" > "${HOME}/.opencode/AGENTS.md"
printf "%s\n" "${SKILL_TEXT}" > "${HOME}/.openclaw/AGENTS.md"

echo "[ok] installed executable: ${TARGET_EXE}"
echo "[ok] installed command wrapper: ${WR_LINK}"
echo "[ok] installed AI tool skill files"
echo
echo "Restart terminal, then run:"
echo "  wr --version"
echo "  wr doctor"


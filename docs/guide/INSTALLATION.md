# Installation Guide

## 1. Prerequisites

- Python `3.10+`
- Network access (for Playwright browser runtime download)
- Recommended: Git

## 2. One-Click Install (CLI First)

Windows:

```bat
install.bat
```

macOS / Linux:

```bash
bash install.sh
```

What the one-click installer does:

- create/reuse `.venv312`
- install `requirements.txt`
- install Playwright Chromium runtime
- run environment doctor check (`wr doctor` equivalent)
- install user-level global CLI command `wr`
- inject Web-Rooter CLI skill packs into Claude/Cursor/OpenCode/OpenClaw (best-effort)

Default global skill paths:

- Claude: `~/.claude/skills/web-rooter-cli.md`
- Cursor: `~/.cursor/rules/web-rooter-cli.mdc`
- OpenCode: `~/.opencode/AGENTS.md`
- OpenClaw: `~/.openclaw/AGENTS.md`

Optional MCP setup:

- Windows: `install.bat --with-mcp`
- macOS/Linux: `bash install.sh --with-mcp`

## 2.5 Build Standalone Release Bundle (Maintainers)

If you need a “no Python/pip preinstall” delivery package for end users:

```bash
# macOS / Linux
bash scripts/release/package-release.sh

# Windows
scripts\release\package-release.bat
```

Useful options:

```bash
# Re-package existing dist binary without rebuilding
bash scripts/release/package-release.sh --skip-build

# Emit both zip and tar.gz
bash scripts/release/package-release.sh --format both
```

Artifacts are generated under `dist/release/`.

## 3. Manual Install (All Platforms)

```bash
pip install -r requirements.txt
python -m playwright install chromium
python main.py doctor
```

`--doctor` should pass before running deep crawling tasks.

Windows note:

- If your system `python` is below `3.10`, use the project venv directly:
  - `.venv312\Scripts\python.exe main.py doctor`
  - `.venv312\Scripts\python.exe main.py quick "OpenAI Agents SDK"`

## 4. OS-Specific Helpers

### Windows

- One-click installer: `install.bat`
- Install global CLI (`wr`): `scripts\windows\install-system-cli.bat`
- Uninstall global CLI: `scripts\windows\uninstall-system-cli.bat`
- Install AI tool skills only: `python scripts\setup_ai_skills.py --repo-root .`
- Setup Claude MCP: `scripts\windows\setup-claude-mcp.bat`
- Uninstall Claude MCP: `scripts\windows\uninstall-claude-mcp.bat`

### macOS / Linux

```bash
chmod +x scripts/unix/*.sh
./scripts/unix/install-system-cli.sh
python3 scripts/setup_ai_skills.py --repo-root .
./scripts/unix/setup-claude-mcp.sh
```

Uninstall:

```bash
./scripts/unix/uninstall-system-cli.sh
./scripts/unix/uninstall-claude-mcp.sh
```

## 5. Verify

```bash
wr help
wr doctor
wr quick "OpenAI Agents SDK"
```

If you are debugging directly in source tree, use:

```bash
python main.py help
python main.py doctor
```

## 6. Troubleshooting

- Playwright browser missing:
  - `python -m playwright install chromium`
- Python version too low in doctor:
  - Use `.venv312\Scripts\python.exe main.py doctor` (Windows)
  - Or create a fresh `python3.10+` virtualenv and reinstall requirements
- Anti-bot or access challenges:
  - Prefer `visit <url> --js` or `quick --js`
- MCP tools not showing up in Claude:
  - Re-run MCP setup script
  - Restart Claude client and run `/tools`

# Installation Guide

## 1. Prerequisites

- Python `3.10+`
- Network access (for Playwright browser runtime download)
- Recommended: Git

## 2. Basic Install (All Platforms)

```bash
pip install -r requirements.txt
python -m playwright install chromium
python main.py --doctor
```

`--doctor` should pass before running deep crawling tasks.

Windows note:

- If your system `python` is below `3.10`, use the project venv directly:
  - `.venv312\Scripts\python.exe main.py --doctor`
  - `.venv312\Scripts\python.exe main.py quick "OpenAI Agents SDK"`

## 3. OS-Specific Helpers

### Windows

- Basic installer: `install.bat`
- Install global CLI (`wr`): `scripts\windows\install-system-cli.bat`
- Uninstall global CLI: `scripts\windows\uninstall-system-cli.bat`
- Setup Claude MCP: `scripts\windows\setup-claude-mcp.bat`
- Uninstall Claude MCP: `scripts\windows\uninstall-claude-mcp.bat`

### macOS / Linux

```bash
chmod +x scripts/unix/*.sh
./scripts/unix/install-system-cli.sh
./scripts/unix/setup-claude-mcp.sh
```

Uninstall:

```bash
./scripts/unix/uninstall-system-cli.sh
./scripts/unix/uninstall-claude-mcp.sh
```

## 4. Verify

```bash
python main.py help
python main.py --doctor
python main.py quick "OpenAI Agents SDK"
```

If global CLI is installed:

```bash
wr help
wr doctor
```

## 5. Troubleshooting

- Playwright browser missing:
  - `python -m playwright install chromium`
- Python version too low in doctor:
  - Use `.venv312\Scripts\python.exe main.py --doctor` (Windows)
  - Or create a fresh `python3.10+` virtualenv and reinstall requirements
- Anti-bot or access challenges:
  - Prefer `visit <url> --js` or `quick --js`
- MCP tools not showing up in Claude:
  - Re-run MCP setup script
  - Restart Claude client and run `/tools`

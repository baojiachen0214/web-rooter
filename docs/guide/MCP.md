# MCP Guide

## Start MCP Server Manually

```bash
python main.py --mcp
```

## Quick Setup by OS

### Windows

```bash
scripts\windows\setup-claude-mcp.bat
```

### macOS / Linux

```bash
chmod +x scripts/unix/setup-claude-mcp.sh
./scripts/unix/setup-claude-mcp.sh
```

## Manual Claude Configuration

Use one of the following paths:

- Linux: `~/.config/Claude/config.json`
- macOS: `~/Library/Application Support/Claude/config.json`
- Windows: `%APPDATA%\Claude\config.json`

Minimal config:

```json
{
  "mcpServers": {
    "web-rooter": {
      "command": "python",
      "args": ["main.py", "--mcp"],
      "cwd": "/path/to/web-rooter",
      "env": {
        "PYTHONUNBUFFERED": "1",
        "PYTHONIOENCODING": "utf-8"
      }
    }
  }
}
```

Example file:

- `examples/claude/claude-code-mcp.example.json`

## Verify

1. Restart Claude client.
2. Run `/tools`.
3. Confirm `web-rooter` tools are available.

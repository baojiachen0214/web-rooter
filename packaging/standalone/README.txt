Web-Rooter Standalone Bundle

This package is designed for clean machines (no pip/git required).

Windows:
1) Extract zip
2) Double-click install-web-rooter.bat
3) Restart terminal
4) Run:
   wr --version
   wr doctor

macOS / Linux:
1) Extract tar.gz
2) Run:
   chmod +x install-web-rooter.sh
   ./install-web-rooter.sh
3) Restart terminal
4) Run:
   wr --version
   wr doctor

Notes:
- First run may download Chromium runtime if network is available.
- For Claude MCP integration, installer performs best-effort config.
- If MCP is not detected, configure MCP manually with command:
  web-rooter --mcp

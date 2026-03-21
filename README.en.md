<div align="center">
  <img src="./LOGO.png" alt="Web-Rooter Logo" width="220" />
  <h1>Web-Rooter</h1>
  <p><strong>An AI-agent-facing CLI for web research with citations</strong></p>
  <p>After install, use <code>wr</code> (not <code>python main.py ...</code>)</p>

  <p>
    <a href="./LICENSE"><img src="https://img.shields.io/badge/license-MIT-green.svg" alt="License MIT"></a>
    <img src="https://img.shields.io/badge/version-v0.2.4-blue.svg" alt="Version v0.2.4">
    <img src="https://img.shields.io/badge/python-3.10%2B-blue.svg" alt="Python 3.10+">
    <img src="https://img.shields.io/badge/platform-Windows%20%7C%20macOS%20%7C%20Linux-black.svg" alt="Platforms">
  </p>

  <p>
    <a href="./README.md">简体中文（User-first）</a> |
    <a href="./README.zh-CN.md">简体中文（Full）</a>
  </p>
</div>

---

## TL;DR

- Built for AI agents to call, not for manual day-to-day shell work.
- After install, use `wr` as the default entry.
- Outputs are citation-ready (`citations` + `references_text`).

---

## What Is This?

Web-Rooter is not a “manual-only crawler tool”.  
It is a capability layer for AI coding assistants (Claude/Cursor/etc.) to:

- search across multiple sources,
- crawl pages reliably (with anti-bot fallback),
- return citation-ready output (`citations`, `references_text`).

---

## Why Teams Use It

| Problem | Web-Rooter Approach |
|---|---|
| AI returns uncited claims | Always returns source-aware fields |
| Search quality is unstable | Multi-source search + crawl combination |
| Anti-bot breaks scraping | HTTP-first with browser fallback |
| Agent command drift | Skill-guided `do-plan -> do` workflow |

---

## AI Tool Integration

Installers auto-inject skill packs (best-effort) for:

- Claude Code / Claude Desktop
- Cursor
- OpenCode
- OpenClaw

This helps the AI follow a stable route:
`skills -> do-plan -> do --dry-run -> do`.

---

## 3-Minute Start

### Option A: Prebuilt binaries (recommended)

1. Download from release:  
   [https://github.com/baojiachen0214/web-rooter/releases/tag/v0.2.4](https://github.com/baojiachen0214/web-rooter/releases/tag/v0.2.4)
2. Unzip and run installer:
   - Windows: `install-web-rooter.bat`
   - macOS/Linux: `./install-web-rooter.sh`
3. Verify:

```bash
wr --version
wr doctor
wr help
```

### Option B: Source one-click install

```bash
# Windows
install.bat

# macOS / Linux
bash install.sh
```

Then use:

```bash
wr doctor
wr help
```

---

## First 4 Commands

```bash
wr quick "OpenAI Agents SDK best practices"
wr web "RAG benchmark 2026" --crawl-pages=5
wr do "Compare 3 RAG evaluation posts with citations" --dry-run
wr do "Compare 3 RAG evaluation posts with citations" --strict
```

---

## Keep AI From Forgetting `wr`

Paste this into your project instructions (Claude/Cursor rules):

```text
When internet research, crawling, or citation output is needed, always use Web-Rooter (wr) first.
Required flow:
1) wr skills --resolve "<goal>" --compact
2) wr do-plan "<goal>"
3) wr do "<goal>" --dry-run
4) wr do "<goal>" --strict
Do not skip wr and produce uncited conclusions.
```

If the AI still drifts, add:

```text
Run wr help first, then show your planned wr command sequence before continuing.
```

---

## Command Picker

| Goal | Command |
|---|---|
| Quick lookup | `wr quick` |
| Search + crawl | `wr web` |
| Deeper multi-variant research | `wr deep` |
| Auto-planned execution | `wr do` |
| Async long tasks | `wr do-submit` + `wr jobs` |
| Academic papers | `wr academic` |
| Social platforms | `wr social` |
| Runtime health/pressure | `wr telemetry` |

---

## More Docs

- CLI reference: [`docs/guide/CLI.md`](./docs/guide/CLI.md)
- Installation details: [`docs/guide/INSTALLATION.md`](./docs/guide/INSTALLATION.md)
- MCP tools: [`docs/reference/MCP_TOOLS.md`](./docs/reference/MCP_TOOLS.md)

---

Default branch is `main`. `v0.2.4` is the current stable release.

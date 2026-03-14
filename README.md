<div align="center">
  <img src="./LOGO.png" alt="Web-Rooter Logo" width="220" />
  <h1>Web-Rooter</h1>
  <p><strong>给 AI 工具调用的联网检索 CLI（带引用）</strong></p>
  <p>安装后只用 <code>wr</code>，不是长期手敲 <code>python main.py</code></p>

  <p>
    <a href="./LICENSE"><img src="https://img.shields.io/badge/license-MIT-green.svg" alt="License MIT"></a>
    <img src="https://img.shields.io/badge/version-v0.2.1-blue.svg" alt="Version v0.2.1">
    <img src="https://img.shields.io/badge/python-3.10%2B-blue.svg" alt="Python 3.10+">
    <img src="https://img.shields.io/badge/platform-Windows%20%7C%20macOS%20%7C%20Linux-black.svg" alt="Platforms">
  </p>

  <p>
    <a href="./README.zh-CN.md">中文完整版</a> |
    <a href="./README.en.md">English</a>
  </p>
</div>

---

## 用户只要做三件事

### 1) 安装（推荐预编译）

Release 下载：  
[https://github.com/baojiachen0214/web-rooter/releases/tag/v0.2.1](https://github.com/baojiachen0214/web-rooter/releases/tag/v0.2.1)

- Windows：运行 `install-web-rooter.bat`
- macOS/Linux：运行 `./install-web-rooter.sh`

安装后验证：

```bash
wr --version
wr doctor
wr help
```

### 2) 告诉 AI：必须先用 `wr`

把下面这段贴到 Claude/Cursor 的项目规则：

```text
凡是需要联网检索、网页抓取、引用输出，必须优先使用 Web-Rooter（wr）。
固定流程：
1) wr skills --resolve "<用户目标>" --compact
2) wr do-plan "<用户目标>"
3) wr do "<用户目标>" --dry-run
4) wr do "<用户目标>" --strict
```

### 3) 直接让 AI 执行这些命令

```bash
wr quick "OpenAI Agents SDK best practices"
wr web "RAG benchmark 2026" --crawl-pages=5
wr do "对比 3 篇 RAG 评测文章并给出处" --dry-run
wr do "对比 3 篇 RAG 评测文章并给出处" --strict
wr telemetry
```

---

## 你关心的两个问题

1. 这个工具是给谁用的？
   - 核心是给 AI 代理调用；人类只需要安装和下达目标。

2. 安装后用什么命令？
   - 默认入口是 `wr`。  
   - `python main.py` 只作为开发调试兜底。

---

## 自动注入 AI Skills（已内置）

安装脚本会自动注入（best-effort）：

- Claude Code / Claude Desktop
- Cursor
- OpenCode
- OpenClaw

手动重跑：

```bash
python scripts/setup_ai_skills.py --repo-root .
```

---

## 常用命令速查

| 目标 | 命令 |
|---|---|
| 快速查 | `wr quick` |
| 搜索+抓取 | `wr web` |
| 深度研究 | `wr deep` |
| 自动规划执行 | `wr do` |
| 后台任务 | `wr do-submit` + `wr jobs` |
| 学术检索 | `wr academic` |
| 社交检索 | `wr social` |
| 健康度/压力 | `wr telemetry` |

---

## 进阶文档

- CLI 参数全集：[`docs/guide/CLI.md`](./docs/guide/CLI.md)
- 安装细节：[`docs/guide/INSTALLATION.md`](./docs/guide/INSTALLATION.md)
- MCP 工具清单：[`docs/reference/MCP_TOOLS.md`](./docs/reference/MCP_TOOLS.md)

---

默认分支：`main`  
当前稳定版：`v0.2.1`

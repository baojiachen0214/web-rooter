<div align="center">
  <img src="./LOGO.png" alt="Web-Rooter Logo" width="220" />
  <h1>Web-Rooter</h1>
  <p><strong>面向 AI 代理调用的可引用搜索 CLI</strong></p>
  <p>安装后请默认使用 <code>wr</code> 命令</p>

  <p>
    <a href="./LICENSE"><img src="https://img.shields.io/badge/license-MIT-green.svg" alt="License MIT"></a>
    <img src="https://img.shields.io/badge/version-v0.2.4-blue.svg" alt="Version v0.2.4">
    <img src="https://img.shields.io/badge/python-3.10%2B-blue.svg" alt="Python 3.10+">
    <img src="https://img.shields.io/badge/platform-Windows%20%7C%20macOS%20%7C%20Linux-black.svg" alt="Platforms">
  </p>

  <p>
    <a href="./README.md">简体中文（用户版）</a> |
    <a href="./README.en.md">English</a>
  </p>
</div>

---

## TL;DR

- 这是给 AI 代理调用的工具，不是长期手工 CLI。
- 安装后默认使用 `wr`。
- 输出天然带 `citations` 与 `references_text`，可直接引用。

---

## 定位说明

Web-Rooter 不是让用户长期手敲命令的独立工具，  
而是给 Claude/Cursor 等 AI 工具调用的“联网检索 + 抓取 + 引用”能力层。

它会统一输出：

- `citations`（来源列表）
- `references_text`（可直接粘贴的参考文献文本）

---

## 团队为什么会用它

| 问题 | Web-Rooter 做法 |
|---|---|
| AI 给出无来源结论 | 强制输出可引用字段 |
| 搜索结果不稳定 | 多源搜索 + 抓取组合 |
| 反爬导致失败 | HTTP 优先 + 浏览器兜底 |
| AI 指令漂移 | 用 `do-plan -> do` 固定路径 |

---

## AI 工具协同（关键）

安装脚本会自动注入 skills（best-effort）到：

- Claude Code / Claude Desktop
- Cursor
- OpenCode
- OpenClaw

推荐让 AI 固定走：`skills -> do-plan -> do --dry-run -> do`

---

## 如何让 AI 不忘记用 `wr`

把这段贴进你的项目规则（Claude Project Instructions / Cursor Rules）：

```text
只要涉及联网检索、网页抓取、引用输出，必须优先使用 Web-Rooter（wr）。
固定流程：
1) wr skills --resolve "<用户目标>" --compact
2) wr do-plan "<用户目标>"
3) wr do "<用户目标>" --dry-run
4) wr do "<用户目标>" --strict
禁止跳过 wr 直接给无来源结论。
```

如果 AI 仍然跑偏，再补一句：

```text
请先执行 wr help，并先给出你要执行的 wr 命令序列。
```

---

## 3 分钟安装与验证

### 方案 A：预编译安装（推荐）

Release 页面：  
[https://github.com/baojiachen0214/web-rooter/releases/tag/v0.2.4](https://github.com/baojiachen0214/web-rooter/releases/tag/v0.2.4)

- Windows：运行 `install-web-rooter.bat`
- macOS/Linux：运行 `./install-web-rooter.sh`

验证：

```bash
wr --version
wr doctor
wr help
```

### 方案 B：源码一键安装

```bash
# Windows
install.bat

# macOS / Linux
bash install.sh
```

安装后同样使用：

```bash
wr doctor
wr help
```

---

## 新用户先跑这几条

```bash
wr quick "OpenAI Agents SDK best practices"
wr web "RAG benchmark 2026" --crawl-pages=5
wr do "对比 3 篇 RAG 评测文章并给出处" --dry-run
wr do "对比 3 篇 RAG 评测文章并给出处" --strict
wr telemetry
```

---

## 命令选择速查

| 目标 | 命令 |
|---|---|
| 先快速查 | `wr quick` |
| 搜索 + 抓取 | `wr web` |
| 深度研究 | `wr deep` |
| AI 自动规划执行 | `wr do` |
| 后台长任务 | `wr do-submit` + `wr jobs` |
| 学术检索 | `wr academic` |
| 社交观点 | `wr social` |
| 看压力与预算 | `wr telemetry` |

---

## 常见问题

1. 为什么不推荐 `python main.py`？
   - 用户侧统一入口就是 `wr`；
   - `python main.py` 仅作为开发调试或兜底手段。

2. `deep/social` 超时怎么办？
   - 先试 `--crawl=0`；
   - 或先用 `wr web`、`wr quick --js`。

3. skills 注入失败怎么办？
   - 手动执行：`python scripts/setup_ai_skills.py --repo-root .`

---

## 进阶文档

- CLI 参数：[`docs/guide/CLI.md`](./docs/guide/CLI.md)
- 安装细节：[`docs/guide/INSTALLATION.md`](./docs/guide/INSTALLATION.md)
- MCP 工具：[`docs/reference/MCP_TOOLS.md`](./docs/reference/MCP_TOOLS.md)

---

默认分支为 `main`，当前稳定版为 `v0.2.4`。

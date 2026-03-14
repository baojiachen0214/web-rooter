<div align="center">
  <img src="./LOGO.png" alt="Web-Rooter Logo" width="220" />
  <h1>Web-Rooter</h1>
  <p><strong>给 AI 代理调用的可引用搜索 CLI（不是纯手工工具）</strong></p>
  <p>安装后默认用 <code>wr</code>，不用记 <code>python main.py ...</code></p>

  <p>
    <a href="./LICENSE"><img src="https://img.shields.io/badge/license-MIT-green.svg" alt="License MIT"></a>
    <img src="https://img.shields.io/badge/version-v0.2.1-blue.svg" alt="Version v0.2.1">
    <img src="https://img.shields.io/badge/python-3.10%2B-blue.svg" alt="Python 3.10+">
    <img src="https://img.shields.io/badge/platform-Windows%20%7C%20macOS%20%7C%20Linux-black.svg" alt="Platforms">
  </p>

  <p>
    <a href="./README.zh-CN.md">简体中文（完整说明）</a> |
    <a href="./README.en.md">English</a>
  </p>
</div>

---

## 这是什么？

Web-Rooter 是一个面向 AI 编程工具的“可引用搜索”基础层。  
它会做多源搜索、页面抓取、反爬兜底，并输出可直接引用的 `citations` 与 `references_text`。

你通常不是“自己手动长期使用它”，而是让 Claude/Cursor 等 AI 在任务里调用它。

适合这类场景：

- 让 Claude/Cursor 帮你做调研，但必须给出处
- 做报告时需要“结论 + 来源 URL”一起产出
- 想要比普通搜索更稳的网页抓取能力

---

## 和 AI 工具怎么配合？

安装脚本会自动注入 Skills（best-effort），覆盖：

- Claude Code / Claude Desktop
- Cursor
- OpenCode
- OpenClaw

这意味着安装后，AI 工具会更倾向于按 `skills -> do-plan -> do` 的安全路径调用，而不是乱拼底层命令。

---

## 如何让 AI 不忘记调用 `wr`？

把下面这段直接贴进你的 AI 工具项目规则（Claude Project Instructions / Cursor Rules）：

```text
本项目涉及联网检索、网页抓取、引用输出时，必须优先使用 Web-Rooter CLI（wr）。
流程固定为：
1) wr skills --resolve "<用户目标>" --compact
2) wr do-plan "<用户目标>"
3) wr do "<用户目标>" --dry-run
4) wr do "<用户目标>" --strict
禁止直接跳过 wr 去手写底层爬虫或无来源结论。
```

如果 AI 还是没调用，你可以补一句：

```text
请先执行 wr help，并给出你准备使用的 wr 命令序列，再继续。
```

---

## 3 分钟上手（用户视角）

### 方案 A：下载预编译包（推荐）

1. 打开 Release：  
   [https://github.com/baojiachen0214/web-rooter/releases/tag/v0.2.1](https://github.com/baojiachen0214/web-rooter/releases/tag/v0.2.1)
2. 下载对应平台压缩包并解压
3. 运行安装脚本
   - Windows：`install-web-rooter.bat`
   - macOS/Linux：`./install-web-rooter.sh`
4. 打开新终端，验证：

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

安装完成后同样使用 `wr`：

```bash
wr doctor
wr help
```

---

## 安装后先跑这 4 条

```bash
# 1) 快速查一个问题
wr quick "OpenAI Agents SDK best practices"

# 2) 多源搜索 + 抓取（带出处）
wr web "RAG benchmark 2026" --crawl-pages=5

# 3) 先规划再执行（推荐工作流）
wr do "对比 3 篇 RAG 评测文章并给出处" --dry-run
wr do "对比 3 篇 RAG 评测文章并给出处" --strict

# 4) 看系统压力与预算（排查卡慢/内存）
wr telemetry
```

---

## 命令怎么选？

| 目标 | 命令 |
|---|---|
| 先快速查一下 | `wr quick` |
| 要搜索 + 抓取 | `wr web` |
| 要更深更全（多变体） | `wr deep` |
| 让系统自动规划执行 | `wr do` |
| 长任务后台执行 | `wr do-submit` + `wr jobs` |
| 学术论文检索 | `wr academic` |
| 社交平台观点检索 | `wr social` |
| 看健康度/压力 | `wr telemetry` |

---

## 常见问题

1. 安装后为什么不用 `python main.py`？
   - 面向用户的标准入口就是 `wr`。  
   - `python main.py ...` 主要用于开发调试或未安装全局命令时的临时调用。

2. `deep/social` 偶尔超时怎么办？
   - 先用 `--crawl=0` 只拿搜索结果；
   - 或先用 `wr web`、`wr quick --js`。

3. 怎么确认 Skills 注入成功？
   - Claude Code 里执行 `/tools`；
   - 或手动重跑：
     - `python scripts/setup_ai_skills.py --repo-root .`

---

## 进阶文档

- CLI 参数全集：[`docs/guide/CLI.md`](./docs/guide/CLI.md)
- 安装细节：[`docs/guide/INSTALLATION.md`](./docs/guide/INSTALLATION.md)
- MCP 工具清单：[`docs/reference/MCP_TOOLS.md`](./docs/reference/MCP_TOOLS.md)
- 中文完整说明：[`README.zh-CN.md`](./README.zh-CN.md)

---

默认分支是 `main`，`v0.2.1` 已是正式发布版本。

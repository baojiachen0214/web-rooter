<div align="center">
  <img src="./LOGO.png" alt="Web-Rooter Logo" width="220" />
  <h1>Web-Rooter</h1>
  <p><strong>给 AI 编程工具的可引用联网检索层</strong></p>
  <p>让 Claude/Cursor 在任务中稳定调用 <code>wr</code>，输出“结论 + 来源”</p>

  <p>
    <a href="./LICENSE"><img src="https://img.shields.io/badge/license-MIT-green.svg" alt="License MIT"></a>
    <img src="https://img.shields.io/badge/version-v0.2.1-blue.svg" alt="Version v0.2.1">
    <img src="https://img.shields.io/badge/python-3.10%2B-blue.svg" alt="Python 3.10+">
    <img src="https://img.shields.io/badge/platform-Windows%20%7C%20macOS%20%7C%20Linux-black.svg" alt="Platforms">
    <img src="https://img.shields.io/badge/interface-CLI%20%7C%20MCP-orange.svg" alt="Interfaces">
  </p>

  <p>
    <a href="./README.zh-CN.md">中文（完整）</a> |
    <a href="./README.en.md">English</a>
  </p>
</div>

---

## TL;DR

- 这是一个 **给 AI 调用** 的工具，不是人类长期手敲脚本的工具。
- 安装后统一入口是 **`wr`**（不是默认 `python main.py ...`）。
- 输出自带 `citations` 和 `references_text`，可以直接进报告/PR 说明。

```bash
wr quick "OpenAI Agents SDK best practices"
wr web "RAG benchmark 2026" --crawl-pages=5
wr do "对比 3 篇 RAG 评测文章并给出处" --strict
```

---

## 为什么团队会用它

| 问题 | Web-Rooter 的做法 |
|---|---|
| AI 会给“无来源结论” | 强制输出 `citations` 与 `references_text` |
| 普通搜索召回不稳 | `web/deep` 多源检索 + 页面抓取 |
| 反爬导致抓取失败 | HTTP 优先，必要时自动浏览器兜底 |
| AI 容易乱走命令 | 用 skills + `do-plan` + `do` 固定执行路径 |

---

## 1 分钟安装

### 方案 A：预编译（推荐）

Release 下载：  
[https://github.com/baojiachen0214/web-rooter/releases/tag/v0.2.1](https://github.com/baojiachen0214/web-rooter/releases/tag/v0.2.1)

- Windows：`install-web-rooter.bat`
- macOS/Linux：`./install-web-rooter.sh`

### 方案 B：源码一键安装

```bash
# Windows
install.bat

# macOS / Linux
bash install.sh
```

### 安装完成验证

```bash
wr --version
wr doctor
wr help
```

---

## 让 AI 永远记得用 `wr`

安装脚本会自动注入 skills（best-effort）到：

- Claude Code / Claude Desktop
- Cursor
- OpenCode
- OpenClaw

再把下面规则贴进你的项目指令（强烈推荐）：

```text
凡是涉及联网检索、网页抓取、引用输出，必须优先使用 Web-Rooter（wr）。
固定流程：
1) wr skills --resolve "<用户目标>" --compact
2) wr do-plan "<用户目标>"
3) wr do "<用户目标>" --dry-run
4) wr do "<用户目标>" --strict
禁止跳过 wr 直接给无来源结论。
```

如果 AI 还是跑偏，补一句：

```text
请先执行 wr help，并先给出你将执行的 wr 命令序列。
```

---

## 命令选择表

| 你要做什么 | 直接用 |
|---|---|
| 快速查一个点 | `wr quick` |
| 搜索 + 抓取页面 | `wr web` |
| 深度多变体研究 | `wr deep` |
| 自动规划并执行 | `wr do` |
| 长任务后台跑 | `wr do-submit` + `wr jobs` |
| 学术论文检索 | `wr academic` |
| 社交观点检索 | `wr social` |
| 看健康度和资源压力 | `wr telemetry` |

---

## 一个标准工作流（可直接复制）

```bash
# 1) 先让系统判断最合适 skill
wr skills --resolve "比较三篇 RAG 评测并给出处" --compact

# 2) 先看计划
wr do-plan "比较三篇 RAG 评测并给出处"

# 3) 先 dry-run
wr do "比较三篇 RAG 评测并给出处" --dry-run

# 4) 正式执行
wr do "比较三篇 RAG 评测并给出处" --strict
```

---

## 输出契约（对消费者最重要）

你重点看两个字段：

- `citations`: 结论对应的来源 URL/标题
- `references_text`: 已格式化的可粘贴参考文献

也就是说，结果天然是“可审计、可引用、可复现”的。

---

## 常见问题

1. 为什么不用 `python main.py`？
   - 用户入口就是 `wr`。  
   - `python main.py` 仅用于开发调试或兜底。

2. `deep/social` 超时怎么办？
   - 先试 `--crawl=0`；
   - 或先用 `wr web` / `wr quick --js`。

3. skills 注入失败怎么办？
   - 手动执行：`python scripts/setup_ai_skills.py --repo-root .`

---

## 文档导航

- CLI 参数全集：[`docs/guide/CLI.md`](./docs/guide/CLI.md)
- 安装细节：[`docs/guide/INSTALLATION.md`](./docs/guide/INSTALLATION.md)
- MCP 工具清单：[`docs/reference/MCP_TOOLS.md`](./docs/reference/MCP_TOOLS.md)

---

默认分支：`main`  
稳定版本：`v0.2.1`

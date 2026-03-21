<div align="center">
  <img src="./LOGO.png" alt="Web-Rooter Logo" width="240" />
  <h1>Web-Rooter</h1>
  <p><strong>给 AI 编程助手的“可引用联网执行层”</strong></p>
  <p>让 Claude Code / Cursor / 本地 Agent 通过同一套 <code>wr</code> 命令稳定完成：检索 → 抓取 → 引用 → 可复查</p>

  <p>
    <a href="./LICENSE"><img src="https://img.shields.io/badge/license-MIT-green.svg" alt="License MIT"></a>
    <img src="https://img.shields.io/badge/version-v0.2.4-blue.svg" alt="Version v0.2.4">
    <img src="https://img.shields.io/badge/python-3.10%2B-blue.svg" alt="Python 3.10+">
    <img src="https://img.shields.io/badge/platform-Windows%20%7C%20macOS%20%7C%20Linux-black.svg" alt="Platforms">
    <img src="https://img.shields.io/badge/interface-CLI%20%7C%20MCP-orange.svg" alt="Interfaces">
  </p>

  <p>
    <a href="./README.zh-CN.md">中文（完整版）</a> |
    <a href="./README.en.md">English</a>
  </p>
</div>

---

## 先讲结论

Web-Rooter 不是“给人长期手敲的爬虫工具”，而是“给 AI 调用的标准化联网协议层”。

- 你给 AI 一个目标
- AI 执行 `wr` 的固定流程
- 输出天然带 `citations` + `references_text`

目标是把“AI 看起来答对但没有来源”升级成“AI 有执行链路、有引用、可审计”。

---

## 你是否需要它（30 秒判断）

如果你在用 Claude Code / Cursor / 其他 Vibe Coding 工具，并且出现以下任一情况：

- AI 会回答，但经常不给来源
- 搜索、抓取、引用整理流程很碎
- 长任务偶发卡住或不稳定
- 团队想统一 AI 联网执行规范

那 Web-Rooter 就是你缺的那层“执行底座”。

---

## 90 秒安装

### 方案 A：预编译安装（推荐）

Release 页面：  
[https://github.com/baojiachen0214/web-rooter/releases/tag/v0.2.4](https://github.com/baojiachen0214/web-rooter/releases/tag/v0.2.4)

- Windows：运行 `install-web-rooter.bat`
- macOS/Linux：运行 `./install-web-rooter.sh`

### 方案 B：源码安装

```bash
# Windows
install.bat

# macOS / Linux
bash install.sh
```

### 安装后立刻验证

```bash
wr --version
wr doctor
wr help
```

> 安装后默认入口是 `wr`，不是 `python main.py`。  
> `python main.py` 仅用于源码调试和开发兜底。

---

## 给 AI 的“强约束规则”（直接复制）

把这段放进 Claude Project Instructions / Cursor Rules：

```text
凡是涉及联网检索、网页抓取、引用输出，必须优先使用 Web-Rooter（wr）。
固定流程：
1) wr skills --resolve "<用户目标>" --compact
2) wr do-plan "<用户目标>"
3) wr do "<用户目标>" --dry-run
4) wr do "<用户目标>" --strict
禁止跳过 wr 直接给无来源结论。
```

如果 AI 偶尔还会忘记，再补一句：

```text
请先执行 wr help，并先输出你将执行的 wr 命令序列。
```

安装脚本会 best-effort 自动注入 skills 到 Claude/Cursor/OpenCode/OpenClaw，但项目级规则仍建议显式写上。

---

## 标准工作流（可直接跑）

```bash
wr skills --resolve "比较三篇 RAG 评测并给出处" --compact
wr do-plan "比较三篇 RAG 评测并给出处"
wr do "比较三篇 RAG 评测并给出处" --dry-run
wr do "比较三篇 RAG 评测并给出处" --strict
```

长任务请走后台作业系统，避免阻塞：

```bash
wr do-submit "比较三篇 RAG 评测并给出处" --strict
wr jobs --status=running
wr job-status <job_id>
wr job-result <job_id>
```

---

## 输出契约（为什么它适合生产）

```json
{
  "citations": [
    {
      "id": "W1",
      "title": "Example Source",
      "url": "https://example.com/report"
    }
  ],
  "references_text": "[W1] Example Source https://example.com/report",
  "comparison": {
    "total_results": 8,
    "corroborated_results": 3
  }
}
```

消费者最该盯住的两个字段：

- `citations`：关键结论的来源证据
- `references_text`：可直接粘贴到报告/PR 的引用文本

---

## 命令选择表

| 目标 | 命令 |
|---|---|
| 快速查一个点 | `wr quick` |
| 搜索 + 抓取 | `wr web` |
| 多变体深度研究 | `wr deep` |
| 自动规划并执行 | `wr do` |
| 后台异步任务 | `wr do-submit` + `wr jobs` |
| 清理历史后台作业 | `wr jobs-clean` |
| 学术文献检索 | `wr academic` |
| 社交观点检索 | `wr social` |
| 健康度/压力观测 | `wr telemetry` |

---

## v0.2.4 的核心升级（稳定性优先）

这一版优先解决“会让 AI 生产流崩掉”的问题，并进一步修复了部分 `v0.2.3` 安装环境里暴露出的 SSL 兼容问题：

- `aiohttp` 的 SSL 策略改为“系统证书链优先 + certifi 补充”，不再用 `certifi` 覆盖本机/企业环境的自定义根证书
- 连接池路径补齐同一套 SSL 策略，避免主会话修好了但池化请求仍然偶发证书错误
- 增加显式紧急开关 `WEB_ROOTER_INSECURE_SSL=1`，仅用于可信网络下的临时排障；`doctor` 会明确警告该状态不安全
- 强化 `bilibili` / `xiaohongshu` 支持：补充配置化浏览器搜索入口、候选搜索 URL、结果选择器与高信号详情页识别
- 为 B 站补充本地登录模板入口，降低搜索页与详情页遇到登录门槛时的恢复成本
- 发布版打包补齐 `profiles/auth`、`profiles/search_templates`、`profiles/challenge_profiles` 等运行时资源，减少二进制版与源码版行为偏差
- 新增回归测试覆盖 SSL 上下文选择与 B 站搜索入口，优先保证发布稳定性

---

## 常见问题

1. `wr doctor` 没通过，还能做什么？  
可以先做规划类命令：`skills`、`do-plan`、`do --dry-run`、`workflow-schema`；真实抓取建议等依赖就绪后再执行。

2. 长任务容易卡怎么办？  
优先用 `wr do-submit` 后台运行，再用 `jobs` 系列命令轮询结果。

3. AI 输出没引用怎么办？  
把上面的“强约束规则”写入项目指令，并把“必须包含 citations”作为 review 检查项。

---

## 文档入口

- CLI 命令全集：[`docs/guide/CLI.md`](./docs/guide/CLI.md)
- 安装与打包：[`docs/guide/INSTALLATION.md`](./docs/guide/INSTALLATION.md)
- MCP 工具参考：[`docs/reference/MCP_TOOLS.md`](./docs/reference/MCP_TOOLS.md)

---

默认分支：`main`  
当前稳定版本：`v0.2.4`

<div align="center">
  <img src="./LOGO.png" alt="Web-Rooter Logo" width="240" />
  <h1>Web-Rooter</h1>
  <p><strong>给 AI 编程工具的可引用联网研究层</strong></p>
  <p>让 Claude Code / Cursor / 本地 Agent 在同一条 <code>wr</code> 链路里稳定完成“检索 → 抓取 → 引用”</p>

  <p>
    <a href="./LICENSE"><img src="https://img.shields.io/badge/license-MIT-green.svg" alt="License MIT"></a>
    <img src="https://img.shields.io/badge/version-v0.2.2-blue.svg" alt="Version v0.2.2">
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

## 这是什么（先说人话）

Web-Rooter 不是“又一个爬虫脚本集合”，而是给 AI 用的联网执行底座：

- 你给 AI 一个目标
- AI 调用 `wr` 执行固定流程
- 输出结论时自动带 `citations` 和 `references_text`

目标是把“AI 会编答案但不给来源”的体验，改造成“AI 有执行链路、有引用、可复查”。

---

## 30 秒判断你需不需要它

你正在用 Claude Code / Cursor / 其他 AI 编程工具，并且遇到以下任一问题：

- AI 回答看起来正确，但没有可追溯来源
- 搜索、抓取、整理出处要切多个工具，工作流很碎
- 长任务容易卡住，或者运行不稳定
- 希望团队里所有 AI 都走同一套命令标准

如果是，Web-Rooter 就是这层“统一执行协议”。

---

## 1 分钟上手

### 1) 安装

预编译安装（推荐消费者）：
[https://github.com/baojiachen0214/web-rooter/releases/tag/v0.2.2](https://github.com/baojiachen0214/web-rooter/releases/tag/v0.2.2)

- Windows：`install-web-rooter.bat`
- macOS/Linux：`./install-web-rooter.sh`

源码安装：

```bash
# Windows
install.bat

# macOS / Linux
bash install.sh
```

### 2) 验证

```bash
wr --version
wr doctor
```

### 3) 跑第一个可引用任务

```bash
wr skills --resolve "比较三篇 RAG 评测并给出处" --compact
wr do-plan "比较三篇 RAG 评测并给出处"
wr do "比较三篇 RAG 评测并给出处" --dry-run
wr do "比较三篇 RAG 评测并给出处"
```

如果你在源码目录调试，才使用 `python main.py ...`。

---

## 给 AI 的“强约束提示词”（直接可复制）

把下面这段贴进项目级 AI 指令：

```text
凡是涉及联网检索、网页抓取、引用输出，必须优先使用 Web-Rooter（wr）。
固定流程：
1) wr skills --resolve "<用户目标>" --compact
2) wr do-plan "<用户目标>"
3) wr do "<用户目标>" --dry-run
4) wr do "<用户目标>"
禁止跳过 wr 直接给无来源结论。
```

安装脚本会 best-effort 自动注入技能引导到 Claude/Cursor/OpenCode/OpenClaw，但项目指令里再强调一次，效果最稳。

---

## 输出契约（为什么它适合生产）

Web-Rooter 的核心价值不是“搜到内容”，而是“可引用、可审计、可复现”。

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

面向消费者最重要的两个字段：

- `citations`：每条关键结论的来源
- `references_text`：已经格式化好的可粘贴引用

---

## 命令选择图

| 你要做什么 | 命令 |
|---|---|
| 快速查一个点 | `wr quick` |
| 多引擎检索 + 抓取 | `wr web` |
| 深度多变体研究 | `wr deep` |
| 让系统自动规划并执行 | `wr do` |
| 长任务异步后台执行 | `wr do-submit` + `wr jobs` |
| 清理历史后台作业 | `wr jobs-clean` |
| 学术文献检索 | `wr academic` |
| 社交观点抓取 | `wr social` |
| 查看系统健康与压力 | `wr telemetry` |
| 检查挑战页/登录态提示 | `wr challenge-profiles` / `wr auth-hint` |

---

## 可靠性（v0.2.2 重点）

这一版聚焦在“AI 长时间实战是否稳定”：

- 命令级超时护栏：`--command-timeout-sec` / `WEB_ROOTER_COMMAND_TIMEOUT_SEC`
- 超长输出保持合法 JSON（不再出现“被截断后 AI 解析失败”）
- URL 归一化强化：拒绝 path-only / malformed URL，减少无效重试
- 后台作业硬化：
  - 僵尸作业自动纠偏
  - 结果文件大小预算与压缩
  - 作业列表按更新时间排序
  - `wr jobs-clean` 清理历史作业目录
- 缓存与预算路径增强，避免在异常环境下演变成资源失控

一句话：优先修“会让 AI 生产流崩掉”的问题，而不是堆炫技功能。

---

## 常见问题

1. 为什么强调 `wr` 而不是 `python main.py`？  
`wr` 是安装后的正式用户入口，适合 AI 和团队统一调用；`python main.py` 是源码调试入口。

2. `doctor` 没通过还能做什么？  
可以先做路由/规划类命令：`skills`、`do-plan`、`do --dry-run`、`workflow-schema`。  
真实抓取类命令建议等依赖就绪后再执行。

3. 长任务怕卡住怎么办？  
优先用 `wr do-submit ...` 后台执行，再用 `wr jobs` / `wr job-status` / `wr job-result` 轮询。

4. AI 还是偶尔忘记调用 `wr` 怎么办？  
把上面的“强约束提示词”放进项目级系统指令，并在 code review 中把“是否有 citations”作为检查项。

---

## 文档

- CLI 参数全集：[`docs/guide/CLI.md`](./docs/guide/CLI.md)
- 安装与打包：[`docs/guide/INSTALLATION.md`](./docs/guide/INSTALLATION.md)
- MCP 工具参考：[`docs/reference/MCP_TOOLS.md`](./docs/reference/MCP_TOOLS.md)

---

默认分支：`main`  
当前稳定版本：`v0.2.2`

<div align="center">
  <img src="./LOGO.png" alt="Web-Rooter Logo" width="240" />
  <h1>Web-Rooter</h1>
  <p><strong>给 AI 编程助手的“可引用联网执行层”</strong></p>
  <p>让 Claude Code / Cursor / 本地 Agent 通过同一套 <code>wr</code> 命令稳定完成：检索 → 抓取 → 引用 → 可复查</p>

  <p>
    <a href="./LICENSE"><img src="https://img.shields.io/badge/license-MIT-green.svg" alt="License MIT"></a>
    <img src="https://img.shields.io/badge/version-v0.3.1-blue.svg" alt="Version v0.3.0">
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
[https://github.com/baojiachen0214/web-rooter/releases/tag/v0.3.1](https://github.com/baojiachen0214/web-rooter/releases/tag/v0.3.0)

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
```

若安装过程中出现问题，`wr doctor`指令会自动检查并给出修复方案。

---

## 15 秒上手（零手动配置）

安装脚本会自动注入 skills 到 Claude/Cursor/OpenCode/OpenClaw，无需手动配置！只需配置 `cookie` 即可：

Web-Rooter 具备一键快速配置 `cookie` 能力，现已支持 Safari、Chrome、Edge、Firefox、Brave 浏览器。在终端执行以下指令即可完成配置（需要事先在上述浏览器中对所需访问网页登陆）：

```bash
wr cookie
```

> macOS 系统中需要给终端开启 “完全磁盘访问权限” 才能访问到 Safari 的 `cookie`

---

## 参考示例（可直接跑）

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

## 精选命令选择表

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

> 若使用过程中遗忘，可使用 `wr help` 指令快速查看其他指令使用方法

---

### v0.3.1 更新日志

- 新增公司新闻中心批量抓取能力（`company_news_mining`）
  - 集成 job / checkpoint / queue / memory 模块，支持断点续爬与内存保护
  - 提供 `scripts/pilot_crawl_20.py` 试抓脚本与完整使用手册 [`docs/guide/COMPANY_NEWS_MINING.md`](./docs/guide/COMPANY_NEWS_MINING.md)
- 新增 `NewsCountChangeProcessor` 后处理器，用于质量验收阶段统计新闻增量

### v0.3.0 更新日志

- 修复若干已知问题：
  - 修复 `SearchEngine.QUARK` 业务问题
  - `aiohttp` 的 SSL 策略改为"系统证书链优先 + certifi 补充"
- 增强了主业务链路的稳定性：
  - 优化作业系统排序和清理逻辑
  - 在 `workflow` 结束后判断 `body / author / engagement / comments` 等是否真的拿到
  - 给出完成度、缺失项、是否建议走 `fallback`

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
- 公司新闻批量抓取：[`docs/guide/COMPANY_NEWS_MINING.md`](./docs/guide/COMPANY_NEWS_MINING.md)
- MCP 工具参考：[`docs/reference/MCP_TOOLS.md`](./docs/reference/MCP_TOOLS.md)

---

默认分支：`main`  
当前稳定版本：`v0.3.1`
<div align="center">
  <img src="./LOGO.png" alt="Web-Rooter Logo" width="220" />
  <h1>Web-Rooter</h1>
  <p><strong>给 AI 与人类都好用的网页搜索 + 抓取 CLI 工具</strong></p>
  <p>一句命令，拿到可引用结果（含来源 URL 与 references_text）</p>

  <p>
    <a href="./LICENSE"><img src="https://img.shields.io/badge/license-MIT-green.svg" alt="License MIT"></a>
    <img src="https://img.shields.io/badge/version-v0.2.1-blue.svg" alt="Version v0.2.1">
    <img src="https://img.shields.io/badge/python-3.10%2B-blue.svg" alt="Python 3.10+">
    <img src="https://img.shields.io/badge/platform-Windows%20%7C%20macOS%20%7C%20Linux-black.svg" alt="Platforms">
  </p>

  <p>
    <a href="./README.zh-CN.md">简体中文（完整版）</a> |
    <a href="./README.en.md">English</a>
  </p>
</div>

---

## 这个项目能做什么？

Web-Rooter 解决的是一个很实际的问题：  
你想让 AI “上网查资料并给出处”，但普通搜索结果不稳定、没法引用、容易被反爬拦截。

它提供统一 CLI，支持：

- 多引擎搜索（`web / deep`）
- 自动抓取页面正文（必要时自动切到浏览器模式）
- 结构化输出 `citations` 和 `references_text`（可直接贴到报告）
- 学术、社交、电商等垂直检索

---

## 3 分钟上手

### 方式 A：零依赖安装（推荐普通用户）

1. 打开 Release 页面下载对应系统包：  
   [https://github.com/baojiachen0214/web-rooter/releases/tag/v0.2.1](https://github.com/baojiachen0214/web-rooter/releases/tag/v0.2.1)
2. 解压并运行安装脚本：
   - Windows：双击 `install-web-rooter.bat`
   - macOS/Linux：`./install-web-rooter.sh`
3. 验证：

```bash
wr --version
wr help
```

### 方式 B：源码一键安装（开发者常用）

```bash
# Windows
install.bat

# macOS / Linux
bash install.sh
```

验证：

```bash
python main.py doctor
python main.py help
```

---

## 第一次使用（直接复制）

```bash
# 1) 快速查一个问题
python main.py quick "OpenAI Agents SDK best practices"

# 2) 做可引用的多源搜索
python main.py web "RAG benchmark 2026" --crawl-pages=5

# 3) 让系统自动规划执行步骤（推荐）
python main.py do "对比 3 篇 RAG 评测文章并给出处" --dry-run
python main.py do "对比 3 篇 RAG 评测文章并给出处" --strict

# 4) 看运行健康（排查卡慢/爆内存）
python main.py telemetry
```

如果你安装的是二进制版本，把 `python main.py` 换成 `wr` 即可。

---

## 命令怎么选？

| 你的目标 | 用这个命令 |
|---|---|
| 我就想先查一下 | `quick` |
| 要多引擎结果 + 页面抓取 | `web` |
| 要更深、更全（多变体） | `deep` |
| 让系统自动规划整个流程 | `do` |
| 长任务避免阻塞终端 | `do-submit` + `jobs/job-status/job-result` |
| 学术论文检索 | `academic` |
| 社交平台观点检索 | `social` |
| 查看资源压力与预算 | `telemetry` |

---

## 常用场景示例

```bash
# 学术检索（论文 + 引用）
python main.py academic "RAG evaluation" --papers-only --source=arxiv --source=semantic_scholar

# 社交观点（指定平台）
python main.py social "iPhone 17 评测" --platform=xiaohongshu --platform=zhihu

# 深度主题研究
python main.py deep "AI Agent 工程化" --variants=4 --crawl=5 --platforms --channel=news

# 提交后台任务（不阻塞）
python main.py do-submit "分析 RAG benchmark 论文关系并给引用" --skill=academic_relation_mining --strict --timeout-sec=1200
python main.py jobs --status=running
python main.py job-result <job_id>
```

---

## 输出怎么看？

重点看这两个字段：

- `citations`: 每条结论对应的来源 URL 与标题
- `references_text`: 已格式化好的参考文献文本

这意味着：你可以把结果直接贴进报告，不用再手工整理出处。

---

## 常见问题

1. `deep/social` 偶尔超时
   - 先试 `--crawl=0`（先拿搜索结果）
   - 或改用 `web` / `quick --js`

2. 想要更稳的长期运行（避免爆内存）
   - 本版本默认已启用有界队列和去重预算
   - 用 `python main.py telemetry` 查看 `pressure/utilization/alerts`

3. 需要接入 Claude Code / MCP
   - 先跑安装脚本，MCP 可选开启：
     - `install.bat --with-mcp`
     - `bash install.sh --with-mcp`

---

## 进阶文档

- CLI 参数全集：[`docs/guide/CLI.md`](./docs/guide/CLI.md)
- 安装细节：[`docs/guide/INSTALLATION.md`](./docs/guide/INSTALLATION.md)
- MCP 工具表：[`docs/reference/MCP_TOOLS.md`](./docs/reference/MCP_TOOLS.md)
- 中文完整版介绍：[`README.zh-CN.md`](./README.zh-CN.md)

---

## 分支说明

仓库默认分支已回到 `main`，用于正式版本发布与稳定迭代。  
`v0.2.1` 正式版已发布，可直接使用上面的 Release 链接下载安装。

### MCP 工具清单

| 工具 | 用途 |
|------|------|
| `web_search_internet` | 多引擎互联网搜索 |
| `web_research` | 主题深度研究 |
| `web_search_academic` | 学术文献搜索 |
| `web_mindsearch` | MindSearch 图研究 |
| `web_search_social` | 社交媒体搜索 |
| `web_search_commerce` | 电商/本地生活搜索 |
| `web_fetch` / `web_fetch_js` | HTTP / 浏览器页面获取 |
| `web_crawl` | 站点深度爬取 |
| `web_extract` | 目标信息提取 |
| `web_context_snapshot` | 查看全局深度抓取上下文事件 |
| `web_postprocessors` / `web_planners` | 加载后处理器 / 研究规划器扩展 |
| `web_challenge_profiles` | 查看挑战页 workflow 路由档案 |
| `web_auth_profiles` / `web_auth_hint` / `web_auth_template` | 管理需登录站点的本地登录态模板 |

---

## 技术特性

### 反爬策略

- **HTTP 优先**：高性能异步抓取，支持连接池与缓存
- **浏览器兜底**：遇到挑战页自动切换 Playwright
- **隐身模式**：Canvas 指纹噪声、WebRTC 禁用、随机 User-Agent
- **Cloudflare 自动处理**：内置等待与重试逻辑

### 搜索增强

- **多引擎并行**：Google + Bing + Baidu + DuckDuckGo
- **查询变体**：自动生成子查询，扩展召回
- **渠道扩展**：`--news` / `--platforms` / `--commerce` 自动注入 site: 限定
- **交叉验证**：`comparison.corroborated_results` 显示多源 corroborated 结果数

### 可靠性保障

- **断点续爬**：checkpoint 机制支持中断恢复
- **内存优化**：大页面流式处理，防止 OOM
- **健康检查**：`main.py --doctor` 一键诊断环境

### 已知限制

- **网络超时**：`deep` / `social` 命令在部分网络环境下可能遇到超时（由反爬/挑战页导致），建议：
  - 使用 `--crawl=0` 跳过页面抓取，仅获取搜索结果
  - 优先使用 `web` 命令作为替代
  - 检查网络连接或尝试切换网络环境

---

## 项目结构

```
web-rooter/
├── main.py                 # CLI / MCP / HTTP 统一入口
├── agents/
│   └── web_agent.py        # 任务编排层 (visit/search/research/crawl)
├── core/
│   ├── crawler.py          # HTTP 抓取核心
│   ├── browser.py          # Playwright 浏览器管理
│   ├── challenge_workflow.py # 挑战页 workflow 路由与动作编排
│   ├── workflow.py         # 声明式 AI 工作流执行器（可组合步骤）
│   ├── command_ir.py       # 命令 IR 与 lint 校验
│   ├── skills.py           # skill 契约加载与意图路由
│   ├── trace_distill.py    # 执行轨迹蒸馏（紧凑记忆）
│   ├── global_context.py   # 全局深度抓取事件存储
│   ├── postprocess.py      # 抓取后处理扩展注册中心
│   ├── search/             # 搜索引擎实现
│   │   ├── engine_base.py  # 配置驱动搜索流程
│   │   ├── advanced.py     # 多引擎与深度搜索聚合
│   │   ├── mindsearch_pipeline.py # MindSearch 图研究管线
│   │   ├── research_planner.py # MindSearch planner 注册中心
│   │   └── universal_parser.py  # 搜索结果解析
│   ├── academic_search.py  # 学术搜索实现
│   └── citation.py         # 引用格式生成
├── plugins/                # 用户扩展（示例）
│   ├── post_processors/
│   └── planners/
├── profiles/               # 内置可配置模板
│   ├── challenge_profiles/ # 平台级挑战页 profile JSON
│   ├── skills/             # AI skills 契约（意图->模板/策略）
│   ├── search_templates/   # 平台搜索入口/backup 优先级模板 JSON
│   ├── auth/               # 登录态模板 JSON
│   └── workflows/          # workflow 模板 JSON（社交/学术）
├── tools/
│   └── mcp_tools.py        # MCP 协议适配
├── scripts/                # 跨平台安装与回归脚本
│   ├── regression/         # 真实回归与 skills A/B
├── docs/                   # 完整文档
│   ├── guide/              # 使用指南
│   ├── reference/          # API 参考
│   └── architecture/       # 架构文档
└── tests/                  # 自动化测试
```

---

## 文档导航

| 文档 | 内容 |
|------|------|
| [docs/guide/INSTALLATION.md](./docs/guide/INSTALLATION.md) | 详细安装指南 |
| [docs/guide/CONFIGURATION.md](./docs/guide/CONFIGURATION.md) | 配置说明 |
| [docs/guide/CLI.md](./docs/guide/CLI.md) | CLI 完整命令参考 |
| [docs/guide/MCP.md](./docs/guide/MCP.md) | MCP 集成指南 |
| [docs/reference/MCP_TOOLS.md](./docs/reference/MCP_TOOLS.md) | MCP 工具详细说明 |
| [docs/architecture/PROJECT_STRUCTURE.md](./docs/architecture/PROJECT_STRUCTURE.md) | 项目架构设计 |

---

## 开源致谢

本项目在搜索/爬虫方向参考了多个优秀开源项目，详见 [ACKNOWLEDGMENTS.md](./ACKNOWLEDGMENTS.md)。

---

## 使用声明

**本项目专为辅助 Vibe Coding 工具（如 Claude Code、Cursor 等）进行资料检索和文献查找而开发。**

⚠️ **严禁将本项目二次开发成具有网络危害的攻击性程序，包括但不限于：**
- 大规模恶意爬虫用于 DDoS 攻击
- 自动化注册/刷量/薅羊毛工具
- 绕过安全机制进行未授权数据抓取
- 任何违反目标网站服务条款的滥用行为

使用者应遵守相关法律法规和目标网站的 robots.txt 及服务条款。

---

## License

MIT License - 详见 [LICENSE](./LICENSE)

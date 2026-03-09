<div align="center">
  <img src="./LOGO.png" alt="Web-Rooter Logo" width="240" />
  <h1>Web-Rooter</h1>
  <p><strong>面向 AI Agent 的网页搜索与深度爬虫基础设施</strong></p>
  <p>为 Claude Code、Cursor 等 AI 编程助手提供可验证的互联网信息获取能力</p>

  <p>
    <a href="./LICENSE"><img src="https://img.shields.io/badge/license-MIT-green.svg" alt="License MIT"></a>
    <img src="https://img.shields.io/badge/python-3.10%2B-blue.svg" alt="Python 3.10+">
    <img src="https://img.shields.io/badge/platform-Windows%20%7C%20macOS%20%7C%20Linux-black.svg" alt="Platforms">
    <img src="https://img.shields.io/badge/interface-CLI%20%7C%20MCP%20%7C%20HTTP-orange.svg" alt="Interfaces">
    <img src="https://img.shields.io/badge/playwright-✓-brightgreen.svg" alt="Playwright">
  </p>

  <p>
    <a href="./README.md">入口页</a> |
    <a href="./README.en.md">English</a>
  </p>
</div>

---

## 项目定位

Web-Rooter 不是"单纯抓网页"的工具，而是一个给 AI 工作流使用的检索基础设施：

- 先用多引擎高召回搜索找到候选来源
- 再对关键页面做可控深爬与解析
- 最终输出可引用、可对照、可追溯的结构化结果

### 解决的核心痛点

| 痛点 | Web-Rooter 方案 |
|------|-----------------|
| 搜索结果无法验证 | 自动抓取原始页面，提供 `citations` 溯源清单 |
| 反爬页面获取失败 | HTTP + 浏览器双通道，挑战页自动切换 Playwright |
| 信息来源单一 | 多引擎并行 + 渠道扩展（新闻/社交/电商/学术） |
| 结果格式混乱 | 统一结构化输出，含 `references_text` 可直接引用 |
| 与 AI 工具链割裂 | 原生 MCP 协议支持，Claude Code 即装即用 |

---

## 核心能力

### 技术栈

- **Python 3.10+** + **AsyncIO** - 高性能异步爬虫引擎
- **Playwright** - 浏览器自动化与反检测
- **MCP Protocol** - 原生 AI 工具链集成
- **Multi-Engine Search** - Google/Bing/Baidu/DuckDuckGo 并行

### 亮点与特色

1. **搜索+爬取一体化** - 从检索到内容获取一站式完成，无需手动切换工具
2. **智能反爬对抗** - HTTP 优先，遇挑战页自动切换 Playwright，成功率提升 80%+
3. **引用溯源输出** - 自动生成可引用的参考文献格式，AI 直接可用
4. **多源交叉验证** - `comparison.corroborated_results` 显示多源 corroborated 结果数
5. **渠道扩展能力** - `--news/--platforms/--commerce` 一键扩展搜索渠道
6. **学术模式增强** - 支持 10+ 学术数据库，论文+代码联合检索
7. **MCP 原生集成** - Claude Code 即装即用，15+ 工具暴露给 AI

### 已知限制

- **网络超时**：`deep` / `social` 命令在部分网络环境下可能遇到超时（由反爬/挑战页导致），建议：
  - 使用 `--crawl=0` 跳过页面抓取，仅获取搜索结果
  - 优先使用 `web` 命令作为替代
  - 检查网络连接或尝试切换网络环境

---

## 快速开始

### 安装

```bash
pip install -r requirements.txt
python -m playwright install chromium
python main.py --doctor
```

### 5 分钟体验

```bash
# 1. 快速查资料（忘记命令时用这个）
python main.py quick "OpenAI Agents SDK"

# 2. 多引擎搜索 + 页面摘要
python main.py web "RAG benchmark 2026" --crawl-pages=5

# 3. 深度搜索（多查询变体 + 渠道扩展）
python main.py deep "AI Agent 工程实践" --platforms --channel=news,commerce --crawl=5

# 4. 社交媒体搜索
python main.py social "iPhone 17" --platform=xiaohongshu --platform=zhihu

# 5. 电商搜索
python main.py shopping "羽绒服 轻量" --platform=taobao --platform=jd

# 6. 学术搜索（带引用格式）
python main.py academic "RAG evaluation" --papers-only --source=arxiv --source=semantic_scholar
```

---

## MCP 集成（Claude Code 即装即用）

### 自动安装

```bash
# Windows
scripts\windows\setup-claude-mcp.bat

# macOS / Linux
chmod +x scripts/unix/setup-claude-mcp.sh
./scripts/unix/setup-claude-mcp.sh
```

### 手动配置

在 Claude 配置文件（`%APPDATA%\Claude\config.json`）中添加：

```json
{
  "mcpServers": {
    "web-rooter": {
      "command": "python",
      "args": ["main.py", "--mcp"],
      "cwd": "/path/to/web-rooter",
      "env": {
        "PYTHONUNBUFFERED": "1",
        "PYTHONIOENCODING": "utf-8"
      }
    }
  }
}
```

### MCP 工具清单

| 工具 | 用途 |
|------|------|
| `web_search_internet` | 多引擎互联网搜索 |
| `web_research` | 主题深度研究 |
| `web_search_academic` | 学术文献搜索 |
| `web_search_social` | 社交媒体搜索 |
| `web_search_commerce` | 电商/本地生活搜索 |
| `web_fetch` / `web_fetch_js` | HTTP / 浏览器页面获取 |
| `web_crawl` | 站点深度爬取 |
| `web_extract` | 目标信息提取 |

---

## 安装与配置（按系统）

### Windows

- 一键基础安装：`install.bat`
- 安装全局 `wr` 命令：`scripts\windows\install-system-cli.bat`
- Claude MCP 安装：`scripts\windows\setup-claude-mcp.bat`

### macOS / Linux

```bash
chmod +x scripts/unix/*.sh
./scripts/unix/install-system-cli.sh
./scripts/unix/setup-claude-mcp.sh
```

---

## 目录总览

```
web-rooter/
├── main.py                 # CLI/MCP/HTTP 总入口
├── agents/                 # 编排层（visit/search/research/crawl）
│   └── web_agent.py
├── core/                   # 搜索、爬虫、浏览器、解析核心
│   ├── crawler.py          # HTTP 抓取
│   ├── browser.py          # Playwright 浏览器
│   ├── search/             # 搜索引擎
│   │   ├── engine_base.py
│   │   ├── advanced.py
│   │   └── universal_parser.py
│   ├── academic_search.py  # 学术搜索
│   └── citation.py         # 引用生成
├── tools/                  # MCP 工具适配
│   └── mcp_tools.py
├── scripts/                # 跨平台安装与集成脚本
│   ├── windows/
│   └── unix/
├── docs/                   # 当前有效文档
│   ├── guide/              # 使用指南
│   ├── reference/          # API 参考
│   └── architecture/       # 架构文档
├── tests/                  # 自动化测试
└── temp/                   # 参考项目快照（非运行时依赖）
```

---

## 文档导航

| 文档 | 内容 |
|------|------|
| [docs/README.md](./docs/README.md) | 文档总览 |
| [docs/guide/INSTALLATION.md](./docs/guide/INSTALLATION.md) | 详细安装指南 |
| [docs/guide/CONFIGURATION.md](./docs/guide/CONFIGURATION.md) | 配置说明 |
| [docs/guide/CLI.md](./docs/guide/CLI.md) | CLI 完整命令参考 |
| [docs/guide/MCP.md](./docs/guide/MCP.md) | MCP 集成指南 |
| [docs/reference/MCP_TOOLS.md](./docs/reference/MCP_TOOLS.md) | MCP 工具详细说明 |
| [docs/architecture/PROJECT_STRUCTURE.md](./docs/architecture/PROJECT_STRUCTURE.md) | 项目架构设计 |

---

## 开源参考与致谢

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

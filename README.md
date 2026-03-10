<div align="center">
  <img src="./LOGO.png" alt="Web-Rooter Logo" width="240" />
  <h1>Web-Rooter</h1>
  <p><strong>面向 AI Agent 的「搜索 + 深度爬取 + 引用溯源」基础设施</strong></p>
  <p>为 Claude Code、Cursor 等 AI 编程助手提供可验证的互联网信息获取能力</p>

  <p>
    <a href="./LICENSE"><img src="https://img.shields.io/badge/license-MIT-green.svg" alt="License MIT"></a>
    <img src="https://img.shields.io/badge/python-3.10%2B-blue.svg" alt="Python 3.10+">
    <img src="https://img.shields.io/badge/platform-Windows%20%7C%20macOS%20%7C%20Linux-black.svg" alt="Platforms">
    <img src="https://img.shields.io/badge/interface-CLI%20%7C%20MCP%20%7C%20HTTP-orange.svg" alt="Interfaces">
    <img src="https://img.shields.io/badge/playwright-✓-brightgreen.svg" alt="Playwright">
  </p>

  <p>
    <a href="./README.zh-CN.md">简体中文</a> |
    <a href="./README.en.md">English</a>
  </p>
</div>

---

## 为什么需要 Web-Rooter？

AI 编程助手在解决实际问题时，常常面临以下痛点：

| 痛点 | Web-Rooter 解决方案 |
|------|---------------------|
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
8. **挑战页工作流路由** - 内置 `cloudflare_interstitial` / `cloudflare_turnstile` / `frame_checkbox`，支持 JSON 自定义 profile
9. **MindSearch 图研究增强** - 产出 `mindsearch_compat`（`node`/`adjacency_list`/`ref2url`）兼容结构，便于外层 AI 推理
10. **可插拔扩展接口** - 支持 `postprocessors`（结果后处理）与 `planners`（研究规划器）热加载

---

## 5 分钟快速体验

### 安装

```bash
pip install -r requirements.txt
python -m playwright install chromium
python main.py --doctor
```

### 典型工作流

```bash
# 1. 快速查资料（忘记命令时用这个）
python main.py quick "OpenAI Agents SDK 最佳实践"

# 2. 多引擎搜索 + 自动抓取
python main.py web "RAG 评估基准 2025" --crawl-pages=5

# 3. 深度研究（多查询变体 + 渠道扩展）
python main.py deep "AI Agent 工程化" --variants=4 --crawl=5 --platforms --channel=news

# 4. 社交媒体舆情
python main.py social "iPhone 17 评测" --platform=xiaohongshu --platform=zhihu

# 5. 学术研究（带引用格式）
python main.py academic "RAG evaluation" --papers-only --source=arxiv --source=semantic_scholar

# 6. MindSearch 图研究（可切换 planner）
python main.py mindsearch "多模态大模型 工程化落地" --turns=3 --branches=4 --planner=heuristic --strict-expand --channel=news,platforms

# 7. 站点定向爬取
python main.py crawl "https://docs.python.org/3/" 20 2 --pattern="/3/library/" --no-subdomains

# 8. 查看扩展与挑战页路由（不需要记住内部细节）
python main.py planners
python main.py challenge-profiles
python main.py context --limit=20
```

---

## 输出示例

### 深度搜索输出结构

```json
{
  "query": "AI Agent 工程实践",
  "total_results": 42,
  "citations": [
    {
      "id": "P1",
      "title": "Building Effective AI Agents",
      "url": "https://www.anthropic.com/research/building-effective-agents",
      "source": "anthropic",
      "corroborated": true,
      "corroborated_by": ["P3", "P7"]
    }
  ],
  "references_text": "参考文献 / References:\n[P1] Building Effective AI Agents (anthropic) https://...\n[P3] AI Agent Patterns 2025 (github) https://...",
  "comparison": {
    "total_results": 42,
    "corroborated_results": 11,
    "domain_coverage": 17,
    "engines_used": ["google", "bing", "duckduckgo"]
  },
  "crawled_content": [
    {
      "url": "https://...",
      "title": "...",
      "content": "...",
      "citation_id": "P1"
    }
  ]
}
```

### 学术搜索输出

```json
{
  "query": "RAG evaluation",
  "papers": [
    {
      "id": "S1",
      "title": "Retrieval-Augmented Generation for Knowledge-Intensive NLP",
      "authors": ["Lewis et al."],
      "venue": "NeurIPS 2020",
      "url": "https://arxiv.org/abs/2005.11401",
      "source": "arxiv"
    }
  ],
  "references_text": "学术论文 / Papers:\n[S1] Lewis et al. Retrieval-Augmented Generation... (NeurIPS 2020) https://..."
}
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

在 Claude 配置文件中添加：

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
| `web_mindsearch` | MindSearch 图研究 |
| `web_search_social` | 社交媒体搜索 |
| `web_search_commerce` | 电商/本地生活搜索 |
| `web_fetch` / `web_fetch_js` | HTTP / 浏览器页面获取 |
| `web_crawl` | 站点深度爬取 |
| `web_extract` | 目标信息提取 |
| `web_context_snapshot` | 查看全局深度抓取上下文事件 |
| `web_postprocessors` / `web_planners` | 加载后处理器 / 研究规划器扩展 |
| `web_challenge_profiles` | 查看挑战页 workflow 路由档案 |

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
├── tools/
│   └── mcp_tools.py        # MCP 协议适配
├── scripts/                # 跨平台安装脚本
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

# Web-Rooter - AI Web Crawling Agent

一个专为 AI 设计的网页访问和爬虫系统，让 AI 可以自主访问网页、提取信息、爬取网站。

## 项目结构

```
Web-Rooter/
├── core/                  # 核心模块
│   ├── crawler.py        # 异步网页爬虫
│   ├── parser.py         # HTML 解析器
│   ├── browser.py        # 浏览器自动化（Playwright）
│   ├── search_engine.py  # 多搜索引擎模块
│   ├── academic_search.py # 学术搜索模块（新增）
│   └── form_search.py    # 表单填写搜索模块（新增）
├── agents/               # AI Agents
│   └── web_agent.py      # Web Agent（自然语言接口）
├── tools/                # MCP 工具
│   └── mcp_tools.py      # MCP 工具定义
├── config.py             # 配置
├── main.py               # 主入口
├── server.py             # HTTP API 服务器
├── demo.py               # 演示脚本
├── search_demo.py        # 搜索功能演示（新增）
├── test.py               # 测试脚本
└── requirements.txt      # 依赖
```

## 快速开始

### 安装

**Windows:**
```bash
# 运行安装脚本
install.bat
```

**手动安装:**
```bash
pip install -r requirements.txt
playwright install chromium
```

### 使用

**1. 演示模式（快速测试）**
```bash
python demo.py
```

**2. 交互模式**
```bash
python main.py
```

可用命令：
- `visit <url>` - 访问网页
- `visit <url> --js` - 使用浏览器（支持 JavaScript）
- `search <query>` - 搜索信息
- `extract <url> <target>` - 提取特定信息
- `crawl <url> [pages] [depth]` - 爬取网站
- `links <url>` - 获取链接
- `kb` - 查看知识库
- `web <query>` - 互联网搜索（多引擎）
- `research <topic>` - 深度研究主题
- `academic <query>` - 学术搜索（论文/代码，新增）
- `site <url> <query>` - 站内搜索（新增）

**3. MCP 模式（AI 集成）**
```bash
python main.py --mcp
```

**4. HTTP API**
```bash
python main.py --server
```

## Python API

```python
import asyncio
from agents.web_agent import WebAgent

async def main():
    async with WebAgent() as agent:
        # 访问网页
        result = await agent.visit("https://example.com")
        print(f"标题：{result.data['title']}")

        # 搜索信息
        search = await agent.search("example")
        print(search.content)

        # 提取信息
        extract = await agent.extract(
            "https://example.com",
            "网站用途"
        )
        print(extract.content)

        # 爬取网站
        crawl = await agent.crawl(
            "https://example.com",
            max_pages=10,
            max_depth=3
        )

        # 获取知识库
        kb = agent.get_knowledge_base()
        for page in kb:
            print(f"- {page['title']}")

        # === 互联网搜索功能 ===

        # 多引擎搜索
        search_result = await agent.search_internet(
            "AI 大模型 2025 最新进展",
            num_results=10,
            auto_crawl=True,
        )
        print(search_result.content)

        # 搜索并获取内容
        fetch_result = await agent.search_and_fetch(
            "机器学习入门",
            num_results=5,
        )

        # 深度研究主题
        research = await agent.research_topic(
            "Transformer 架构原理",
            max_searches=3,
            max_pages=10,
        )
        print(research.content)

        # === 学术模式搜索（新增）===

        # 学术搜索（论文 + 代码）
        academic = await agent.search_academic(
            "Transformer architecture",
            include_code=True,
            fetch_abstracts=True,
        )
        print(academic.content)

        # 站内搜索（填表搜索）
        site_result = await agent.search_with_form(
            "https://github.com",
            "machine learning framework",
        )
        print(site_result.content)

asyncio.run(main())
```

## MCP 工具

安装后，AI 可以使用以下工具：

| 工具 | 描述 |
|------|------|
| `web_fetch` | 获取网页内容 |
| `web_fetch_js` | 使用浏览器获取（支持 JS） |
| `web_search` | 在已访问内容中搜索 |
| `web_search_internet` | 互联网搜索（多引擎） |
| `web_search_combined` | 互联网搜索 + 爬取内容 |
| `web_research` | 深度研究主题 |
| `web_search_academic` | 学术搜索（论文/代码项目，新增） |
| `web_search_site` | 站内搜索（填表搜索，新增） |
| `web_extract` | 提取特定信息 |
| `web_crawl` | 爬取网站 |
| `parse_html` | 解析 HTML |
| `get_links` | 获取页面链接 |

### Claude Code 配置

在 Claude Code 配置中添加：

```json
{
  "mcpServers": {
    "web-rooter": {
      "command": "python",
      "args": ["main.py", "--mcp"],
      "cwd": "C:\\Users\\rukel\\Desktop\\Web-Rooter"
    }
  }
}
```

## 功能特性

- 异步网页爬取
- JavaScript 渲染支持（通过 Playwright）
- HTML 智能解析
- 结构化数据提取（JSON-LD）
- 自然语言搜索
- 网站深度爬取
- 请求限流和重试
- MCP 工具集成
- **多搜索引擎支持（Bing、Google、百度、DuckDuckGo、搜狗、Google Scholar）**
- **智能引擎选择（根据查询语言和内容自动选择）**
- **搜索结果去重和合并**
- **搜索 + 爬取组合功能**
- **学术模式搜索（arXiv、Google Scholar、PubMed、IEEE、CNKI、GitHub、Gitee）**
- **论文摘要自动爬取**
- **表单自动填写和站内搜索**

## HTTP API 端点

| 端点 | 方法 | 描述 |
|------|------|------|
| `/fetch` | POST | 获取网页 |
| `/search` | POST | 在已访问页面搜索 |
| `/search/internet` | POST | 互联网搜索（多引擎） |
| `/search/combined` | POST | 互联网搜索 + 爬取 |
| `/search/academic` | POST | 学术搜索（新增） |
| `/search/site` | POST | 站内搜索（新增） |
| `/research` | POST | 深度研究主题 |
| `/extract` | POST | 提取信息 |
| `/crawl` | POST | 爬取网站 |
| `/links` | GET | 获取链接 |
| `/knowledge` | GET | 获取知识库 |
| `/parse` | POST | 解析 HTML |

## 配置

在 `.env` 文件中配置：

```ini
# 爬虫配置
CRAWLER_TIMEOUT=30
CRAWLER_MAX_RETRIES=3
CRAWLER_USER_AGENT=Mozilla/5.0...

# 浏览器配置
BROWSER_HEADLESS=true
BROWSER_TIMEOUT=30000

# 服务器配置
SERVER_HOST=127.0.0.1
SERVER_PORT=8765
```

## 依赖

- **aiohttp**: 异步 HTTP 客户端
- **beautifulsoup4**: HTML 解析
- **playwright**: 浏览器自动化
- **fastapi**: HTTP API 服务器
- **mcp**: MCP SDK

## 许可证

MIT License

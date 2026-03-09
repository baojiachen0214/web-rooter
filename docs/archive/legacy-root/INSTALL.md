# Web-Rooter 安装指南

## 快速安装

### 1. 安装依赖

```bash
cd /path/to/web-rooter
pip install -r requirements.txt
```

### 2. 安装 Playwright 浏览器（可选，用于 JavaScript 渲染页面）

```bash
playwright install chromium
```

### 3. 验证安装

```bash
python demo.py
```

## 使用方式

### 方式一：命令行交互模式

```bash
python main.py
```

可用命令：
- `visit <url>` - 访问网页
- `visit <url> --js` - 使用浏览器访问（支持 JavaScript）
- `search <query>` - 搜索信息
- `extract <url> <target>` - 提取特定信息
- `crawl <url> [pages] [depth]` - 爬取网站
- `links <url>` - 获取链接
- `kb` - 查看知识库
- `help` - 帮助
- `exit` - 退出

### 方式二：MCP 服务器（推荐用于 AI 集成）

```bash
python main.py --mcp
```

### 方式三：HTTP API

```bash
python main.py --server
```

API 端点：
- `POST /fetch` - 获取网页
- `POST /search` - 搜索信息
- `POST /extract` - 提取信息
- `POST /crawl` - 爬取网站
- `GET /links?url=` - 获取链接

### 方式四：Python 代码

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

asyncio.run(main())
```

## 工具列表（AI 可用）

| 工具名 | 描述 | 参数 |
|--------|------|------|
| `web_fetch` | 获取网页内容 | url |
| `web_fetch_js` | 使用浏览器获取（支持 JS） | url, wait_for |
| `web_search` | 在内容中搜索 | query, url |
| `web_extract` | 提取特定信息 | url, target |
| `web_crawl` | 爬取网站 | start_url, max_pages, max_depth |
| `parse_html` | 解析 HTML | html, url |
| `get_links` | 获取页面链接 | url, internal_only |

## 配置 MCP

在 Claude Code 配置中添加：

```json
{
  "mcpServers": {
    "web-rooter": {
      "command": "python",
      "args": ["main.py", "--mcp"],
      "cwd": "/path/to/web-rooter"
    }
  }
}
```

或者使用项目中的配置文件：
```bash
# 复制配置文件到 Claude Code 配置目录
copy claude-code-mcp.json %APPDATA%\Code\User\globalStorage\anthropic.claude-code\claude_descriptors\
```

## 示例

### Python 示例

```python
from agents.web_agent import WebAgent
import asyncio

async def demo():
    async with WebAgent() as agent:
        # 访问多个网页
        urls = [
            "https://example.com",
            "https://example.org"
        ]
        for url in urls:
            result = await agent.visit(url)
            print(f"访问：{result.data['title']}")

        # 搜索信息
        search = await agent.search("domain")
        print(search.content)

        # 提取信息
        extract = await agent.extract("https://example.com", "网站用途")
        print(extract.content)

        # 爬取网站
        crawl = await agent.crawl("https://example.com", max_pages=5)
        print(f"爬取了 {len(crawl.urls)} 个页面")

asyncio.run(demo())
```

### 命令行示例

```bash
# 交互模式
python main.py

# 直接命令
python main.py visit https://example.com
python main.py search "关键词"
python main.py extract https://example.com "网站标题"
python main.py crawl https://example.com 5 2
```

## 故障排除

### Playwright 浏览器问题

如果遇到浏览器相关错误：

```bash
# 重新安装浏览器
playwright install chromium --force
```

### 编码问题

Windows 系统可能需要设置 UTF-8 编码：

```bash
set PYTHONIOENCODING=utf-8
python main.py
```

### 依赖问题

```bash
# 升级 pip
python -m pip install --upgrade pip

# 重新安装依赖
pip install -r requirements.txt --force-reinstall
```

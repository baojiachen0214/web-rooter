# Web-Rooter Agent API 文档

> 本文档面向 AI Agent 调用者，展示可用的功能函数和调用方式。

---

## Agent 功能概览

Web-Rooter 提供以下 **AI Agent 功能函数**，可通过 MCP 工具或 Python API 调用：

| 功能类别 | 函数名 | 描述 | 返回类型 |
|----------|--------|------|----------|
| **网页访问** | `visit(url)` | 访问网页并提取内容 | `AgentResponse` |
| **网页访问** | `visit_js(url)` | 使用浏览器访问（支持 JavaScript） | `AgentResponse` |
| **信息搜索** | `search(query)` | 在已访问页面中搜索 | `AgentResponse` |
| **信息搜索** | `search_internet(query)` | 互联网多引擎搜索 | `AgentResponse` |
| **信息搜索** | `search_and_fetch(query)` | 搜索并获取详细内容 | `AgentResponse` |
| **深度研究** | `research_topic(topic)` | 深度研究主题（多轮搜索 + 爬取） | `AgentResponse` |
| **学术搜索** | `search_academic(query)` | 搜索论文和代码项目 | `AgentResponse` |
| **站内搜索** | `search_with_form(url, query)` | 使用网站内部搜索表单 | `AgentResponse` |
| **信息提取** | `extract(url, target)` | 从网页提取特定信息 | `AgentResponse` |
| **网站爬取** | `crawl(url, max_pages, max_depth)` | 爬取整个网站 | `AgentResponse` |
| **知识管理** | `get_knowledge_base()` | 获取已访问页面的知识库 | `List[PageKnowledge]` |
| **知识管理** | `get_visited_urls()` | 获取已访问 URL 列表 | `List[str]` |

---

## Python API 调用示例

### 初始化 Agent

```python
import asyncio
from agents.web_agent import WebAgent

async with WebAgent() as agent:
    # 调用各种功能...
    pass
```

---

## 功能函数详解

### 1. visit(url) - 访问网页

**用途**: 访问单个网页，提取标题、正文、链接等信息。

**参数**:
- `url` (str): 目标 URL
- `use_browser` (bool): 是否使用浏览器（默认 False，用于 JavaScript 渲染页面）

**返回**: `AgentResponse`
```python
result = await agent.visit("https://example.com")
print(result.data['title'])      # 页面标题
print(result.data['text'][:500]) # 正文前 500 字
print(result.data['links'])      # 链接列表
```

**Agent 行为**:
- 自动提取页面结构化数据
- 缓存到知识库供后续搜索
- 返回摘要信息

---

### 2. search(query) - 页面内搜索

**用途**: 在已访问的页面内容中搜索关键词。

**参数**:
- `query` (str): 搜索关键词

**返回**: `AgentResponse`
```python
result = await agent.search("AI 技术")
print(result.content)  # 匹配的摘要内容
```

**Agent 行为**:
- 在知识库中全文搜索
- 返回最相关的片段
- 标注来源 URL

---

### 3. search_internet(query) - 互联网搜索

**用途**: 调用多个搜索引擎进行互联网搜索。

**参数**:
- `query` (str): 搜索关键词
- `num_results` (int): 结果数量（默认 10）
- `auto_crawl` (bool): 是否自动爬取搜索结果（默认 True）

**返回**: `AgentResponse`
```python
result = await agent.search_internet(
    "AI 大模型 2025 最新进展",
    num_results=10,
    auto_crawl=True
)
print(result.content)  # 整合的搜索结果
```

**支持的搜索引擎**:
- Bing（默认）
- Google
- 百度（中文查询）
- DuckDuckGo
- 搜狗

**Agent 行为**:
- 智能选择搜索引擎
- 多引擎并行搜索
- 结果去重合并
- 可选爬取 top 结果

---

### 4. research_topic(topic) - 深度研究

**用途**: 对复杂主题进行多轮搜索和深度爬取。

**参数**:
- `topic` (str): 研究主题
- `max_searches` (int): 最大搜索次数（默认 3）
- `max_pages` (int): 最大爬取页面数（默认 10）

**返回**: `AgentResponse`
```python
result = await agent.research_topic(
    "Transformer 架构原理",
    max_searches=3,
    max_pages=10
)
print(result.content)  # 综合研究报告
```

**Agent 行为**:
- 多轮迭代搜索
- 自动爬取相关内容
- 整合多源信息
- 生成结构化报告

---

### 5. search_academic(query) - 学术搜索

**用途**: 搜索学术论文和代码项目。

**参数**:
- `query` (str): 搜索关键词
- `include_code` (bool): 是否包含代码项目（默认 True）
- `fetch_abstracts` (bool): 是否获取论文摘要（默认 True）

**返回**: `AgentResponse`
```python
result = await agent.search_academic(
    "Transformer architecture",
    include_code=True,
    fetch_abstracts=True
)
print(result.content)  # 论文和代码项目列表
```

**支持的学术来源**:
- arXiv（预印本论文）
- Google Scholar
- PubMed（生物医学）
- IEEE Xplore
- CNKI（中文论文）
- GitHub（代码项目）
- Gitee（中文代码）

**Agent 行为**:
- 自动识别学术查询
- 多来源并行搜索
- 自动获取摘要
- 整合论文和代码

---

### 6. search_with_form(url, query) - 站内搜索

**用途**: 使用网站内部的搜索表单进行搜索。

**参数**:
- `url` (str): 网站 URL
- `query` (str): 搜索关键词

**返回**: `AgentResponse`
```python
result = await agent.search_with_form(
    "https://github.com",
    "machine learning framework"
)
print(result.content)  # 站内搜索结果
```

**Agent 行为**:
- 自动检测搜索表单
- 智能填写并提交
- 解析搜索结果

---

### 7. extract(url, target) - 信息提取

**用途**: 从指定网页提取特定类型的信息。

**参数**:
- `url` (str): 目标 URL
- `target` (str): 要提取的信息描述

**返回**: `AgentResponse`
```python
result = await agent.extract(
    "https://example.com/product",
    "产品名称、价格、库存状态"
)
print(result.content)  # 提取的结构化信息
```

**Agent 行为**:
- 智能定位相关区域
- 提取结构化数据
- 返回格式化结果

---

### 8. crawl(url, max_pages, max_depth) - 网站爬取

**用途**: 爬取整个网站的多层页面。

**参数**:
- `url` (str): 起始 URL
- `max_pages` (int): 最大页面数（默认 100）
- `max_depth` (int): 最大深度（默认 3）

**返回**: `AgentResponse`
```python
result = await agent.crawl(
    "https://example.com",
    max_pages=50,
    max_depth=3
)
print(f"爬取了 {len(result.data['pages'])} 个页面")
```

**Agent 行为**:
- 广度优先爬取
- 自动去重
- 域限制
- 结构化存储

---

### 9. get_knowledge_base() - 获取知识库

**用途**: 获取所有已访问页面的知识库。

**返回**: `List[PageKnowledge]`
```python
kb = agent.get_knowledge_base()
for page in kb:
    print(f"- {page['title']}: {page['url']}")
```

**PageKnowledge 结构**:
```python
{
    "url": str,
    "title": str,
    "content": str,
    "links": List[str],
    "visited_at": datetime,
}
```

---

### 10. get_visited_urls() - 获取访问历史

**用途**: 获取所有已访问的 URL 列表。

**返回**: `List[str]`
```python
urls = agent.get_visited_urls()
print(f"共访问 {len(urls)} 个 URL")
```

---

## MCP 工具调用

Web-Rooter 作为 MCP Server 时，提供以下工具：

```json
{
  "name": "web_fetch",
  "description": "Fetch webpage content"
}
{
  "name": "web_fetch_js",
  "description": "Fetch with browser (JavaScript support)"
}
{
  "name": "web_search",
  "description": "Search in visited pages"
}
{
  "name": "web_search_internet",
  "description": "Internet search across multiple engines"
}
{
  "name": "web_search_combined",
  "description": "Internet search + crawl top results"
}
{
  "name": "web_research",
  "description": "Deep research on a topic"
}
{
  "name": "web_search_academic",
  "description": "Academic search (papers + code projects)"
}
{
  "name": "web_search_site",
  "description": "Site search using internal form"
}
{
  "name": "web_extract",
  "description": "Extract specific information"
}
{
  "name": "web_crawl",
  "description": "Crawl a website"
}
{
  "name": "parse_html",
  "description": "Parse HTML content"
}
{
  "name": "get_links",
  "description": "Get page links"
}
```

---

## Spider 爬虫 API（高级用法）

对于需要自定义爬取逻辑的场景，可以使用 Spider 框架：

### 创建自定义 Spider

```python
from agents.spider import Spider

class MySpider(Spider):
    name = "myspider"
    start_urls = ["https://example.com"]

    async def parse(self, response):
        # 提取数据
        data = {
            "title": response.get_title(),
            "content": response.get_text(),
        }
        yield data

        # 跟随链接
        for link in response.get_links():
            yield response.follow(link["href"], callback="parse")

# 运行
spider = MySpider()
stats = await spider.run()
```

### 流式输出

```python
async with spider.stream() as stream:
    async for item in stream:
        print(f"实时数据：{item.data}")
```

---

## 错误处理

所有 Agent 方法返回 `AgentResponse`，包含：

```python
@dataclass
class AgentResponse:
    success: bool      # 是否成功
    data: Any          # 返回数据
    content: str       # 文本内容
    error: str         # 错误信息
    metadata: dict     # 元数据
```

**使用建议**:
```python
result = await agent.search_internet("query")
if result.success:
    print(result.content)
else:
    print(f"错误：{result.error}")
```

---

## 配置选项

在 `.env` 文件中配置：

```ini
# 爬虫配置
CRAWLER_TIMEOUT=30
CRAWLER_MAX_RETRIES=3
CRAWLER_USER_AGENT=Mozilla/5.0...

# 缓存配置
CACHE_TTL=3600
CACHE_ENABLED=true

# 性能配置
MAX_CONCURRENT=10
REQUEST_DELAY=0.5
```

---

## 最佳实践

1. **搜索优先**: 先用 `search_internet` 获取信息，再针对性爬取
2. **批量操作**: 使用 `crawl` 而非多次 `visit`
3. **知识复用**: 访问过的页面会被缓存，可重复搜索
4. **深度研究**: 复杂主题使用 `research_topic` 而非单次搜索
5. **错误处理**: 始终检查 `AgentResponse.success`

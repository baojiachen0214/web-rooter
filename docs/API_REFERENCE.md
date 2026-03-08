# Web-Rooter API 参考文档

**版本**: v2.1
**更新日期**: 2026-03-08

---

## 一、快速参考

### MCP 工具列表

| 工具 | 用途 | 关键参数 |
|------|------|----------|
| `web_fetch` | 获取网页 | `url` |
| `web_fetch_js` | 浏览器获取 | `url`, `wait_for` |
| `web_search` | 页面内搜索 | `query`, `url` |
| `web_search_internet` | 互联网搜索 | `query`, `num_results` |
| `web_search_combined` | 搜索 + 爬取 | `query`, `num_results`, `crawl_top` |
| `web_research` | 深度研究 | `topic`, `max_pages` |
| `web_search_academic` | 学术搜索 | `query`, `include_code` |
| `web_search_site` | 站内搜索 | `url`, `query` |
| `web_extract` | 信息提取 | `url`, `target` |
| `web_crawl` | 网站爬取 | `start_url`, `max_pages`, `max_depth` |
| `parse_html` | HTML 解析 | `html`, `url` |
| `get_links` | 获取链接 | `url`, `internal_only` |
| `web_deep_search` | 深度搜索 | `query`, `use_english`, `crawl_top` |
| `web_search_social` | 社交媒体 | `query`, `platforms` |
| `web_search_tech` | 技术社区 | `query`, `sources` |

---

## 二、工具详细 API

### 2.1 web_fetch

获取网页内容。

**签名**:
```python
web_fetch(url: str) -> Dict[str, Any]
```

**参数**:
- `url`: 要访问的网页地址

**返回**:
```json
{
  "success": true,
  "url": "https://example.com",
  "title": "Page Title",
  "html": "<html>...",
  "text": "Page text content...",
  "links": [...],
  "error": null
}
```

**使用技巧**:
- 适用于静态 HTML 页面
- 如果返回内容为空，尝试 `web_fetch_js`
- 自动提取标题、链接和文本

**示例**:
```
web_fetch("https://www.python.org")
```

---

### 2.2 web_fetch_js

使用浏览器获取网页（支持 JavaScript 渲染）。

**签名**:
```python
web_fetch_js(url: str, wait_for: Optional[str] = None) -> Dict[str, Any]
```

**参数**:
- `url`: 要访问的网页地址
- `wait_for`: CSS 选择器，等待该元素出现后返回

**返回**:
```json
{
  "success": true,
  "url": "https://example.com",
  "title": "Page Title",
  "html": "<html>...",
  "error": null
}
```

**使用技巧**:
- 适用于 SPA（单页应用）
- 适用于需要登录的页面
- `wait_for` 可以确保内容加载完成
- 比普通 fetch 慢 3-5 倍

**示例**:
```
web_fetch_js("https://twitter.com", wait_for="[data-testid='tweet']")
```

---

### 2.3 web_search_internet

互联网多引擎搜索。

**签名**:
```python
web_search_internet(query: str, num_results: int = 10) -> Dict[str, Any]
```

**参数**:
- `query`: 搜索关键词
- `num_results`: 结果数量（默认 10）

**返回**:
```json
{
  "success": true,
  "results": [
    {
      "title": "Result Title",
      "url": "https://...",
      "snippet": "摘要内容...",
      "engine": "bing"
    }
  ],
  "content": "格式化后的结果文本"
}
```

**使用技巧**:
- 默认使用 Bing 搜索引擎
- 适合快速了解概况
- 结果包含摘要，但需要访问 URL 获取详情

**示例**:
```
web_search_internet("Python 量化交易框架", num_results=10)
```

---

### 2.4 web_search_combined

互联网搜索并爬取前 N 个结果。

**签名**:
```python
web_search_combined(
    query: str,
    num_results: int = 20,
    crawl_top: int = 3
) -> Dict[str, Any]
```

**参数**:
- `query`: 搜索关键词
- `num_results`: 搜索结果数量（默认 20）
- `crawl_top`: 爬取前 N 个结果（默认 3）

**返回**:
```json
{
  "success": true,
  "results": [...],
  "crawled_content": [
    {
      "url": "https://...",
      "title": "...",
      "content": "完整页面内容..."
    }
  ]
}
```

**使用技巧**:
- 推荐作为默认搜索工具
- 爬取内容可以获取更详细信息
- 爬取会增加耗时，但结果更丰富

**示例**:
```
web_search_combined("AI 大模型", num_results=20, crawl_top=5)
```

---

### 2.5 web_deep_search

深度搜索（多引擎并行，支持中英文）。

**签名**:
```python
web_deep_search(
    query: str,
    num_results: int = 20,
    use_english: bool = True,
    crawl_top: int = 5
) -> Dict[str, Any]
```

**参数**:
- `query`: 搜索关键词
- `num_results`: 每个引擎的结果数量（默认 20）
- `use_english`: 是否同时使用英文搜索（默认 true）
- `crawl_top`: 爬取前 N 个结果（默认 5）

**返回**:
```json
{
  "success": true,
  "query": "AI 人工智能",
  "total_results": 50,
  "results": [...],
  "crawled_content": [...],
  "search_summary": "使用 4 个引擎搜索，共找到 50 条结果"
}
```

**使用技巧**:
- 并行使用 Google、Bing、Baidu、DuckDuckGo
- `use_english=True` 时会自动添加英文关键词
- 适合需要全面信息的任务
- 结果自动去重

**示例**:
```
web_deep_search("machine learning tutorial", use_english=True, crawl_top=10)
```

---

### 2.6 web_search_social

社交媒体搜索。

**签名**:
```python
web_search_social(
    query: str,
    platforms: Optional[List[str]] = None
) -> Dict[str, Any]
```

**参数**:
- `query`: 搜索关键词
- `platforms`: 指定平台列表（默认全部）
  - `bilibili` - B 站
  - `zhihu` - 知乎
  - `weibo` - 微博
  - `reddit` - Reddit
  - `twitter` - Twitter

**返回**:
```json
{
  "success": true,
  "query": "iPhone 17",
  "total_results": 20,
  "results": [...]
}
```

**使用技巧**:
- 获取真实用户评价
- 了解舆情和口碑
- 多平台组合使用

**示例**:
```
web_search_social("iPhone 17 评价", platforms=["zhihu", "bilibili"])
```

---

### 2.7 web_search_tech

技术社区搜索。

**签名**:
```python
web_search_tech(
    query: str,
    sources: Optional[List[str]] = None
) -> Dict[str, Any]
```

**参数**:
- `query`: 搜索关键词
- `sources`: 指定来源列表（默认全部）
  - `github` - GitHub 项目
  - `stackoverflow` - Stack Overflow
  - `medium` - Medium 文章
  - `hackernews` - Hacker News

**返回**:
```json
{
  "success": true,
  "query": "python web framework",
  "total_results": 15,
  "results": [...]
}
```

**使用技巧**:
- 技术内容默认使用英文搜索
- 寻找开源项目用 `github`
- 解决技术问题用 `stackoverflow`

**示例**:
```
web_search_tech("python web framework", sources=["github", "stackoverflow"])
```

---

### 2.8 web_search_academic

学术搜索。

**签名**:
```python
web_search_academic(
    query: str,
    num_results: int = 10,
    include_code: bool = True,
    fetch_abstracts: bool = True
) -> Dict[str, Any]
```

**参数**:
- `query`: 搜索关键词
- `num_results`: 结果数量（默认 10）
- `include_code`: 是否包含代码项目（默认 true）
- `fetch_abstracts`: 是否获取论文摘要（默认 true）

**返回**:
```json
{
  "success": true,
  "papers": [...],
  "code_projects": [...]
}
```

**使用技巧**:
- 适合学术研究任务
- `include_code=True` 同时搜索代码实现
- 技术主题建议用英文查询

**示例**:
```
web_search_academic("transformer attention mechanism", include_code=True)
```

---

### 2.9 web_research

深度研究。

**签名**:
```python
web_research(topic: str, max_pages: int = 10) -> Dict[str, Any]
```

**参数**:
- `topic`: 研究主题
- `max_pages`: 最大爬取页面数（默认 10）

**返回**:
```json
{
  "success": true,
  "content": "综合研究报告...",
  "data": {
    "sources": [...],
    "pages_crawled": 10
  }
}
```

**使用技巧**:
- 多轮迭代搜索
- 自动分析和综合
- 适合复杂研究任务
- 耗时较长但结果最全面

**示例**:
```
web_research("量子计算发展现状", max_pages=15)
```

---

### 2.10 web_search_site

站内搜索。

**签名**:
```python
web_search_site(
    url: str,
    query: str,
    use_browser: bool = True
) -> Dict[str, Any]
```

**参数**:
- `url`: 网站地址
- `query`: 搜索关键词
- `use_browser`: 是否使用浏览器（默认 true）

**返回**:
```json
{
  "success": true,
  "content": "搜索结果..."
}
```

**使用技巧**:
- 在特定网站内搜索
- 适合大型网站（GitHub、知乎等）
- `use_browser=True` 处理 JavaScript 表单

**示例**:
```
web_search_site("https://github.com", "machine learning python")
```

---

### 2.11 web_extract

信息提取。

**签名**:
```python
web_extract(url: str, target: str) -> Dict[str, Any]
```

**参数**:
- `url`: 目标网页
- `target`: 要提取的信息描述

**返回**:
```json
{
  "success": true,
  "content": "提取的结构化信息..."
}
```

**使用技巧**:
- 用自然语言描述要提取的内容
- 适合提取价格、规格、评价等
- 自动识别和结构化

**示例**:
```
web_extract("https://example.com/product", "产品名称、价格、库存状态、用户评分")
```

---

### 2.12 web_crawl

网站爬取。

**签名**:
```python
web_crawl(
    start_url: str,
    max_pages: int = 10,
    max_depth: int = 3
) -> Dict[str, Any]
```

**参数**:
- `start_url`: 起始 URL
- `max_pages`: 最大页面数（默认 10）
- `max_depth`: 最大深度（默认 3）

**返回**:
```json
{
  "success": true,
  "pages": [
    {
      "url": "https://...",
      "title": "...",
      "content": "..."
    }
  ]
}
```

**使用技巧**:
- 自动追踪链接
- 适合获取整个网站内容
- 合理设置 `max_pages` 和 `max_depth`

**示例**:
```
web_crawl("https://blog.example.com", max_pages=50, max_depth=3)
```

---

### 2.13 parse_html

解析 HTML 内容。

**签名**:
```python
parse_html(html: str, url: str = "") -> Dict[str, Any]
```

**参数**:
- `html`: HTML 字符串
- `url`: 源 URL（用于解析相对链接）

**返回**:
```json
{
  "title": "Page Title",
  "text": "Text content...",
  "links": [...],
  "metadata": {...}
}
```

**使用技巧**:
- 用于解析已获取的 HTML
- 自动提取标题、文本、链接
- 生成结构化数据

**示例**:
```
parse_html(html_content, url="https://example.com")
```

---

### 2.14 get_links

获取页面链接。

**签名**:
```python
get_links(url: str, internal_only: bool = True) -> Dict[str, Any]
```

**参数**:
- `url`: 目标 URL
- `internal_only`: 只返回内部链接（默认 true）

**返回**:
```json
{
  "success": true,
  "links": [
    {"href": "https://...", "text": "Link text"}
  ],
  "count": 50
}
```

**使用技巧**:
- 了解网站结构
- 批量获取相关页面 URL
- `internal_only=False` 获取所有外链

**示例**:
```
get_links("https://example.com", internal_only=True)
```

---

## 三、任务驱动的工具选择

### 3.1 信息发现任务

```
用户需求：不知道有什么，需要了解概况

工具选择:
1. web_search_internet - 快速了解
2. web_deep_search - 全面了解（推荐）
3. web_search_combined - 搜索 + 详情

示例流程:
web_deep_search("主题", use_english=True, crawl_top=5)
```

---

### 3.2 信息获取任务

```
用户需求：已有 URL，需要获取内容

工具选择:
1. web_fetch - 静态页面
2. web_fetch_js - 动态页面
3. web_crawl - 多页面

示例流程:
if 动态页面：
    web_fetch_js(url, wait_for=".content")
else:
    web_fetch(url)
```

---

### 3.3 信息提取任务

```
用户需求：从页面提取特定信息

工具选择:
1. web_extract - AI 提取
2. parse_html - 结构化解析

示例流程:
web_extract(url, "需要提取的信息描述")
```

---

### 3.4 深度研究任务

```
用户需求：复杂主题的综合研究

工具选择:
1. web_research - 全自动研究
2. web_deep_search + web_crawl - 手动控制

示例流程:
web_research("研究主题", max_pages=15)
```

---

## 四、最佳实践

### 4.1 搜索策略

```python
# ✅ 推荐：搜索 + 爬取组合
web_search_combined(query, num_results=20, crawl_top=5)

# ✅ 推荐：深度搜索获取全面信息
web_deep_search(query, use_english=True, crawl_top=10)

# ❌ 避免：只搜索不爬取
web_search_internet(query)  # 只有摘要
```

---

### 4.2 页面访问策略

```python
# ✅ 推荐：先尝试普通获取，失败后用 browser
result = web_fetch(url)
if not result.html or len(result.html) < 100:
    result = web_fetch_js(url, wait_for=".content")

# ❌ 避免：默认使用 browser
web_fetch_js(url)  # 慢 3-5 倍
```

---

### 4.3 多工具组合

```python
# 完整的信息收集流程
# 1. 搜索发现
search_results = web_deep_search(query, use_english=True)

# 2. 社交媒体验证
social_results = web_search_social(query)

# 3. 获取详情
for url in top_urls:
    content = web_fetch(url)

# 4. 提取关键信息
info = web_extract(url, "关键信息描述")
```

---

### 4.4 错误处理

```python
# ✅ 推荐：重试和降级策略
try:
    result = web_fetch(url)
    if not result.html:
        result = web_fetch_js(url)
except Exception as e:
    # 尝试其他方式
    result = web_search_internet(query)
```

---

## 五、性能优化建议

### 5.1 减少不必要的请求

```python
# ✅ 先搜索再爬取
results = web_search_combined(query, crawl_top=3)

# ❌ 盲目爬取
web_crawl(start_url, max_pages=100)  # 可能爬取无关内容
```

---

### 5.2 合理设置参数

```python
# ✅ 合理限制
web_crawl(url, max_pages=20, max_depth=2)
web_research(topic, max_pages=10)

# ❌ 过大参数
web_crawl(url, max_pages=1000, max_depth=10)  # 耗时长
```

---

### 5.3 利用缓存

```python
# 系统自动缓存已访问页面
# 重复访问相同 URL 会返回缓存结果
# 缓存有效期：1 小时
```

---

## 六、常见问题

### Q1: 搜索结果为空？

**解决方案**:
1. 更换关键词
2. 使用 `web_deep_search` 代替 `web_search_internet`
3. 尝试英文搜索

---

### Q2: 页面内容为空？

**解决方案**:
1. 使用 `web_fetch_js` 代替 `web_fetch`
2. 添加 `wait_for` 参数
3. 检查 URL 是否正确

---

### Q3: 爬取速度太慢？

**解决方案**:
1. 减少 `max_pages` 和 `max_depth`
2. 减少 `crawl_top` 数量
3. 优先使用搜索而非爬取

---

### Q4: 如何选择 `crawl_top`？

**建议**:
- 快速浏览：`crawl_top=0`
- 获取摘要：`crawl_top=3-5`
- 详细分析：`crawl_top=10+`

---

## 七、总结

**选择工具的核心原则**:

1. **信息发现** → `web_deep_search`（全面）
2. **获取内容** → `web_fetch` / `web_fetch_js`（根据页面类型）
3. **提取信息** → `web_extract`（AI 提取）
4. **深度研究** → `web_research`（全自动）
5. **用户评价** → `web_search_social`（社交媒体）
6. **技术内容** → `web_search_tech`（技术社区）
7. **学术论文** → `web_search_academic`（学术搜索）

记住：**没有万能工具，根据任务选择最佳组合**。

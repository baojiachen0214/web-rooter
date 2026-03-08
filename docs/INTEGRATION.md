# Web-Rooter 集成到 Claude Code 指南

## 概述

Web-Rooter 是一个功能强大的 AI Web 爬虫 Agent，可以集成到 Claude Code 中，让 AI 能够：
- 访问和爬取网页
- 搜索互联网信息
- 搜索学术论文和代码
- 深度研究主题
- 提取特定信息

---

## 快速集成

### 1. 配置 MCP Server

在 Claude Code 配置目录（通常是 `%APPDATA%\Claude\` 或 `~/.config/claude/`）中编辑配置文件，添加：

```json
{
  "mcpServers": {
    "web-rooter": {
      "command": "python",
      "args": ["main.py", "--mcp"],
      "cwd": "/path/to/web-rooter",
      "env": {
        "PYTHONUNBUFFERED": "1"
      }
    }
  }
}
```

### 2. 验证安装

在 Claude Code 中输入 `/tools` 查看可用工具，应该能看到：
- `web_fetch`
- `web_fetch_js`
- `web_search`
- `web_search_internet`
- `web_search_combined`
- `web_research`
- `web_search_academic`
- `web_search_site`
- `web_extract`
- `web_crawl`
- `parse_html`
- `get_links`

---

## 可用工具详解

### 网页访问工具

#### `web_fetch` - 获取网页内容
```
参数：url (字符串) - 要访问的网页地址
返回：网页标题、内容、链接等
```

**示例**:
```
使用 web_fetch 获取 https://example.com 的内容
```

#### `web_fetch_js` - 浏览器获取（支持 JavaScript）
```
参数：
  - url (字符串) - 要访问的网页地址
  - wait_for (可选，字符串) - CSS 选择器，等待元素出现
返回：渲染后的网页内容
```

**示例**:
```
使用 web_fetch_js 访问 https://example.com，等待 .content 元素
```

---

### 搜索工具

#### `web_search` - 在已访问页面中搜索
```
参数：
  - query (字符串) - 搜索关键词
  - url (可选，字符串) - 限制在特定 URL
返回：匹配的摘要内容
```

**示例**:
```
使用 web_search 搜索"人工智能"
```

#### `web_search_internet` - 互联网多引擎搜索
```
参数：
  - query (字符串) - 搜索关键词
  - num_results (可选，数字，默认 10) - 结果数量
返回：搜索结果列表和摘要
```

**示例**:
```
使用 web_search_internet 搜索"苹果发布会 2025 最新进展"，获取 10 个结果
```

#### `web_search_combined` - 搜索并爬取内容
```
参数：
  - query (字符串) - 搜索关键词
  - num_results (可选，数字，默认 20) - 搜索结果数量
  - crawl_top (可选，数字，默认 3) - 爬取前 N 个结果
返回：搜索结果和爬取的详细内容
```

**示例**:
```
使用 web_search_combined 搜索"机器学习入门"，爬取前 5 个结果
```

#### `web_research` - 深度研究主题
```
参数：
  - topic (字符串) - 研究主题
  - max_pages (可选，数字，默认 10) - 最大爬取页面数
返回：综合研究报告
```

**示例**:
```
使用 web_research 研究"Transformer 架构原理"
```

#### `web_search_academic` - 学术搜索
```
参数：
  - query (字符串) - 搜索关键词
  - num_results (可选，数字，默认 10) - 结果数量
  - include_code (可选，布尔，默认 true) - 是否包含代码项目
  - fetch_abstracts (可选，布尔，默认 true) - 是否获取摘要
返回：论文和代码项目列表
```

**示例**:
```
使用 web_search_academic 搜索"large language model"
```

#### `web_search_site` - 站内搜索
```
参数：
  - url (字符串) - 网站地址
  - query (字符串) - 搜索关键词
  - use_browser (可选，布尔，默认 true) - 是否使用浏览器
返回：站内搜索结果
```

**示例**:
```
使用 web_search_site 在 https://github.com 搜索"machine learning"
```

---

### 信息提取工具

#### `web_extract` - 提取特定信息
```
参数：
  - url (字符串) - 目标网页
  - target (字符串) - 要提取的信息描述
返回：提取的结构化信息
```

**示例**:
```
使用 web_extract 从 https://example.com/product 提取"产品名称、价格、库存状态"
```

#### `web_crawl` - 爬取网站
```
参数：
  - start_url (字符串) - 起始 URL
  - max_pages (可选，数字，默认 10) - 最大页面数
  - max_depth (可选，数字，默认 3) - 最大深度
返回：爬取结果
```

**示例**:
```
使用 web_crawl 爬取 https://example.com，最多 50 页，深度 3
```

---

### 工具链使用

#### 场景 1: 搜索最新新闻
```
1. web_search_internet("苹果发布会 2025")
2. web_fetch(结果中的 URL)
3. parse_html(获取的内容)
```

#### 场景 2: 研究学术主题
```
1. web_search_academic("Transformer architecture")
2. web_fetch(论文 URL)
3. web_extract(提取摘要和结论)
```

#### 场景 3: 爬取评论数据
```
1. web_search_internet("产品名 用户评价")
2. web_search_combined(搜索并爬取)
3. parse_html(整理结果)
```

---

## 实际使用示例

### 示例 1: 搜索科技新闻

**用户**: "帮我搜索最新的苹果发布会信息"

**Claude Code 操作**:
1. 调用 `web_search_internet(query="苹果发布会 2025 最新进展", num_results=10)`
2. 调用 `web_fetch(url="https://www.apple.com.cn/...")` 获取详细内容
3. 整理结果并返回给用户

### 示例 2: 学术论文调研

**用户**: "帮我找一些关于大语言模型的论文"

**Claude Code 操作**:
1. 调用 `web_search_academic(query="large language model survey", include_code=true)`
2. 整理论文列表返回

### 示例 3: 产品信息爬取

**用户**: "帮我收集 iPhone 17 的用户评价"

**Claude Code 操作**:
1. 调用 `web_search_internet(query="iPhone 17 用户评价")`
2. 调用 `web_search_combined(query="iPhone 17 使用体验", crawl_top=5)`
3. 整理评论数据

---

## 最佳实践

### 1. 选择合适的工具
- 单次访问：`web_fetch`
- JavaScript 页面：`web_fetch_js`
- 信息搜索：`web_search_internet`
- 深入研究：`web_research`
- 学术查询：`web_search_academic`

### 2. 组合使用工具
```
web_search_internet → web_fetch → parse_html
```

### 3. 错误处理
如果工具返回错误，尝试：
- 使用 `web_fetch_js` 代替 `web_fetch`
- 更换搜索引擎
- 减少爬取深度

### 4. 性能优化
- 先搜索再爬取，避免盲目访问
- 限制爬取深度和页面数
- 使用缓存（自动启用）

---

## 故障排除

### MCP Server 无法启动
```
检查：
1. Python 是否正确安装
2. 依赖是否安装 (pip install -r requirements.txt)
3. 工作目录是否正确
4. 防火墙设置
```

### 工具调用失败
```
尝试：
1. 检查 URL 格式是否正确
2. 使用 browser 模式 (web_fetch_js)
3. 增加超时时间
```

### 搜索结果为空
```
建议：
1. 更换搜索引擎
2. 修改查询关键词
3. 使用英文搜索
```

---

## 输出示例

成功响应:
```json
{
  "success": true,
  "data": {...},
  "content": "搜索结果摘要...",
  "error": null
}
```

失败响应:
```json
{
  "success": false,
  "data": null,
  "content": null,
  "error": "错误描述"
}
```

---

## 更新和维护

### 更新 Web-Rooter
```bash
cd E:\ApplicationProgram\web-rooter
git pull
pip install -r requirements.txt
```

### 检查状态
```bash
python main.py --mcp
```

### 查看日志
工具执行日志会显示在 Claude Code 的输出中

---

## 联系和支持

遇到问题时：
1. 查看 `docs/AGENT_API.md` 了解详细 API
2. 运行 `python run_test.py` 测试功能
3. 检查 `FEATURES.md` 了解支持的功能

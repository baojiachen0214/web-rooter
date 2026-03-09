# Web-Rooter MCP 快速使用指南

## 配置状态

web-rooter 已成功注册到 Claude Code 用户级别配置，所有项目均可使用。

**配置位置**: `%APPDATA%\Claude\config.json`

**MCP Server 配置**:
```json
{
  "mcpServers": {
    "web-rooter": {
      "command": "E:\\Anaconda\\python.exe",
      "args": ["E:\\ApplicationProgram\\web-rooter\\main.py", "--mcp"],
      "env": {
        "PYTHONUNBUFFERED": "1",
        "PYTHONIOENCODING": "utf-8"
      }
    }
  }
}
```

---

## 验证安装

### 方法 1: 在 Claude Code 中
1. 打开 Claude Code
2. 输入 `/tools` 查看可用工具
3. 应该能看到 web-rooter 提供的工具列表

### 方法 2: 测试功能
在 Claude Code 中输入:
```
访问 https://example.com 并告诉我内容
```

---

## 可用工具列表

web-rooter 提供以下 MCP 工具供 Claude Code 调用:

| 工具名 | 描述 | 参数 |
|--------|------|------|
| `web_fetch` | 获取网页内容 | url |
| `web_fetch_js` | 使用浏览器获取 (支持 JavaScript) | url, wait_for |
| `web_search` | 在内容中搜索 | query, url |
| `web_extract` | 提取特定信息 | url, target |
| `web_crawl` | 爬取网站 | start_url, max_pages, max_depth |
| `parse_html` | 解析 HTML | html, url |
| `get_links` | 获取页面链接 | url, internal_only |
| `web_deep_search` | 深度互联网搜索 | query |
| `web_research` | 深度研究主题 | topic |
| `web_search_academic` | 学术搜索 | query |

---

## 使用示例

### 1. 基础网页访问
```
> 访问 https://github.com/trending 并告诉我热门项目
```

### 2. 信息搜索
```
> 搜索 Python 3.12 的新特性
```

### 3. 信息提取
```
> 从 https://example.com 提取网站标题和描述
```

### 4. 网站爬取
```
> 爬取 https://docs.python.org 前 5 个页面
```

### 5. 深度研究
```
> 研究 Transformer 架构的最新进展
```

### 6. 学术搜索
```
> 搜索关于深度学习的论文和代码项目
```

---

## CLI 调用方式

### 直接在 Claude Code 中使用
只需自然语言描述你的需求，Claude 会自动调用 web-rooter MCP 工具。

### 使用命令行 (独立模式)
```bash
# 交互模式
cd E:\ApplicationProgram\web-rooter
python main.py

# 直接命令
python main.py visit https://example.com
python main.py search "关键词"
python main.py crawl https://example.com 5 2

# MCP 服务器模式 (Claude Code 自动启动)
python main.py --mcp

# HTTP API 模式
python main.py --server
```

---

## 管理配置

### 查看当前配置
```bash
# 在 Claude Code 中
/mcp
```

### 临时禁用 MCP
```bash
# 启动时禁用
claude --no-mcp

# 或设置环境变量
ENABLE_MCP=false claude
```

### 卸载 web-rooter MCP
运行卸载脚本:
```bash
E:\ApplicationProgram\web-rooter\uninstall-claude-mcp.bat
```

或手动编辑 `%APPDATA%\Claude\config.json` 移除 `web-rooter` 配置。

---

## 故障排除

### 问题 1: 工具未显示
- 确保已重启 Claude Code
- 检查 Python 路径是否正确
- 确认依赖已安装：`pip install -r requirements.txt`

### 问题 2: 工具调用失败
- 检查 Playwright 浏览器：`playwright install chromium`
- 确保网络连接正常
- 查看 MCP server 日志

### 问题 3: 编码错误
配置中已包含：
```json
"env": {
  "PYTHONIOENCODING": "utf-8",
  "PYTHONUNBUFFERED": "1"
}
```

---

## 高级功能

### Session Hook
配置中包含一个 SessionStart hook，每次 Claude Code 启动时会自动提醒优先使用 web-rooter 工具。

### MCP 资源
未来可以扩展支持 MCP 资源，使用 `@web-rooter:resource-name` 格式访问。

### MCP 提示
可以添加 MCP prompts，使用 `/mcp__web-rooter__prompt-name` 格式调用。

---

## 文件结构

```
E:\ApplicationProgram\web-rooter/
├── main.py                 # 主入口 (MCP 模式)
├── server.py               # HTTP API 服务器
├── requirements.txt        # Python 依赖
├── .mcp.json               # 项目级 MCP 配置
├── install-mcp.ps1         # PowerShell 安装脚本
├── setup-claude-mcp.bat    # 批处理安装脚本
├── uninstall-claude-mcp.bat # 卸载脚本
└── USAGE.md                # 本文档
```

---

## 联系方式

如有问题，请查阅项目文档或创建 issue。

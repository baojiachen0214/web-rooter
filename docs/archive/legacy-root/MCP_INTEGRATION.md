# Web-Rooter MCP 深度集成报告

## 集成状态：已完成

---

## 配置架构

```
┌─────────────────────────────────────────────────────────────┐
│                      Claude Code                            │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  /tools  → web-rooter MCP tools                    │   │
│  │  @web-rooter:resource → MCP resources              │   │
│  │  /mcp → 查看和管理 MCP servers                     │   │
│  └─────────────────────────────────────────────────────┘   │
│                            │                                │
│                            │ stdio transport                │
└────────────────────────────┼────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────┐
│              Claude Code MCP Configuration                  │
│              %APPDATA%\Claude\config.json                   │
│                                                             │
│  {                                                          │
│    "mcpServers": {                                          │
│      "web-rooter": {                                        │
│        "command": "E:\Anaconda\python.exe",                 │
│        "args": ["E:\ApplicationProgram\web-rooter\main.py", │
│                 "--mcp"],                                   │
│        "env": {                                             │
│          "PYTHONUNBUFFERED": "1",                           │
│          "PYTHONIOENCODING": "utf-8"                        │
│        }                                                    │
│      }                                                      │
│    },                                                       │
│    "toolPreferences": {                                     │
│      "preferMcpTools": true                                 │
│    },                                                       │
│    "hooks": {                                               │
│      "SessionStart": [...]                                  │
│    }                                                        │
│  }                                                          │
└─────────────────────────────────────────────────────────────┘
                             │
                             │ python main.py --mcp
                             ▼
┌─────────────────────────────────────────────────────────────┐
│                   web-rooter MCP Server                     │
│              E:\ApplicationProgram\web-rooter               │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  Available Tools:                                   │   │
│  │  • web_fetch         - 获取网页内容                 │   │
│  │  • web_fetch_js      - 浏览器获取 (支持 JS)          │   │
│  │  • web_search        - 内容搜索                     │   │
│  │  • web_search_internet - 互联网搜索 (多引擎)         │   │
│  │  • web_research      - 深度研究                     │   │
│  │  • web_search_academic - 学术搜索                  │   │
│  │  • web_search_site   - 站内搜索                     │   │
│  │  • web_extract       - 信息提取                     │   │
│  │  • web_crawl         - 网站爬取                     │   │
│  │  • parse_html        - HTML 解析                    │   │
│  │  • get_links         - 获取链接                     │   │
│  └─────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

---

## 已创建的文件

### 1. 配置文件
| 文件 | 位置 | 用途 |
|------|------|------|
| `config.json` | `%APPDATA%\Claude\` | Claude Code 主配置 |
| `.mcp.json` | `E:\ApplicationProgram\web-rooter\` | 项目级 MCP 配置 |

### 2. 安装脚本
| 文件 | 描述 |
|------|------|
| `setup-claude-mcp.bat` | 一键安装脚本（批处理） |
| `install-mcp.ps1` | PowerShell 安装脚本 |
| `uninstall-claude-mcp.bat` | 卸载脚本 |

### 3. 文档
| 文件 | 描述 |
|------|------|
| `USAGE.md` | 详细使用指南 |
| `MCP_INTEGRATION.md` | 本文件 |

---

## 使用方式

### 方式 1: 自然语言调用（推荐）

在 Claude Code 中直接用自然语言描述需求：

```
> 访问 https://example.com 并告诉我内容

> 搜索 Python 3.12 的新特性

> 爬取 https://github.com/trending 前 5 个项目

> 研究 Transformer 架构的最新进展

> 从 https://news.ycombinator.com 提取最新头条新闻
```

Claude 会自动选择并调用合适的 web-rooter MCP 工具。

### 方式 2: 查看可用工具

```
> /tools
```

显示所有可用的 MCP 工具。

### 方式 3: 查看 MCP 状态

```
> /mcp
```

显示 MCP server 连接状态和身份验证选项。

---

## 工具调用流程

```
用户请求
    │
    ▼
Claude Code 分析意图
    │
    ▼
选择合适的 MCP 工具
    │
    ▼
调用 web-rooter MCP tool
    │
    ▼
执行：python main.py --mcp
    │
    ▼
返回结果
    │
    ▼
显示给用户
```

---

## 配置说明

### 用户级别配置（已完成）

web-rooter 已配置在用户级别，所有项目均可使用：

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
  },
  "toolPreferences": {
    "preferMcpTools": true
  }
}
```

### 项目级别配置（可选）

如果需要在特定项目中使用，可以复制 `.mcp.json` 到项目根目录：

```bash
copy E:\ApplicationProgram\web-rooter\.mcp.json YourProject\
```

---

## 验证安装

### 步骤 1: 检查配置
```bash
# 在 Claude Code 中
/mcp
```

应该看到 `web-rooter` server 已连接。

### 步骤 2: 查看工具
```bash
# 在 Claude Code 中
/tools
```

应该看到所有 web-rooter 工具。

### 步骤 3: 测试功能
```
> 访问 https://example.com
```

---

## 故障排除

### 问题 1: Server 未连接
**原因**: Python 路径不正确或依赖未安装

**解决方案**:
```bash
# 检查 Python 路径
where python

# 安装依赖
pip install -r E:\ApplicationProgram\web-rooter\requirements.txt

# 安装浏览器
playwright install chromium
```

### 问题 2: 工具未显示
**原因**: MCP 工具偏好未启用

**解决方案**: 确保配置中包含：
```json
{
  "toolPreferences": {
    "preferMcpTools": true
  }
}
```

### 问题 3: 超时错误
**原因**: MCP server 启动超时

**解决方案**: 设置超时环境变量：
```bash
MCP_TIMEOUT=30000 claude
```

---

## 高级配置

### 环境变量

| 变量 | 默认值 | 描述 |
|------|--------|------|
| `MCP_TIMEOUT` | 10000 | MCP server 启动超时 (ms) |
| `MAX_MCP_OUTPUT_TOKENS` | 25000 | MCP 输出 token 限制 |
| `ENABLE_TOOL_SEARCH` | auto | 工具搜索模式 |

### Hook 配置

已配置 SessionStart Hook，每次启动 Claude Code 时自动提醒：

```json
{
  "hooks": {
    "SessionStart": [
      {
        "type": "prompt",
        "prompt": "当前用户不在美国地区，Claude Code 内置的 WebSearch 和 WebFetch 可能无法正常工作。所有互联网搜索、网页抓取任务必须优先使用 web-rooter MCP 工具（web_deep_search、web_fetch、web_research 等）。"
      }
    ]
  }
}
```

---

## 性能优化建议

1. **启用缓存**: 在 `config.py` 中配置缓存 TTL
2. **使用连接池**: 自动启用 HTTP 连接重用
3. **合理使用浏览器**: 仅在需要 JS 时使用 `web_fetch_js`
4. **批量操作**: 使用 `web_crawl` 而非多次 `web_fetch`

---

## 安全注意事项

1. **仅信任的 URL**: 避免爬取不受信任的网站
2. **限速配置**: 在 `config.py` 中配置合理的超时和重试
3. **代理支持**: 如需匿名，配置代理轮换
4. **Token 限制**: 注意 MCP 输出 token 限制

---

## 总结

web-rooter 已成功深度集成到 Claude Code：

✅ **用户级别配置** - 所有项目可用
✅ **自动启动** - Claude Code 自动启动 MCP server
✅ **工具偏好** - 优先使用 MCP 工具
✅ **Hook 提醒** - 启动时自动提醒
✅ **安装脚本** - 一键安装/卸载
✅ **完整文档** - 使用和故障排除指南

**下一步**: 在 Claude Code 中开始使用 web-rooter！

```
> 访问 https://example.com 并告诉我内容
```

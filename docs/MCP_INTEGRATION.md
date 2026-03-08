# Web-Rooter MCP 集成配置指南

**版本**: v2.1
**更新日期**: 2026-03-08

---

## 一、配置步骤

### 1.1 找到 Claude Code 配置文件

根据你的操作系统，配置文件位置如下：

**Windows**:
```
%APPDATA%\Claude\config.json
通常是：C:\Users\<你的用户名>\AppData\Roaming\Claude\config.json
```

**macOS/Linux**:
```
~/.config/claude/config.json
```

### 1.2 添加 MCP Server 配置

在配置文件中添加以下内容：

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

### 1.3 验证配置

1. 重启 Claude Code
2. 输入 `/tools` 命令
3. 检查是否看到以下工具：
   - `web_fetch`
   - `web_fetch_js`
   - `web_search_internet`
   - `web_deep_search`
   - `web_search_social`
   - `web_search_tech`
   - `web_research`
   - `web_search_academic`
   - `web_search_site`
   - `web_search_combined`
   - `web_extract`
   - `web_crawl`
   - `parse_html`
   - `get_links`
   - `web_search`

---

## 二、全局使用 web-rooter 配置

### 2.1 禁用内置工具（推荐）

**重要**: 为确保 Claude Code 始终使用 web-rooter 而非内置工具，请在项目配置中添加：

在你的项目 `.claude/settings.local.json` 中添加：

```json
{
  "toolPreferences": {
    "preferMcpTools": true,
    "defaultSearchTool": "web-rooter"
  }
}
```

### 2.2 提示词配置

在你的项目 `CLAUDE.md` 中添加以下提示：

```markdown
## 搜索工具使用规范

**重要**: 本项目的所有互联网搜索任务必须使用 web-rooter MCP 工具，而不是 Claude Code 内置的搜索工具。

### 可用工具
- `web_deep_search` - 深度搜索（推荐默认使用）
- `web_search_internet` - 互联网搜索
- `web_search_social` - 社交媒体搜索
- `web_search_tech` - 技术社区搜索
- `web_search_academic` - 学术搜索
- `web_research` - 深度研究
- `web_fetch` - 获取网页
- `web_fetch_js` - 浏览器获取
- `web_crawl` - 网站爬取
- `web_extract` - 信息提取

### 信息来源标注
- 所有内容必须标注来源
- web-rooter 搜索结果：标注 `[web-rooter]`
- AI 知识库内容：标注 `[AI 知识库]`
- 未找到信息：标注 `[未找到]`
```

---

## 三、使用示例

### 3.1 基本搜索

```
用户：帮我搜索最新的 AI 新闻

AI: 我将使用 web-rooter 的 web_deep_search 工具来搜索最新的 AI 新闻。
    [调用 web_deep_search("AI 人工智能 最新新闻", use_english=True, crawl_top=5)]

    根据 web-rooter 搜索结果，找到以下信息：
    [内容] [web-rooter]
```

### 3.2 技术调研

```
用户：帮我调研 Python 量化交易框架

AI: 我将使用 web-rooter 进行技术社区搜索。
    [调用 web_search_tech("Python quantitative trading framework", sources=["github", "stackoverflow"])]

    根据 web-rooter 搜索结果：
    [内容] [web-rooter]
```

### 3.3 深度研究

```
用户：帮我研究 Transformer 架构原理

AI: 我将使用 web-rooter 的 web_research 工具进行深度研究。
    [调用 web_research("Transformer architecture principle", max_pages=15)]

    根据 web-rooter 的深度研究结果：
    [内容] [web-rooter]
```

---

## 四、常见问题

### Q1: 如何确认 web-rooter 已正确配置？

**A**: 在 Claude Code 中输入 `/tools`，如果看到 15 个 web-rooter 工具，说明配置成功。

### Q2: web-rooter 和内置工具同时存在怎么办？

**A**: 在提示词中明确要求使用 web-rooter，或在配置中设置 `preferMcpTools: true`。

### Q3: 如何确保 AI 不使用内置搜索？

**A**: 在 `CLAUDE.md` 中明确说明，并在对话开始时提醒：
```
注意：请使用 web-rooter 工具进行搜索，不要使用内置搜索。
```

---

## 五、最佳实践

### 5.1 默认工具选择

| 任务类型 | 推荐工具 |
|----------|----------|
| 一般搜索 | `web_deep_search` |
| 技术内容 | `web_search_tech` |
| 用户评价 | `web_search_social` |
| 学术内容 | `web_search_academic` |
| 深度研究 | `web_research` |
| 获取网页 | `web_fetch` 或 `web_fetch_js` |
| 爬取网站 | `web_crawl` |

### 5.2 提示词模板

在对话开始时使用：

```
我将使用 web-rooter 来搜索相关信息。web-rooter 是一个集成了 21 个搜索引擎的工具，可以获取最新的第一手资料。
```

在回答结束时使用：

```
以上信息来源于 web-rooter 搜索到的网页内容。我的训练数据截至 2025 年，如有冲突请以最新搜索结果为准。
```

---

## 六、配置文件完整示例

### 6.1 Claude Code 全局配置

**位置**: `%APPDATA%\Claude\config.json`

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
  },
  "toolPreferences": {
    "preferMcpTools": true
  }
}
```

### 6.2 项目配置

**位置**: `项目根目录/.claude/settings.local.json`

```json
{
  "toolPreferences": {
    "preferMcpTools": true,
    "defaultSearchTool": "web-rooter"
  },
  "permissions": {
    "allow": [
      "Bash(python:*)",
      "Bash(E:/ApplicationProgram/web-rooter/tests:*)"
    ]
  }
}
```

### 6.3 项目 CLAUDE.md

**位置**: `项目根目录/CLAUDE.md`

```markdown
# CLAUDE.md

## 搜索工具使用规范

**重要**: 本项目所有互联网搜索必须使用 web-rooter MCP 工具。

### 可用工具
[工具列表...]

### 信息来源标注
- web-rooter 搜索结果：[web-rooter]
- AI 知识库内容：[AI 知识库]
- 未找到信息：[未找到]
```

---

## 七、检查清单

在开始使用前，请确认：

- [ ] MCP Server 配置已添加到 Claude Code 配置文件
- [ ] 重启过 Claude Code
- [ ] 输入 `/tools` 能看到 15 个 web-rooter 工具
- [ ] 项目 `.claude/settings.local.json` 已配置
- [ ] 项目 `CLAUDE.md` 已添加使用说明

---

**配置完成后，Claude Code 将全局使用 web-rooter 进行所有搜索任务。**

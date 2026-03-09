# Web-Rooter 全局配置指南

**目标**: 在任意项目/文件夹中打开 Claude Code，都能优先使用 web-rooter 而不是内置工具。

---

## 一、快速配置（推荐）

### Windows 用户

1. **运行安装脚本**

   双击运行项目根目录的：
   ```
   setup-global-mcp.bat
   ```

   或手动执行：
   ```bash
   # 在 web-rooter 项目目录
   .\setup-global-mcp.bat
   ```

2. **验证配置**

   - 打开任意项目/文件夹的 Claude Code
   - 输入 `/tools` 命令
   - 检查是否看到以下工具：
     - `web_fetch`, `web_fetch_js`
     - `web_search_internet`, `web_deep_search`
     - `web_search_social`, `web_search_tech`
     - `web_research`, `web_search_academic`
     - 等 15 个 web-rooter 工具

3. **测试使用**

   在任意项目中尝试：
   ```
   搜索一下 iPhone 17 的用户评价
   ```

   Claude Code 应该自动使用 `web_search_social` 或 `web_deep_search` 工具。

---

## 二、手动配置

### 2.1 编辑全局配置文件

**位置**: `%APPDATA%\Claude\config.json`

在 Windows 资源管理器地址栏输入 `%APPDATA%\Claude\` 即可访问。

添加以下配置：

```json
{
  "mcpServers": {
    "web-rooter": {
      "command": "python",
      "args": ["E:\\ApplicationProgram\\web-rooter\\main.py", "--mcp"],
      "cwd": "E:\\ApplicationProgram\\web-rooter",
      "env": {
        "PYTHONIOENCODING": "utf-8"
      }
    }
  },
  "toolPreferences": {
    "preferMcpTools": true
  }
}
```

**注意**: 将路径修改为你实际的 web-rooter 安装路径。

### 2.2 配置说明

| 配置项 | 说明 |
|--------|------|
| `mcpServers.web-rooter` | MCP Server 配置 |
| `command` | 启动命令（python） |
| `args` | 参数数组，包含脚本路径和 `--mcp` 标志 |
| `cwd` | 工作目录（web-rooter 项目路径） |
| `env` | 环境变量（UTF-8 编码） |
| `toolPreferences.preferMcpTools` | 优先使用 MCP 工具 |

---

## 三、配置验证

### 3.1 检查 MCP Server 状态

在 Claude Code 中输入：
```
/tools
```

应该看到类似输出：
```
MCP 工具 (web-rooter):
- web_fetch
- web_fetch_js
- web_search
- web_search_internet
- web_deep_search
- web_search_social
- web_search_tech
- web_search_academic
- web_search_site
- web_research
- web_extract
- web_crawl
- parse_html
- get_links
```

### 3.2 测试工具调用

在任意项目中尝试以下命令：

| 命令 | 预期行为 |
|------|----------|
| "帮我搜索 AI 最新进展" | 使用 `web_deep_search` |
| "查找 iPhone 17 用户评价" | 使用 `web_search_social` |
| "搜索 Transformer 相关论文" | 使用 `web_search_academic` |
| "访问 https://github.com 并提取信息" | 使用 `web_fetch` 或 `web_fetch_js` |

---

## 四、故障排查

### 问题 1: 看不到 web-rooter 工具

**可能原因**:
- 配置文件路径错误
- 未重启 Claude Code
- Python 未安装或不在 PATH 中

**解决方法**:
1. 检查 `%APPDATA%\Claude\config.json` 配置是否正确
2. 完全关闭并重新打开 Claude Code
3. 运行 `python --version` 确认 Python 可用

### 问题 2: 工具调用失败

**可能原因**:
- web-rooter 路径配置错误
- 依赖未安装

**解决方法**:
1. 检查 `cwd` 路径是否指向正确的 web-rooter 目录
2. 运行 `pip install -r requirements.txt` 安装依赖
3. 查看 MCP Server 日志

### 问题 3: 仍然使用内置工具

**可能原因**:
- `preferMcpTools` 未设置
- 内置工具响应更快

**解决方法**:
1. 确保配置了 `"preferMcpTools": true`
2. 在提示词中明确指定使用 web-rooter 工具

---

## 五、项目级配置（可选）

如果需要为特定项目配置不同的权限：

**位置**: `项目根目录/.claude/settings.local.json`

```json
{
  "permissions": {
    "allow": [
      "Bash(python:*)",
      "Bash(E:/ApplicationProgram/web-rooter/main.py:*)"
    ]
  },
  "toolPreferences": {
    "preferMcpTools": true
  }
}
```

---

## 六、卸载

### 方法 1: 运行卸载脚本

```bash
.\setup-uninstall-mcp.bat
```

### 方法 2: 手动删除

编辑 `%APPDATA%\Claude\config.json`，删除 `mcpServers.web-rooter` 配置。

---

## 七、高级配置

### 7.1 使用绝对路径的 Python

如果 Python 不在系统 PATH 中：

```json
{
  "mcpServers": {
    "web-rooter": {
      "command": "C:\\Python311\\python.exe",
      "args": ["E:\\ApplicationProgram\\web-rooter\\main.py", "--mcp"],
      "cwd": "E:\\ApplicationProgram\\web-rooter"
    }
  }
}
```

### 7.2 多项目配置

如果有多个 web-rooter 项目：

```json
{
  "mcpServers": {
    "web-rooter-dev": {
      "command": "python",
      "args": ["E:\\dev\\web-rooter\\main.py", "--mcp"],
      "cwd": "E:\\dev\\web-rooter"
    },
    "web-rooter-prod": {
      "command": "python",
      "args": ["E:\\prod\\web-rooter\\main.py", "--mcp"],
      "cwd": "E:\\prod\\web-rooter"
    }
  }
}
```

---

## 八、配置检查清单

- [ ] 已运行 `setup-global-mcp.bat` 或手动配置
- [ ] 路径已修改为实际的 web-rooter 安装位置
- [ ] 已重启 Claude Code
- [ ] 在任意项目中输入 `/tools` 能看到 15 个 web-rooter 工具
- [ ] 测试搜索命令正常执行
- [ ] （可选）项目级权限已配置

---

**完成配置后，无论打开什么项目，Claude Code 都会优先使用 web-rooter 进行网络访问！**

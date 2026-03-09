# Web-Rooter 系统级 CLI 集成指南

## 快速安装

### 方式 1: 运行安装脚本（推荐）

```bash
# 普通用户终端即可（无需管理员）
cd E:\ApplicationProgram\web-rooter
install-system-cli.bat
```

### 方式 2: 手动配置

#### 步骤 1: 创建用户级命令

创建 `%LOCALAPPDATA%\web-rooter\bin\wr.bat`:
```batch
@echo off
chcp 65001 >nul
"E:\Anaconda\python.exe" "E:\ApplicationProgram\web-rooter\main.py" %*
```

并把 `%LOCALAPPDATA%\web-rooter\bin` 加入用户 PATH。

#### 步骤 2: 配置 PowerShell 模块

创建 `~\Documents\WindowsPowerShell\Modules\WebRooter\WebRooter.psm1`:
```powershell
$WebRooterDir = "E:\ApplicationProgram\web-rooter"
$PythonPath = "E:\Anaconda\python.exe"

function Invoke-WebVisit {
    param([Parameter(Mandatory=$true)] [string]$Url)
    & $PythonPath "$WebRooterDir\main.py" visit $Url
}

function Invoke-WebSearch {
    param([Parameter(Mandatory=$true)] [string]$Query)
    & $PythonPath "$WebRooterDir\main.py" search $Query
}

function Invoke-WebCrawl {
    param(
        [Parameter(Mandatory=$true)] [string]$Url,
        [int]$Pages = 5,
        [int]$Depth = 2
    )
    & $PythonPath "$WebRooterDir\main.py" crawl $Url $Pages $Depth
}

function Invoke-WebDeepSearch {
    param([Parameter(Mandatory=$true)] [string]$Query)
    & $PythonPath "$WebRooterDir\main.py" deep $Query
}

# 导出别名
Set-Alias -Name wr -Value Invoke-WebVisit -Scope Global
Export-ModuleMember -Function * -Alias *
```

#### 步骤 3: 配置 Claude Code 权限

编辑 `%APPDATA%\Claude\settings.json`:
```json
{
  "permissions": {
    "allow": [
      "Bash(wr:*)",
      "Bash(web*:*)",
      "Bash(python:E:\\ApplicationProgram\\web-rooter\\main.py:*)"
    ]
  }
}
```

---

## 可用命令

### 系统级命令（任何终端）

```bash
# 主命令
wr <command> [args]

# 示例
wr visit https://example.com
wr quick "量化因子"
wr crawl https://zhihu.com 5 2
wr deep "Python 量化交易"
wr help
```

### PowerShell 函数

```powershell
# 导入模块
Import-Module WebRooter

# 使用函数（安装脚本会自动创建）
wr visit https://example.com
wr quick "量化因子"
webdoctor
```

### Claude Code 集成

在 Claude Code 中，现在可以直接使用：
```
> wr visit https://zhihu.com/question/123456
> wr deep "量化因子 知乎讨论"
> wr search "alpha101 因子"
```

---

## 性能优势

相比 MCP 模式，系统 CLI 集成有以下优势：

| 对比项 | MCP 模式 | 系统 CLI 模式 |
|--------|---------|--------------|
| 启动延迟 | 2-3 秒 | <0.3 秒 |
| 通信开销 | 高（JSON-RPC） | 低（直接执行） |
| 内存占用 | 高（常驻进程） | 低（按需启动） |
| 错误恢复 | 复杂 | 简单 |
| Claude 集成 | 自动 | 需配置权限 |

---

## 卸载

```bash
# 运行卸载脚本
uninstall-system-cli.bat
```

---

## 示例用法

### 1. 爬取知乎量化讨论
```bash
wr visit https://www.zhihu.com/search?q=量化因子&type=content
wr search "alpha101 因子 知乎"
```

### 2. 小红书爬取
```bash
wr visit https://www.xiaohongshu.com/search_result?keyword=量化交易
```

### 3. 深度搜索
```bash
wr deep "量化因子框架 2025 最新"
```

### 4. 站内搜索
```bash
wr site https://www.zhihu.com "WorldQuant alpha 因子"
```

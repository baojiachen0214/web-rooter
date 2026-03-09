@echo off
chcp 65001 >nul
echo ========================================
echo   Web-Rooter 全局 MCP 配置安装程序
echo ========================================
echo.

:: 获取当前脚本所在目录的绝对路径
set SCRIPT_DIR=%~dp0
set SCRIPT_DIR=%SCRIPT_DIR:~0,-1%
for %%I in ("%SCRIPT_DIR%\..\..") do set REPO_ROOT=%%~fI

echo 检测到 web-rooter 安装路径:
echo %REPO_ROOT%
echo.

:: Claude Code 全局配置目录
set CLAUDE_CONFIG_DIR=%APPDATA%\Claude

:: 检查配置文件是否存在
if not exist "%CLAUDE_CONFIG_DIR%\config.json" (
    echo 创建新的配置文件...
    echo {} > "%CLAUDE_CONFIG_DIR%\config.json"
)

echo 备份现有配置...
copy "%CLAUDE_CONFIG_DIR%\config.json" "%CLAUDE_CONFIG_DIR%\config.json.bak" >nul

echo.
echo 正在配置 web-rooter MCP Server...
echo.

:: 使用 PowerShell 读取和修改 JSON
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
"$configPath = '%CLAUDE_CONFIG_DIR%\config.json'; ^
$config = if (Test-Path $configPath) { Get-Content $configPath | ConvertFrom-Json } else { [PSCustomObject]@{} }; ^
^
if (-not $config.mcpServers) { $config | Add-Member -NotePropertyName 'mcpServers' -NotePropertyValue ([PSCustomObject]@{}) }; ^
^
$config.mcpServers | Add-Member -NotePropertyName 'web-rooter' -NotePropertyValue ([PSCustomObject]@{ ^
    command = 'python' ^
    args = @('%REPO_ROOT%\main.py', '--mcp') ^
    cwd = '%REPO_ROOT%' ^
    env = [PSCustomObject]@{ PYTHONIOENCODING = 'utf-8' } ^
}) -Force; ^
^
if (-not $config.toolPreferences) { $config | Add-Member -NotePropertyName 'toolPreferences' -NotePropertyValue ([PSCustomObject]@{}) }; ^
$config.toolPreferences.preferMcpTools = $true; ^
^
$config | ConvertTo-Json -Depth 10 | Set-Content $configPath -Encoding UTF8; ^
Write-Host '配置完成！' -ForegroundColor Green"

echo.
echo ========================================
echo   配置成功！
echo ========================================
echo.
echo 配置文件位置：%APPDATA%\Claude\config.json
echo.
echo 下一步:
echo 1. 重启所有 Claude Code 窗口
echo 2. 输入 /tools 验证 web-rooter 工具已加载
echo.
echo 如需卸载，运行：scripts\windows\setup-uninstall-mcp.bat
echo.
pause

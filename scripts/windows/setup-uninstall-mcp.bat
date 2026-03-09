@echo off
chcp 65001 >nul
echo ========================================
echo   Web-Rooter MCP 卸载程序
echo ========================================
echo.

set CLAUDE_CONFIG_DIR=%APPDATA%\Claude

if not exist "%CLAUDE_CONFIG_DIR%\config.json" (
    echo 配置文件不存在
    pause
    exit /b 1
)

echo 备份现有配置...
copy "%CLAUDE_CONFIG_DIR%\config.json" "%CLAUDE_CONFIG_DIR%\config.json.bak" >nul

echo.
echo 正在移除 web-rooter MCP Server 配置...
echo.

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
"$configPath = '%CLAUDE_CONFIG_DIR%\config.json'; ^
$config = Get-Content $configPath | ConvertFrom-Json; ^
^
if ($config.mcpServers -and $config.mcpServers.'web-rooter') { ^
    $config.mcpServers.PSObject.Properties.Remove('web-rooter'); ^
    $config | ConvertTo-Json -Depth 10 | Set-Content $configPath -Encoding UTF8; ^
    Write-Host 'web-rooter MCP Server 已移除' -ForegroundColor Green; ^
} else { ^
    Write-Host '未找到 web-rooter MCP Server 配置' -ForegroundColor Yellow; ^
}"

echo.
echo 卸载完成！重启 Claude Code 后生效。
echo.
pause

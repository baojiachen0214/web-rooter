@echo off
chcp 65001 >nul
echo ========================================
echo   Web-Rooter MCP 卸载脚本
echo ========================================
echo.

:: 使用 PowerShell 移除配置
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
"$claudeConfigPath = $env:APPDATA + '\Claude\config.json'; ^
^
if (Test-Path $claudeConfigPath) { ^
    $config = Get-Content $claudeConfigPath | ConvertFrom-Json; ^
    ^
    if ($config.mcpServers -and $config.mcpServers.'web-rooter') { ^
        $config.mcpServers.PSObject.Properties.Remove('web-rooter'); ^
        $config | ConvertTo-Json -Depth 10 | Set-Content $claudeConfigPath -Encoding UTF8; ^
        Write-Host '✓ 已移除 web-rooter MCP 配置' -ForegroundColor Green; ^
    } else { ^
        Write-Host '未找到 web-rooter 配置' -ForegroundColor Yellow; ^
    } ^
} else { ^
    Write-Host '配置文件不存在' -ForegroundColor Yellow; ^
}"

echo.
echo 卸载完成！
echo.
pause

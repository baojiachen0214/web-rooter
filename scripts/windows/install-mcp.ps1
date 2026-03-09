# Web-Rooter MCP Installer (dynamic paths)
param(
    [string]$ProjectDir = (Resolve-Path (Join-Path (Split-Path -Parent $MyInvocation.MyCommand.Path) "..\..")).Path,
    [string]$PythonPath = ""
)

if (-not $PythonPath) {
    $pythonCmd = Get-Command python -ErrorAction SilentlyContinue
    if (-not $pythonCmd) {
        Write-Error "未找到 python，请先安装 Python 并加入 PATH"
        exit 1
    }
    $PythonPath = $pythonCmd.Source
}

$mainPy = Join-Path $ProjectDir "main.py"
if (-not (Test-Path $mainPy)) {
    Write-Error "未找到 main.py: $mainPy"
    exit 1
}

$claudeConfigDir = Join-Path $env:APPDATA "Claude"
$claudeConfigPath = Join-Path $claudeConfigDir "config.json"

Write-Host "========================================"
Write-Host "  Web-Rooter MCP Installer"
Write-Host "========================================"
Write-Host "Project: $ProjectDir"
Write-Host "Python : $PythonPath"
Write-Host ""

if (-not (Test-Path $claudeConfigDir)) {
    New-Item -ItemType Directory -Force -Path $claudeConfigDir | Out-Null
}

if (Test-Path $claudeConfigPath) {
    try {
        $config = Get-Content $claudeConfigPath -Raw | ConvertFrom-Json
    } catch {
        $config = [PSCustomObject]@{}
    }
} else {
    $config = [PSCustomObject]@{}
}

if (-not $config.mcpServers) {
    $config | Add-Member -NotePropertyName "mcpServers" -NotePropertyValue ([PSCustomObject]@{})
}

$mcpConfig = [PSCustomObject]@{
    command = $PythonPath
    args = @($mainPy, "--mcp")
    env = [PSCustomObject]@{
        PYTHONUNBUFFERED = "1"
        PYTHONIOENCODING = "utf-8"
    }
}
$config.mcpServers | Add-Member -NotePropertyName "web-rooter" -NotePropertyValue $mcpConfig -Force

if (-not $config.toolPreferences) {
    $config | Add-Member -NotePropertyName "toolPreferences" -NotePropertyValue ([PSCustomObject]@{})
}
if ($config.toolPreferences.PSObject.Properties.Name -notcontains "preferMcpTools") {
    $config.toolPreferences | Add-Member -NotePropertyName "preferMcpTools" -NotePropertyValue $true -Force
} else {
    $config.toolPreferences.preferMcpTools = $true
}

$config | ConvertTo-Json -Depth 20 | Set-Content $claudeConfigPath -Encoding UTF8

Write-Host "配置已写入: $claudeConfigPath" -ForegroundColor Green
Write-Host "下一步: 重启 Claude / Claude Code 后执行 /tools 验证"

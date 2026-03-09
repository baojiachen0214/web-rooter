@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

set SCRIPT_DIR=%~dp0
set SCRIPT_DIR=%SCRIPT_DIR:~0,-1%
for %%I in ("%SCRIPT_DIR%\..\..") do set REPO_ROOT=%%~fI
set MAIN_PY=%REPO_ROOT%\main.py
set CLAUDE_CONFIG_DIR=%APPDATA%\Claude
set CLAUDE_CONFIG=%CLAUDE_CONFIG_DIR%\config.json
set PROJECT_MCP=%REPO_ROOT%\.mcp.json

echo ========================================
echo   Web-Rooter MCP 一键安装
echo ========================================
echo.

if not exist "%MAIN_PY%" (
    echo [错误] 未找到 main.py: %MAIN_PY%
    pause
    exit /b 1
)

where python >nul 2>&1
if %errorlevel% neq 0 (
    echo [错误] 未找到 Python，请先安装 Python 并加入 PATH
    pause
    exit /b 1
)

for /f "delims=" %%i in ('where python') do (
    set PYTHON_PATH=%%i
    goto :found_python
)
:found_python

if "%PYTHON_PATH%"=="" (
    echo [错误] Python 路径解析失败
    pause
    exit /b 1
)

echo 项目目录: %REPO_ROOT%
echo Python : %PYTHON_PATH%
echo.

echo [1/3] 检查依赖...
"%PYTHON_PATH%" -c "import mcp" >nul 2>&1
if %errorlevel% neq 0 (
    echo   安装 mcp...
    "%PYTHON_PATH%" -m pip install mcp >nul 2>&1
    "%PYTHON_PATH%" -c "import mcp" >nul 2>&1
    if %errorlevel% neq 0 echo   [警告] mcp 安装失败，请手动执行: "%PYTHON_PATH%" -m pip install mcp
)
"%PYTHON_PATH%" -c "import playwright" >nul 2>&1
if %errorlevel% neq 0 (
    echo   安装 playwright...
    "%PYTHON_PATH%" -m pip install playwright >nul 2>&1
    "%PYTHON_PATH%" -c "import playwright" >nul 2>&1
    if %errorlevel% neq 0 echo   [警告] playwright 安装失败，请手动执行: "%PYTHON_PATH%" -m pip install playwright
)

echo [2/3] 写入 Claude 配置...
if not exist "%CLAUDE_CONFIG_DIR%" mkdir "%CLAUDE_CONFIG_DIR%"
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
"$configPath='%CLAUDE_CONFIG%'; $pythonPath='%PYTHON_PATH%'; $mainPy='%MAIN_PY%'; if(Test-Path $configPath){ try{ $config=ConvertFrom-Json (Get-Content -Raw $configPath) } catch { $config=[pscustomobject]@{} } } else { $config=[pscustomobject]@{} }; if(-not $config.mcpServers){ Add-Member -InputObject $config -NotePropertyName mcpServers -NotePropertyValue ([pscustomobject]@{}) }; $server=[pscustomobject]@{ command=$pythonPath; args=@($mainPy,'--mcp'); env=[pscustomobject]@{ PYTHONUNBUFFERED='1'; PYTHONIOENCODING='utf-8' } }; Add-Member -InputObject $config.mcpServers -NotePropertyName 'web-rooter' -NotePropertyValue $server -Force; if(-not $config.toolPreferences){ Add-Member -InputObject $config -NotePropertyName toolPreferences -NotePropertyValue ([pscustomobject]@{}) }; if(-not $config.toolPreferences.preferMcpTools){ Add-Member -InputObject $config.toolPreferences -NotePropertyName preferMcpTools -NotePropertyValue $true -Force } else { $config.toolPreferences.preferMcpTools=$true }; Set-Content -Path $configPath -Value (ConvertTo-Json $config -Depth 20) -Encoding UTF8; Write-Host ('  已写入: ' + $configPath)"

echo [3/3] 写入项目级 .mcp.json...
(
echo {
echo   "$schema": "https://json.schemastore.org/mcp-settings",
echo   "mcpServers": {
echo     "web-rooter": {
echo       "command": "%PYTHON_PATH:\=\\%",
echo       "args": ["%MAIN_PY:\=\\%", "--mcp"],
echo       "env": {
echo         "PYTHONIOENCODING": "utf-8",
echo         "PYTHONUNBUFFERED": "1"
echo       }
echo     }
echo   }
echo }
) > "%PROJECT_MCP%"
echo   已写入: %PROJECT_MCP%

echo.
echo ========================================
echo   安装完成
echo ========================================
echo.
echo 下一步:
echo 1. 重启 Claude / Claude Code
echo 2. 在 Claude Code 输入 /tools
echo 3. 执行 python main.py --doctor
echo.
pause

@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

set WITH_MCP=0
set NO_PAUSE=0

for %%A in (%*) do (
    if /I "%%~A"=="--with-mcp" set WITH_MCP=1
    if /I "%%~A"=="--no-pause" set NO_PAUSE=1
)

echo ========================================
echo Web-Rooter 一键安装（CLI First）
echo ========================================
echo.

set SCRIPT_DIR=%~dp0
set SCRIPT_DIR=%SCRIPT_DIR:~0,-1%
set MAIN_PY=%SCRIPT_DIR%\main.py
set VENV_DIR=%SCRIPT_DIR%\.venv312
set PYTHON_CMD=
set BOOTSTRAP_CMD=

if not exist "%MAIN_PY%" (
    echo [ERROR] 未找到 main.py: %MAIN_PY%
    goto :failed
)

if exist "%VENV_DIR%\Scripts\python.exe" (
    set BOOTSTRAP_CMD="%VENV_DIR%\Scripts\python.exe"
) else (
    where python >nul 2>&1
    if %errorlevel% equ 0 (
        set BOOTSTRAP_CMD=python
    ) else (
        where py >nul 2>&1
        if %errorlevel% equ 0 (
            set BOOTSTRAP_CMD=py -3
        ) else (
            echo [ERROR] 未找到 python 或 py，请先安装 Python 3.10+
            goto :failed
        )
    )
)

echo [INFO] Bootstrap Python: %BOOTSTRAP_CMD%
call %BOOTSTRAP_CMD% -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)"
if errorlevel 1 (
    echo [ERROR] 当前 Python 版本低于 3.10
    goto :failed
)

if not exist "%VENV_DIR%\Scripts\python.exe" (
    echo [1/7] 创建虚拟环境: %VENV_DIR%
    call %BOOTSTRAP_CMD% -m venv "%VENV_DIR%"
    if errorlevel 1 (
        echo [ERROR] 创建虚拟环境失败
        goto :failed
    )
) else (
    echo [1/7] 复用已有虚拟环境: %VENV_DIR%
)

set PYTHON_CMD=%VENV_DIR%\Scripts\python.exe
echo [INFO] Runtime Python: "%PYTHON_CMD%"

echo [2/7] 升级 pip...
"%PYTHON_CMD%" -m pip install --upgrade pip
if errorlevel 1 (
    echo [ERROR] pip 升级失败
    goto :failed
)

echo [3/7] 安装依赖...
"%PYTHON_CMD%" -m pip install -r "%SCRIPT_DIR%\requirements.txt"
if errorlevel 1 (
    echo [ERROR] 依赖安装失败
    goto :failed
)

"%PYTHON_CMD%" "%SCRIPT_DIR%\scripts\render_terminal_logo.py" --logo "%SCRIPT_DIR%\LOGO.png" --style blocks --width 64 --max-height 22

echo [4/7] 安装 Playwright Chromium...
"%PYTHON_CMD%" -m playwright install chromium
if errorlevel 1 (
    echo [WARN] Playwright 浏览器安装失败，可稍后手动执行:
    echo        "%PYTHON_CMD%" -m playwright install chromium
)

echo [5/7] 环境自检...
"%PYTHON_CMD%" "%MAIN_PY%" --doctor
if errorlevel 1 (
    echo [WARN] doctor 发现异常，请阅读上方输出
)

echo [6/7] 安装全局 wr 命令（用户级）...
call "%SCRIPT_DIR%\scripts\windows\install-system-cli.bat" --no-pause
if errorlevel 1 (
    echo [WARN] 全局 wr 安装失败，可稍后手动执行:
    echo        scripts\windows\install-system-cli.bat
)

echo [7/7] 注入 AI 工具 Skills（Claude/Cursor/OpenCode/OpenClaw）...
"%PYTHON_CMD%" "%SCRIPT_DIR%\scripts\setup_ai_skills.py" --repo-root "%SCRIPT_DIR%"
if errorlevel 1 (
    echo [WARN] AI skills 注入失败，可稍后手动执行:
    echo        "%PYTHON_CMD%" "%SCRIPT_DIR%\scripts\setup_ai_skills.py" --repo-root "%SCRIPT_DIR%"
)

if "%WITH_MCP%"=="1" (
    echo [EXTRA] 配置 Claude MCP...
    call "%SCRIPT_DIR%\scripts\windows\setup-claude-mcp.bat"
)

echo.
echo ========================================
echo 安装完成
echo ========================================
echo.
echo 推荐命令:
echo   wr doctor
echo   wr do "抓取知乎评论区观点并给出处" --dry-run
echo   wr skills --resolve "抓取知乎评论区观点并给出处" --compact
echo.
echo 如需 MCP，再执行:
echo   scripts\windows\setup-claude-mcp.bat
echo.
goto :end

:failed
echo.
echo 安装失败，请先修复上方错误后重试。
echo.

:end
if "%NO_PAUSE%"=="0" pause
endlocal

@echo off
chcp 65001 >nul
echo ========================================
echo Web-Rooter 安装脚本
echo ========================================
echo.

set SCRIPT_DIR=%~dp0
set SCRIPT_DIR=%SCRIPT_DIR:~0,-1%
set MAIN_PY=%SCRIPT_DIR%\main.py
set PYTHON_CMD=python

if exist "%SCRIPT_DIR%\.venv312\Scripts\python.exe" (
    set PYTHON_CMD=%SCRIPT_DIR%\.venv312\Scripts\python.exe
) else if exist "%SCRIPT_DIR%\.venv\Scripts\python.exe" (
    set PYTHON_CMD=%SCRIPT_DIR%\.venv\Scripts\python.exe
)

echo [INFO] 使用 Python: %PYTHON_CMD%
%PYTHON_CMD% -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)"
if errorlevel 1 (
    echo 错误：当前 Python 版本低于 3.10
    echo 建议：安装 Python 3.10+ 或使用项目内 .venv/.venv312
    pause
    exit /b 1
)

echo [1/3] 安装 Python 依赖...
%PYTHON_CMD% -m pip install -r "%SCRIPT_DIR%\requirements.txt"
if errorlevel 1 (
    echo 错误：依赖安装失败
    pause
    exit /b 1
)

echo.
echo [2/3] 安装 Playwright 浏览器...
%PYTHON_CMD% -m playwright install chromium
if errorlevel 1 (
    echo 警告：浏览器安装失败，可以稍后手动安装
)

echo.
echo [3/3] 验证安装...
%PYTHON_CMD% "%MAIN_PY%" --doctor
if errorlevel 1 (
    echo 警告：验证失败，请检查错误信息
)

echo.
echo ========================================
echo 安装完成!
echo ========================================
echo.
echo 使用方法:
echo   - 交互模式：%PYTHON_CMD% main.py
echo   - MCP 模式：%PYTHON_CMD% main.py --mcp
echo   - HTTP 服务：%PYTHON_CMD% main.py --server
echo   - 快速入口：%PYTHON_CMD% main.py quick "OpenAI Agents SDK"
echo.
pause

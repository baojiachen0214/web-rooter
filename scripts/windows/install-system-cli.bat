@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

set NO_PAUSE=0
for %%A in (%*) do (
    if /I "%%~A"=="--no-pause" set NO_PAUSE=1
)

set SCRIPT_DIR=%~dp0
set SCRIPT_DIR=%SCRIPT_DIR:~0,-1%
for %%I in ("%SCRIPT_DIR%\..\..") do set REPO_ROOT=%%~fI
set MAIN_PY=%REPO_ROOT%\main.py

echo ========================================
echo   Web-Rooter CLI 安装（用户级）
echo ========================================
echo.

if not exist "%MAIN_PY%" (
    echo [错误] 未找到 main.py: %MAIN_PY%
    if "%NO_PAUSE%"=="0" pause
    exit /b 1
)

if exist "%REPO_ROOT%\.venv312\Scripts\python.exe" (
    set PYTHON_PATH=%REPO_ROOT%\.venv312\Scripts\python.exe
) else if exist "%REPO_ROOT%\.venv\Scripts\python.exe" (
    set PYTHON_PATH=%REPO_ROOT%\.venv\Scripts\python.exe
) else (
    where python >nul 2>&1
    if %errorlevel% neq 0 (
        echo [错误] 未找到 Python，请先安装 Python 并加入 PATH
        if "%NO_PAUSE%"=="0" pause
        exit /b 1
    )
    for /f "delims=" %%i in ('where python') do (
        set PYTHON_PATH=%%i
        goto :found_python
    )
)
:found_python

if "%PYTHON_PATH%"=="" (
    echo [错误] Python 路径解析失败
    if "%NO_PAUSE%"=="0" pause
    exit /b 1
)

echo Project: %REPO_ROOT%
echo Python : %PYTHON_PATH%
echo.

echo [1/4] 安装 wr 命令...
set USER_BIN_DIR=%LOCALAPPDATA%\web-rooter\bin
if not exist "%USER_BIN_DIR%" mkdir "%USER_BIN_DIR%"

set WR_SCRIPT=%USER_BIN_DIR%\wr.bat
(
echo @echo off
echo chcp 65001 ^>nul
echo "%PYTHON_PATH%" "%MAIN_PY%" %%*
) > "%WR_SCRIPT%"

echo   已创建: %WR_SCRIPT%

echo [2/4] 写入用户 PATH...
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
"$target='%USER_BIN_DIR%'; $current=[Environment]::GetEnvironmentVariable('Path','User'); if([string]::IsNullOrEmpty($current)){ $newPath=$target } elseif(($current -split ';') -contains $target){ $newPath=$current } else { $newPath=$current+';'+$target }; [Environment]::SetEnvironmentVariable('Path',$newPath,'User'); Write-Host '  已更新用户 PATH（重启终端后生效）'"

echo [3/4] 安装 PowerShell 模块...
set PS_MODULE_DIR=%USERPROFILE%\Documents\WindowsPowerShell\Modules\WebRooter
if not exist "%PS_MODULE_DIR%" mkdir "%PS_MODULE_DIR%"

set PS_MODULE=%PS_MODULE_DIR%\WebRooter.psm1
(
echo # Web-Rooter PowerShell Module
echo $PythonPath = "%PYTHON_PATH%"
echo $MainPy = "%MAIN_PY%"
echo.
echo function Invoke-WebRooter {
echo     param^([Parameter(ValueFromRemainingArguments = ^$true^)] [string[]]^$Args^)
echo     ^& $PythonPath $MainPy @Args
echo }
echo.
echo function Invoke-WebDoctor {
echo     ^& $PythonPath $MainPy "--doctor"
echo }
echo.
echo Set-Alias -Name wr -Value Invoke-WebRooter -Scope Global
echo Set-Alias -Name webdoctor -Value Invoke-WebDoctor -Scope Global
echo Export-ModuleMember -Function Invoke-WebRooter, Invoke-WebDoctor -Alias wr, webdoctor
) > "%PS_MODULE%"

echo   已创建: %PS_MODULE%

set PS_PROFILE=%USERPROFILE%\Documents\WindowsPowerShell\Microsoft.PowerShell_profile.ps1
if not exist "%PS_PROFILE%" (
    echo # PowerShell Profile > "%PS_PROFILE%"
)
findstr /C:"Import-Module WebRooter" "%PS_PROFILE%" >nul
if errorlevel 1 (
    echo.>> "%PS_PROFILE%"
    echo # Web-Rooter Module>> "%PS_PROFILE%"
    echo Import-Module WebRooter>> "%PS_PROFILE%"
)

echo [4/4] 写入 Claude 权限（Desktop + Code）...
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
"$mainPy='%MAIN_PY%'; $items=@('Bash(wr:*)','Bash(web*:*)',('Bash(python:'+ $mainPy + ':*)')); $targets=@(@{Path='$env:APPDATA\Claude\settings.json';Mode='desktop'},@{Path='$env:USERPROFILE\.claude\settings.json';Mode='code'}); foreach($t in $targets){ $path=$ExecutionContext.InvokeCommand.ExpandString($t.Path); $dir=Split-Path -Parent $path; if(-not (Test-Path $dir)){ [void](New-Item -ItemType Directory -Path $dir -Force) }; if(Test-Path $path){ try{ $raw=Get-Content -Raw $path; $cfg=ConvertFrom-Json $raw } catch { $cfg=[pscustomobject]@{} } } else { $cfg=[pscustomobject]@{} }; if($t.Mode -eq 'desktop'){ if(-not $cfg.permissions){ Add-Member -InputObject $cfg -NotePropertyName permissions -NotePropertyValue ([pscustomobject]@{}) }; if(-not ($cfg.permissions.PSObject.Properties.Name -contains 'allow')){ Add-Member -InputObject $cfg.permissions -NotePropertyName allow -NotePropertyValue @() }; foreach($i in $items){ if(-not ($cfg.permissions.allow -contains $i)){ $cfg.permissions.allow += $i } } } else { if(-not ($cfg.PSObject.Properties.Name -contains 'allow')){ Add-Member -InputObject $cfg -NotePropertyName allow -NotePropertyValue @() }; foreach($i in $items){ if(-not ($cfg.allow -contains $i)){ $cfg.allow += $i } } }; $json=ConvertTo-Json $cfg -Depth 20; Set-Content -Path $path -Value $json -Encoding UTF8; Write-Host ('  已更新: ' + $path) }"

echo [附加] 注入 AI 工具 Skills（Claude/Cursor/OpenCode/OpenClaw）...
"%PYTHON_PATH%" "%REPO_ROOT%\scripts\setup_ai_skills.py" --repo-root "%REPO_ROOT%"
if errorlevel 1 (
    echo   [警告] Skills 注入失败，可手动执行:
    echo          "%PYTHON_PATH%" "%REPO_ROOT%\scripts\setup_ai_skills.py" --repo-root "%REPO_ROOT%"
)

echo.
echo ========================================
echo   安装完成
echo ========================================
echo.
echo 可用命令:
echo   wr help
echo   wr doctor
echo   wr visit https://example.com
echo   wr quick "量化交易 因子"
echo.
echo 下一步:
echo 1. 重启终端
echo 2. 运行 wr doctor
echo 3. 在 Claude Code 输入 /tools
echo.
if "%NO_PAUSE%"=="0" pause

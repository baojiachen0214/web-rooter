@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

set SCRIPT_DIR=%~dp0
set EXE_SRC=%SCRIPT_DIR%web-rooter.exe
set TARGET_ROOT=%LOCALAPPDATA%\web-rooter\standalone
set TARGET_EXE=%TARGET_ROOT%\web-rooter.exe
set BIN_DIR=%LOCALAPPDATA%\web-rooter\bin
set WR_BAT=%BIN_DIR%\wr.bat

echo ========================================
echo Web-Rooter Standalone Install (Windows)
echo ========================================
echo.

if not exist "%EXE_SRC%" (
    echo [ERROR] web-rooter.exe not found next to installer.
    pause
    exit /b 1
)

if not exist "%TARGET_ROOT%" mkdir "%TARGET_ROOT%"
copy /Y "%EXE_SRC%" "%TARGET_EXE%" >nul
if errorlevel 1 (
    echo [ERROR] failed to copy web-rooter.exe
    pause
    exit /b 1
)

if not exist "%BIN_DIR%" mkdir "%BIN_DIR%"
(
echo @echo off
echo "%TARGET_EXE%" %%*
) > "%WR_BAT%"

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
"$target='%BIN_DIR%'; $current=[Environment]::GetEnvironmentVariable('Path','User'); if([string]::IsNullOrEmpty($current)){ $newPath=$target } elseif(($current -split ';') -contains $target){ $newPath=$current } else { $newPath=$current+';'+$target }; [Environment]::SetEnvironmentVariable('Path',$newPath,'User')"

echo [1/3] Installed executable: %TARGET_EXE%
echo [2/3] Installed command wrapper: %WR_BAT%
echo [3/3] Updating AI tool skill files + Claude MCP (best-effort)...

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
"$wr='%TARGET_EXE%'; ^
$skill=@' ^
# Web-Rooter CLI Skills ^
Use `wr skills --resolve \"<goal>\" --compact`, then `wr do-plan`, then `wr do --dry-run`, then `wr do`. ^
'@; ^
$paths=@( ^
  Join-Path $env:USERPROFILE '.claude\skills\web-rooter-cli.md', ^
  Join-Path $env:USERPROFILE '.cursor\rules\web-rooter-cli.mdc', ^
  Join-Path $env:USERPROFILE '.opencode\AGENTS.md', ^
  Join-Path $env:USERPROFILE '.openclaw\AGENTS.md' ^
); ^
foreach($p in $paths){ $d=Split-Path -Parent $p; if(-not (Test-Path $d)){ New-Item -ItemType Directory -Path $d -Force | Out-Null }; Set-Content -Path $p -Value $skill -Encoding UTF8 }; ^
$cfgPath=Join-Path $env:APPDATA 'Claude\config.json'; ^
$cfgDir=Split-Path -Parent $cfgPath; if(-not (Test-Path $cfgDir)){ New-Item -ItemType Directory -Path $cfgDir -Force | Out-Null }; ^
if(Test-Path $cfgPath){ try{ $cfg=ConvertFrom-Json (Get-Content -Raw $cfgPath) } catch { $cfg=[pscustomobject]@{} } } else { $cfg=[pscustomobject]@{} }; ^
if(-not $cfg.mcpServers){ Add-Member -InputObject $cfg -NotePropertyName mcpServers -NotePropertyValue ([pscustomobject]@{}) }; ^
$server=[pscustomobject]@{ command=$wr; args=@('--mcp'); env=[pscustomobject]@{ PYTHONUNBUFFERED='1'; PYTHONIOENCODING='utf-8' } }; ^
Add-Member -InputObject $cfg.mcpServers -NotePropertyName 'web-rooter' -NotePropertyValue $server -Force; ^
$cfg | ConvertTo-Json -Depth 20 | Set-Content $cfgPath -Encoding UTF8"

echo.
echo Install completed.
echo Restart terminal, then run:
echo   wr --version
echo   wr doctor
echo.
pause
endlocal


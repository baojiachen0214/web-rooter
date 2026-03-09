@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

set SCRIPT_DIR=%~dp0
set SCRIPT_DIR=%SCRIPT_DIR:~0,-1%
for %%I in ("%SCRIPT_DIR%\..\..") do set REPO_ROOT=%%~fI
set MAIN_PY=%REPO_ROOT%\main.py
set USER_BIN_DIR=%LOCALAPPDATA%\web-rooter\bin
set WR_SCRIPT=%USER_BIN_DIR%\wr.bat

echo ========================================
echo   Web-Rooter CLI 卸载（用户级）
echo ========================================
echo.

echo [1/4] 删除 wr 命令...
if exist "%WR_SCRIPT%" (
    del /f /q "%WR_SCRIPT%"
    echo   已删除: %WR_SCRIPT%
) else (
    echo   未找到: %WR_SCRIPT%
)

echo [2/4] 清理用户 PATH...
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
"$target='%USER_BIN_DIR%'; $current=[Environment]::GetEnvironmentVariable('Path','User'); if([string]::IsNullOrEmpty($current)){ exit 0 }; $parts=@(); foreach($p in ($current -split ';')){ if($p -and $p -ne $target){ $parts += $p } }; [Environment]::SetEnvironmentVariable('Path',($parts -join ';'),'User'); Write-Host '  已清理用户 PATH（重启终端后生效）'"

echo [3/4] 删除 PowerShell 模块...
set PS_MODULE_DIR=%USERPROFILE%\Documents\WindowsPowerShell\Modules\WebRooter
if exist "%PS_MODULE_DIR%" (
    rmdir /s /q "%PS_MODULE_DIR%"
    echo   已删除: %PS_MODULE_DIR%
) else (
    echo   未找到: %PS_MODULE_DIR%
)

set PS_PROFILE=%USERPROFILE%\Documents\WindowsPowerShell\Microsoft.PowerShell_profile.ps1
if exist "%PS_PROFILE%" (
    powershell -NoProfile -ExecutionPolicy Bypass -Command ^
    "$path='%PS_PROFILE%'; $lines=Get-Content $path; $new=@(); foreach($l in $lines){ if($l -notmatch 'Import-Module WebRooter' -and $l -notmatch '# Web-Rooter Module'){ $new += $l } }; Set-Content -Path $path -Value $new -Encoding UTF8; Write-Host '  已清理 profile 引用'"
)

echo [4/4] 清理 Claude 权限...
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
"$mainPy='%MAIN_PY%'; $items=@('Bash(wr:*)','Bash(web*:*)',('Bash(python:'+ $mainPy + ':*)')); $targets=@(@{Path='$env:APPDATA\Claude\settings.json';Mode='desktop'},@{Path='$env:USERPROFILE\.claude\settings.json';Mode='code'}); foreach($t in $targets){ $path=$ExecutionContext.InvokeCommand.ExpandString($t.Path); if(-not (Test-Path $path)){ continue }; try{ $cfg=ConvertFrom-Json (Get-Content -Raw $path) } catch { continue }; if($t.Mode -eq 'desktop' -and $cfg.permissions -and $cfg.permissions.allow){ $new=@(); foreach($a in $cfg.permissions.allow){ if(-not ($items -contains $a)){ $new += $a } }; $cfg.permissions.allow = $new } elseif($t.Mode -eq 'code' -and $cfg.allow){ $new=@(); foreach($a in $cfg.allow){ if(-not ($items -contains $a)){ $new += $a } }; $cfg.allow = $new }; Set-Content -Path $path -Value (ConvertTo-Json $cfg -Depth 20) -Encoding UTF8; Write-Host ('  已更新: ' + $path) }"

echo.
echo ========================================
echo   卸载完成
echo ========================================
echo.
pause

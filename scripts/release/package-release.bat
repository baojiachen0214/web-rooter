@echo off
setlocal
cd /d "%~dp0\..\.."
python scripts\release\build_standalone_bundle.py %*

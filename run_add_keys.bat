@echo off
title Nusuk Add Keys Automation
echo ========================================================
echo         Nusuk Challenge Key Automation Runner
echo ========================================================
echo.
if exist "%~dp0nusuk_add_keys.exe" (
  "%~dp0nusuk_add_keys.exe" "%~dp0keys.txt" %*
) else (
  python nusuk_add_keys.py "%~dp0keys.txt" %*
)
echo.
pause

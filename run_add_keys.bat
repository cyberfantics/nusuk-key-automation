@echo off
title Nusuk Add Keys Automation
echo ========================================================
echo         Nusuk Challenge Key Automation Runner
echo ========================================================
echo.
python nusuk_add_keys.py keys.txt %*
echo.
pause

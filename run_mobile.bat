@echo off
cd /d "%~dp0\web"
title Lecture Audio Mobile Server

echo ========================================================
echo   Starting Mobile Web Server...
echo ========================================================

python server.py
if %errorlevel% neq 0 (
    echo.
    echo [ERROR] Failed to start server.
    pause
)

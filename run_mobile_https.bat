@echo off
cd /d "%~dp0\web"
title Lecture Audio Mobile HTTPS Server (PWA Installable)

echo ========================================================
echo   Starting Mobile HTTPS Server for PWA Installation...
echo ========================================================
echo.

:: Start python server in background
start "" /b python server.py

echo Waiting for local server to start...
timeout /t 2 /nobreak >nul

echo Starting secure HTTPS tunnel...
echo Open the generated HTTPS URL on your smartphone Chrome/Safari.
echo.
npx -y localtunnel --port 8080

pause

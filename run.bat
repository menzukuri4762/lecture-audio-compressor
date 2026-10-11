@echo off
cd /d "%~dp0"
title Lecture Audio AI Compressor

echo ========================================================
echo   Lecture Audio AI Compressor (100MB Target)
echo ========================================================
echo Starting application...

:: Check and install windnd if missing
python -c "import windnd" 2>nul
if %errorlevel% neq 0 (
    echo Installing required library: windnd...
    pip install windnd
)

:: Launch python app.py
python app.py
if %errorlevel% neq 0 (
    echo.
    echo ========================================================
    echo Application exited with an error.
    echo ========================================================
    pause
)

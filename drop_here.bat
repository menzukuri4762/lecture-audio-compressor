@echo off
cd /d "%~dp0"
title Lecture Audio Auto Compressor

if "%~1"=="" (
    echo ========================================================
    echo   Lecture Audio Compressor - Drag and Drop Tool
    echo ========================================================
    echo How to use:
    echo   Drag and drop your audio file (.m4a, .mp3, .wav, etc.)
    echo   directly onto this batch file icon.
    echo.
    echo   Or run "run.bat" to open the GUI window.
    echo ========================================================
    echo.
    pause
    exit /b 0
)

echo ========================================================
echo   Compressing audio to under 100MB MP3...
echo ========================================================

python cli.py %*

echo.
echo ========================================================
echo Finished! Press any key to close.
echo ========================================================
pause

@echo off
setlocal
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\session_python.ps1" -Action prepare %*
if errorlevel 1 (
    echo.
    echo  PREPARE FAILED. No launch should be attempted until the error above is fixed.
    pause
    exit /b 1
)
echo.
echo  Python-free launch state verified. Launch Session or Push Changes in UEFN now.
pause
exit /b 0

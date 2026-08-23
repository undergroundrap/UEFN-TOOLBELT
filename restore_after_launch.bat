@echo off
setlocal
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\session_python.ps1" -Action restore %*
if errorlevel 1 (
    echo.
    echo  RESTORE FAILED. The recoverable stash was left in place; read the error above.
    pause
    exit /b 1
)
echo.
echo  Toolbelt Python restored. Continue editing normally.
pause
exit /b 0

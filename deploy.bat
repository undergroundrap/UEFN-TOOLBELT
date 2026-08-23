@echo off
setlocal enabledelayedexpansion

echo.
echo  ==========================================
echo    UEFN TOOLBELT  ^|  Deploy Script
echo  ==========================================
echo.

:: ── Find Fortnite Projects folder ─────────────────────────────────────────────
set "FP_ROOT=%USERPROFILE%\Documents\Fortnite Projects"
if not exist "%FP_ROOT%\" (
    echo  ERROR: Could not find your Fortnite Projects folder at:
    echo    %FP_ROOT%
    echo.
    echo  Make sure UEFN is installed and you have created at least one project.
    pause
    exit /b 1
)

:: ── List available UEFN projects ───────────────────────────────────────────────
set /a count=0
echo  Found UEFN projects:
echo.
for /d %%D in ("%FP_ROOT%\*") do (
    if exist "%%~fD\*.uefnproject" (
        set /a count+=1
        set "proj_!count!=%%~nxD"
        echo    [!count!]  %%~nxD
    )
)

if %count%==0 (
    echo  No projects found. Create a project in UEFN first.
    pause
    exit /b 1
)

echo.
if %count%==1 (
    set choice=1
    echo  Only one project found — selecting it automatically.
) else (
    set /p choice="  Enter the number of the project to deploy to: "
)

set "PROJECT=!proj_%choice%!"
if "!PROJECT!"=="" (
    echo  Invalid selection.
    pause
    exit /b 1
)

set "DEST=%FP_ROOT%\!PROJECT!"
echo.
echo  Deploying to:  !DEST!
echo.

:: ── Copy files ────────────────────────────────────────────────────────────────
echo  [1/4]  Copying UEFN_Toolbelt package...
xcopy /E /I /Y "%~dp0Content\Python\UEFN_Toolbelt" "!DEST!\Content\Python\UEFN_Toolbelt" >nul
if errorlevel 1 ( echo         FAILED & goto :error ) else ( echo         OK )

echo  [2/4]  Copying init_unreal.py...
xcopy /Y "%~dp0init_unreal.py" "!DEST!\Content\Python\" >nul
if errorlevel 1 ( echo         FAILED & goto :error ) else ( echo         OK )

echo  [3/4]  Copying verse-book reference without Python helpers...
if exist "%~dp0verse-book\" (
    robocopy "%~dp0verse-book" "!DEST!\verse-book" /E /XF *.py *.pyc /XD .git __pycache__ >nul
    set "ROBOCOPY_EXIT=!ERRORLEVEL!"
    if !ROBOCOPY_EXIT! GEQ 8 ( echo         FAILED & goto :error ) else ( echo         OK )
) else (
    echo         SKIPPED ^(verse-book is not cloned^)
)

:: -- Build stamp --------------------------------------------------------------
:: Written AFTER the copy, straight into the destination, so it describes what is
:: actually deployed rather than what the repo happens to contain. Two test runs
:: were lost to a project silently sitting 40 minutes behind on a different
:: build; this makes that visible in the editor instead of needing a file audit.
echo  [4/4]  Writing build stamp...
set "GIT_SHA=unknown"
set "GIT_DIRTY="
set "STAMP_TIME=unknown"
for /f "delims=" %%i in ('git -C "%~dp0." rev-parse --short HEAD 2^>nul') do set "GIT_SHA=%%i"
for /f "delims=" %%i in ('git -C "%~dp0." status --porcelain 2^>nul') do set "GIT_DIRTY=+dirty"
for /f "delims=" %%i in ('powershell -NoProfile -Command "Get-Date -Format s" 2^>nul') do set "STAMP_TIME=%%i"
set "STAMP_FILE=!DEST!\Content\Python\UEFN_Toolbelt\_build_stamp.json"
> "!STAMP_FILE!" (
    echo {
    echo   "commit": "!GIT_SHA!!GIT_DIRTY!",
    echo   "deployed_at": "!STAMP_TIME!",
    echo   "project": "!PROJECT!"
    echo }
)
if exist "!STAMP_FILE!" ( echo         OK  ^(!GIT_SHA!!GIT_DIRTY! -^> !PROJECT!^) ) else ( echo         FAILED & goto :error )

:: ── PySide6 check — tries multiple install locations ─────────────────────────
echo.
set "UE_PYTHON="
for %%P in (
    "C:\Program Files\Epic Games\Fortnite\Engine\Binaries\ThirdParty\Python3\Win64\python.exe"
    "C:\Program Files (x86)\Epic Games\Fortnite\Engine\Binaries\ThirdParty\Python3\Win64\python.exe"
    "D:\Epic Games\Fortnite\Engine\Binaries\ThirdParty\Python3\Win64\python.exe"
    "E:\Epic Games\Fortnite\Engine\Binaries\ThirdParty\Python3\Win64\python.exe"
) do (
    if exist %%P (
        if "!UE_PYTHON!"=="" set "UE_PYTHON=%%~P"
    )
)

if not "!UE_PYTHON!"=="" (
    echo  UE Python: !UE_PYTHON!
    "!UE_PYTHON!" -c "import PySide6" >nul 2>&1
    if errorlevel 1 (
        echo  PySide6 not installed. Installing now...
        "!UE_PYTHON!" -m pip install PySide6 --quiet
        if errorlevel 1 (
            echo  WARNING: PySide6 install failed. Dashboard UI may not work.
        ) else (
            echo  PySide6 installed OK.
        )
    ) else (
        echo  PySide6 already installed.
    )
) else (
    echo  NOTE: Could not find UE Python — tried C:, D:, E: drives.
    echo  Run install.py for a full drive scan, or install manually in a terminal:
    echo    "^<UE_PATH^>\Engine\Binaries\ThirdParty\Python3\Win64\python.exe" -m pip install PySide6
)

:: ── Done ──────────────────────────────────────────────────────────────────────
:: The selection loop needs delayed expansion, but leaving it enabled here eats
:: literal exclamation marks. That turned "Syntax passing != working" into the
:: exact opposite in the final safety banner and erased "!! BEFORE COMMITTING !!".
setlocal DisableDelayedExpansion
echo.
echo ==========================================
echo   All files deployed successfully!
echo ==========================================
echo.
echo BEFORE LAUNCH SESSION OR PUSH CHANGES:
echo   Run prepare_launch.bat to move every .py outside the UEFN project.
echo   After the upload finishes, run restore_after_launch.bat.
echo   UEFN 42.00 rejects project .py files for the VKCreateUGC role.
echo.
echo HOT-RELOAD COMMANDS (paste into UEFN Python console):
echo.
echo [STANDARD] Reload + open dashboard:
echo import sys; [sys.modules.pop(k) for k in list(sys.modules) if "UEFN_Toolbelt" in k]; import UEFN_Toolbelt as tb; tb.register_all_tools(); tb.launch_qt()
echo.
echo [SMOKE TEST] Reload + verify health:
echo import sys; [sys.modules.pop(k) for k in list(sys.modules) if "UEFN_Toolbelt" in k]; import UEFN_Toolbelt as tb; tb.register_all_tools(); tb.run("toolbelt_smoke_test")
echo.
echo [INTEGRATION TEST] WARNING - invasive, use a clean template only:
echo import sys; [sys.modules.pop(k) for k in list(sys.modules) if "UEFN_Toolbelt" in k]; import UEFN_Toolbelt as tb; tb.register_all_tools(); tb.run("toolbelt_integration_test")
echo.
echo [MASTER SYNC] Reload + sync docs ^& Verse IQ:
echo import sys; [sys.modules.pop(k) for k in list(sys.modules) if "UEFN_Toolbelt" in k]; import UEFN_Toolbelt as tb; tb.register_all_tools(); tb.run("api_sync_master")
echo.
echo [VERSE GRAPH] Reload + open device graph:
echo import sys; [sys.modules.pop(k) for k in list(sys.modules) if "UEFN_Toolbelt" in k]; import UEFN_Toolbelt as tb; tb.register_all_tools(); tb.run("verse_graph_open")
echo.
echo ==========================================
echo   !! BEFORE COMMITTING !!
echo ==========================================
echo   1. Run drift check (catches stale counts + versions):
echo      python scripts/drift_check.py
echo   2. Run the SMOKE TEST command above in UEFN.
echo   3. Confirm the dashboard opens and your change works.
echo   Only run "git commit" after you see it working live.
echo   Syntax passing != working in the editor.
echo ==========================================
echo.
echo TIP: Only restart UEFN if you changed init_unreal.py.
echo      New project deployment? RESTART UEFN for the menu to appear.
echo.
pause
exit /b 0

:error
echo.
echo  Deploy failed. Check that UEFN is not currently open and locking the files.
pause
exit /b 1

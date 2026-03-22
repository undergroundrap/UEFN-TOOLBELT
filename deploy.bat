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
    set /a count+=1
    set "proj_!count!=%%~nxD"
    echo    [!count!]  %%~nxD
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

echo  [3/4]  Copying tests folder...
xcopy /E /I /Y "%~dp0tests" "!DEST!\tests" >nul
if errorlevel 1 ( echo         FAILED & goto :error ) else ( echo         OK )

echo  [4/4]  Copying verse-book spec...
xcopy /E /I /H /Y "%~dp0verse-book" "!DEST!\verse-book" >nul
if errorlevel 1 ( echo         FAILED & goto :error ) else ( echo         OK )

:: ── PySide6 check ─────────────────────────────────────────────────────────────
echo.
set "UE_PYTHON=C:\Program Files\Epic Games\Fortnite\Engine\Binaries\ThirdParty\Python3\Win64\python.exe"
if exist "%UE_PYTHON%" (
    "%UE_PYTHON%" -c "import PySide6" >nul 2>&1
    if errorlevel 1 (
        echo  PySide6 not installed. Installing now...
        "%UE_PYTHON%" -m pip install PySide6 --quiet
        if errorlevel 1 (
            echo  WARNING: PySide6 install failed. Dashboard UI may not work.
        ) else (
            echo  PySide6 installed OK.
        )
    ) else (
        echo  PySide6 already installed.
    )
) else (
    echo  NOTE: Could not find UEFN Python at expected path.
    echo  If the dashboard doesn't open, manually run:
    echo    "^<UE_INSTALL^>\Engine\Binaries\ThirdParty\Python3\Win64\python.exe" -m pip install PySide6
)

:: ── Done ──────────────────────────────────────────────────────────────────────
echo.
echo ==========================================
echo   All files deployed successfully!
echo ==========================================
echo.
echo HOT-RELOAD WORKFLOW (No UEFN Restart Required):
echo Copy and paste this exact line into the UEFN Python console to refresh the toolbelt:
echo.
echo import sys; [sys.modules.pop(k) for k in list(sys.modules) if "UEFN_Toolbelt" in k]; import UEFN_Toolbelt as tb; tb.register_all_tools(); tb.launch_qt()
echo.
echo BUNDLE: HOT-RELOAD + INTEGRATION TEST (WARNING: INVASIVE - Use clean template):
echo import sys; [sys.modules.pop(k) for k in list(sys.modules) if "UEFN_Toolbelt" in k]; import UEFN_Toolbelt as tb; tb.register_all_tools(); tb.run("toolbelt_integration_test")
echo.
echo BUNDLE: HOT-RELOAD + SMOKE TEST:
echo import sys; [sys.modules.pop(k) for k in list(sys.modules) if "UEFN_Toolbelt" in k]; import UEFN_Toolbelt as tb; tb.register_all_tools(); tb.run("toolbelt_smoke_test")
echo.
echo BUNDLE: HOT-RELOAD + MASTER SYNC (Sync Docs ^& Verse IQ):
echo import sys; [sys.modules.pop(k) for k in list(sys.modules) if "UEFN_Toolbelt" in k]; import UEFN_Toolbelt as tb; tb.register_all_tools(); tb.run("api_sync_master")
echo.
echo BUNDLE: HOT-RELOAD + VERSE DEVICE GRAPH (Iterate on graph window):
echo import sys; [sys.modules.pop(k) for k in list(sys.modules) if "UEFN_Toolbelt" in k]; import UEFN_Toolbelt as tb; tb.register_all_tools(); tb.run("verse_graph_open")
echo.
echo TIP: You only need to restart UEFN if you've changed init_unreal.py.
echo      **NOTE: If this is a new project deployment, RESTART UEFN for the Toolbelt to appear.**
echo.
pause
exit /b 0

:error
echo.
echo  Deploy failed. Check that UEFN is not currently open and locking the files.
pause
exit /b 1

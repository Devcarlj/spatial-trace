@echo off
setlocal
rem Double-click friendly wrapper around run.ps1.
rem Forwards any arguments, e.g.:  run.bat -Mode live
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0run.ps1" %*
set "EXITCODE=%ERRORLEVEL%"
if not "%EXITCODE%"=="0" (
    echo.
    echo SpatialTrace launcher exited with code %EXITCODE%.
    pause
)
exit /b %EXITCODE%


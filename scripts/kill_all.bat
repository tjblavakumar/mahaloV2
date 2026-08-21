@echo off
echo Stopping all MAHALO services...
echo.

REM Kill all Python processes (this will stop all servers)
taskkill /F /IM python.exe 2>nul
if %errorlevel% == 0 (
    echo Python processes stopped.
) else (
    echo No Python processes found running.
)

REM Kill all Node processes (frontend)
taskkill /F /IM node.exe 2>nul
if %errorlevel% == 0 (
    echo Node processes stopped.
) else (
    echo No Node processes found running.
)

echo.
echo All MAHALO services have been stopped.
echo You can now run start_all.bat to restart with fresh code.
echo.
pause

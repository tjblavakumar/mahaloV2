@echo off
REM ============================================================
REM MAHALO - Reset Demo Data (Windows)
REM ============================================================
echo.
echo ============================================================
echo    MAHALO - Reset Demo Data for MahaloPay
echo ============================================================
echo.

REM Check if virtual environment exists
if not exist "%~dp0..\venv\Scripts\activate.bat" (
    echo [ERROR] Virtual environment not found!
    echo Please complete Phase 0 setup first.
    pause
    exit /b 1
)

echo This will:
echo   1. Drop all database tables
echo   2. Recreate schema
echo   3. Populate with fresh MahaloPay demo data
echo.
echo WARNING: All current data will be lost!
echo.
echo Press any key to continue or Ctrl+C to cancel...
pause > nul
echo.

echo [INFO] Activating virtual environment...
call "%~dp0..\venv\Scripts\activate.bat"

echo.
echo [1/3] Resetting database...
python -m backend.utils.reset_data

if errorlevel 1 (
    echo.
    echo [ERROR] Failed to reset database!
    echo Check the error messages above.
    pause
    exit /b 1
)

echo.
echo ============================================================
echo Demo data reset complete!
echo ============================================================
echo.
echo MahaloPay demo data loaded:
echo   - 5 users (alice_dev, bob_pm, charlie_qa, diana_dev, eve_exec)
echo   - Sprint 23 with payment processing stories
echo   - Bugs and incidents for payment service
echo   - Logs showing transaction errors
echo.
echo Ready for demo!
echo.
pause

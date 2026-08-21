@echo off
REM ============================================================
REM MAHALO - Run All Tests (Windows)
REM ============================================================
echo.
echo ============================================================
echo    MAHALO - Run Automated Tests
echo ============================================================
echo.

REM Check if virtual environment exists
if not exist "%~dp0..\venv\Scripts\activate.bat" (
    echo [ERROR] Virtual environment not found!
    echo Please complete Phase 0 setup first.
    pause
    exit /b 1
)

echo [INFO] Activating virtual environment...
call "%~dp0..\venv\Scripts\activate.bat"

echo.
echo [INFO] Running pytest with coverage...
echo.

REM Change to project root directory
cd /d "%~dp0.."

REM Run pytest with coverage
pytest tests/ -v --cov=backend --cov=agents --cov=api --cov-report=html --cov-report=term

if errorlevel 1 (
    echo.
    echo [WARNING] Some tests failed!
    echo Check the output above for details.
) else (
    echo.
    echo ============================================================
    echo All tests passed!
    echo ============================================================
)

echo.
echo Coverage report generated in: htmlcov\index.html
echo.
echo Press any key to open coverage report in browser...
pause > nul

if exist "htmlcov\index.html" (
    start htmlcov\index.html
)

echo.
pause

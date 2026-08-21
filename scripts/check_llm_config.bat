@echo off
echo ============================================================
echo LLM Test Data Generator - Configuration Check
echo ============================================================
echo.

cd /d "%~dp0.."

if not exist ".venv\Scripts\activate.bat" (
    if not exist "venv\Scripts\activate.bat" (
        echo [ERROR] Virtual environment not found.
        echo Create it with: python -m venv venv
        pause
        exit /b 1
    )
    set VENV_PATH=venv
) else (
    set VENV_PATH=.venv
)

call "%VENV_PATH%\Scripts\activate.bat"
python -c "import sys; sys.path.insert(0, '.'); from backend.config import settings; print('API Key:', 'SET' if settings.ONE_MIN_AI_API_KEY else 'NOT SET'); print('Base URL:', settings.ONE_MIN_AI_BASE_URL); print('Model:', settings.LITELLM_MODEL)"

echo.
echo ============================================================
if exist ".env" (
    echo Checking .env file...
    findstr /I "ONE_MIN_AI_API_KEY" .env >nul
    if errorlevel 1 (
        echo [WARNING] ONE_MIN_AI_API_KEY not found in .env
        echo.
        echo To fix: Add this line to your .env file:
        echo ONE_MIN_AI_API_KEY=your_api_key_here
    ) else (
        echo [OK] ONE_MIN_AI_API_KEY found in .env
    )
) else (
    echo [WARNING] .env file not found
    echo.
    echo To fix: Create .env file with:
    echo ONE_MIN_AI_API_KEY=your_api_key_here
)
echo ============================================================
echo.
pause

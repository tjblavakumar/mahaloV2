@echo off
setlocal

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

echo ============================================================
echo MAHALO Enhanced Test Data Generation (LLM-Powered)
echo ============================================================
echo.

:: Check if user passed custom arguments
if "%~1"=="" (
    echo Generating realistic demo data with:
    echo   - 10 JIRA stories with detailed descriptions
    echo   - 5 JIRA bugs with reproduction steps
    echo   - 2 sprints
    echo   - 8 ServiceNow incidents
    echo   - 6 deployments
    echo   - 15 Splunk logs
    echo.
    echo This may take 10-30 seconds...
    echo.
    call "%VENV_PATH%\Scripts\activate.bat"
    python -m backend.utils.generate_test_data_llm --quick
) else (
    echo Generating custom test data...
    echo Arguments: %*
    echo.
    echo This may take 30-120 seconds depending on volume...
    echo.
    call "%VENV_PATH%\Scripts\activate.bat"
    python -m backend.utils.generate_test_data_llm %*
)

echo.
echo Done!
pause

@echo off
REM ============================================================
REM MAHALO - Start All Services (Windows)
REM ============================================================
echo.
echo ============================================================
echo    MAHALO - Multi-Agent Harness for Agile Lifecycle
echo    Starting All Services for MahaloPay Demo
echo ============================================================
echo.

REM ============================================================
REM Configure Proxy Settings for Corporate Environments
REM ============================================================
echo [INFO] Configuring proxy settings...

REM Preserve existing NO_PROXY and add localhost if not present
if defined NO_PROXY (
    echo %NO_PROXY% | findstr /C:"localhost" >nul
    if errorlevel 1 (
        SET "NO_PROXY=localhost,127.0.0.1,%NO_PROXY%"
        echo [INFO] Added localhost to existing NO_PROXY
    ) else (
        echo [INFO] localhost already in NO_PROXY
    )
) else (
    SET "NO_PROXY=localhost,127.0.0.1"
    echo [INFO] Set NO_PROXY for localhost
)

REM Display proxy configuration
if defined HTTP_PROXY (
    echo [INFO] HTTP_PROXY: %HTTP_PROXY%
    echo [INFO] NO_PROXY: %NO_PROXY%
    echo [INFO] Proxy configured - localhost will bypass proxy
) else (
    echo [INFO] No proxy detected - direct connections will be used
)
echo.

REM Check if virtual environment exists
if not exist "%~dp0..\venv\Scripts\activate.bat" (
    echo [ERROR] Virtual environment not found!
    echo.
    echo Please complete Phase 0 setup first:
    echo   1. cd mahalo
    echo   2. python -m venv venv
    echo   3. venv\Scripts\activate
    echo   4. pip install -r requirements.txt
    echo.
    pause
    exit /b 1
)

echo [INFO] Checking Python environment...
call "%~dp0..\venv\Scripts\python.exe" --version
if errorlevel 1 (
    echo [ERROR] Python not found in virtual environment!
    pause
    exit /b 1
)
echo.

echo ============================================================
echo Ready to start services. Press any key to continue...
echo ============================================================
pause > nul
echo.

echo [1/8] Starting JIRA Mock API (Port 5001)...
start "MAHALO - JIRA API (5001)" cmd /k "cd /d %~dp0.. && venv\Scripts\activate && python -m uvicorn backend.jira.app:app --host 0.0.0.0 --port 5001"
timeout /t 5 /nobreak > nul

echo [2/8] Starting ServiceNow Mock API (Port 5002)...
start "MAHALO - ServiceNow API (5002)" cmd /k "cd /d %~dp0.. && venv\Scripts\activate && python -m uvicorn backend.servicenow.app:app --host 0.0.0.0 --port 5002"
timeout /t 5 /nobreak > nul

echo [3/8] Starting Splunk Mock API (Port 5003)...
start "MAHALO - Splunk API (5003)" cmd /k "cd /d %~dp0.. && venv\Scripts\activate && python -m uvicorn backend.splunk.app:app --host 0.0.0.0 --port 5003"
echo.
echo [INFO] Waiting for Mock APIs to fully initialize (30 seconds)...
timeout /t 30 /nobreak > nul
echo.

echo [4/8] Starting JIRA MCP Server (Port 6001)...
start "MAHALO - JIRA MCP (6001)" cmd /k "cd /d %~dp0.. && venv\Scripts\activate && python -m mcp_servers.jira_mcp.server"
timeout /t 5 /nobreak > nul

echo [5/8] Starting ServiceNow MCP Server (Port 6002)...
start "MAHALO - ServiceNow MCP (6002)" cmd /k "cd /d %~dp0.. && venv\Scripts\activate && python -m mcp_servers.servicenow_mcp.server"
timeout /t 5 /nobreak > nul

echo [6/8] Starting Splunk MCP Server (Port 6003)...
start "MAHALO - Splunk MCP (6003)" cmd /k "cd /d %~dp0.. && venv\Scripts\activate && python -m mcp_servers.splunk_mcp.server"
timeout /t 5 /nobreak > nul

echo [7/8] Starting Main API Gateway (Port 8000)...
start "MAHALO - Main API (8000)" cmd /k "cd /d %~dp0.. && venv\Scripts\activate && python -m uvicorn api.main:app --host 0.0.0.0 --port 8000"
timeout /t 5 /nobreak > nul

echo [8/8] Starting React Frontend (Port 3000)...
start "MAHALO - Frontend (3000)" cmd /k "cd /d %~dp0..\frontend && npm start"
timeout /t 5 /nobreak > nul

echo.
echo ============================================================
echo All services started in separate terminal windows!
echo ============================================================
echo.
echo Check each terminal window for startup messages and errors.
echo.
echo Services:
echo   [Mock APIs]
echo   - JIRA API............: http://localhost:5001/docs
echo   - ServiceNow API......: http://localhost:5002/docs
echo   - Splunk API..........: http://localhost:5003/docs
echo.
echo   [MCP Servers]
echo   - JIRA MCP............: Port 6001
echo   - ServiceNow MCP......: Port 6002
echo   - Splunk MCP..........: Port 6003
echo.
echo   [Main Services]
echo   - Main API Gateway....: http://localhost:8000/docs
echo   - Frontend UI.........: http://localhost:3000
echo.
echo ============================================================
echo.
echo Press any key to open the MAHALO UI in your browser...
pause > nul
start http://localhost:3000
echo.
echo Done! MAHALO is ready for demo.
echo.

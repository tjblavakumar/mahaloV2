@echo off
REM ============================================================
REM MAHALO - Stop All Services (Windows)
REM ============================================================
echo.
echo ============================================================
echo    MAHALO - Stopping All Services
echo ============================================================
echo.

echo This will close all MAHALO service windows.
echo.
echo Services to stop:
echo   - JIRA API (5001)
echo   - ServiceNow API (5002)
echo   - Splunk API (5003)
echo   - JIRA MCP (6001)
echo   - ServiceNow MCP (6002)
echo   - Splunk MCP (6003)
echo   - Main API (8000)
echo   - Frontend (3000)
echo.
echo Press any key to continue...
pause > nul
echo.

echo [INFO] Closing all MAHALO terminal windows...

REM Kill processes by window title
taskkill /FI "WINDOWTITLE eq MAHALO - JIRA API (5001)" /IM cmd.exe /F 2>nul
taskkill /FI "WINDOWTITLE eq MAHALO - ServiceNow API (5002)" /IM cmd.exe /F 2>nul
taskkill /FI "WINDOWTITLE eq MAHALO - Splunk API (5003)" /IM cmd.exe /F 2>nul
taskkill /FI "WINDOWTITLE eq MAHALO - JIRA MCP (6001)" /IM cmd.exe /F 2>nul
taskkill /FI "WINDOWTITLE eq MAHALO - ServiceNow MCP (6002)" /IM cmd.exe /F 2>nul
taskkill /FI "WINDOWTITLE eq MAHALO - Splunk MCP (6003)" /IM cmd.exe /F 2>nul
taskkill /FI "WINDOWTITLE eq MAHALO - Main API (8000)" /IM cmd.exe /F 2>nul
taskkill /FI "WINDOWTITLE eq MAHALO - Frontend (3000)" /IM cmd.exe /F 2>nul

REM Also kill processes on specific ports (backup method)
echo.
echo [INFO] Ensuring all ports are freed...
for /f "tokens=5" %%a in ('netstat -aon ^| findstr :5001 ^| findstr LISTENING') do taskkill /F /PID %%a 2>nul
for /f "tokens=5" %%a in ('netstat -aon ^| findstr :5002 ^| findstr LISTENING') do taskkill /F /PID %%a 2>nul
for /f "tokens=5" %%a in ('netstat -aon ^| findstr :5003 ^| findstr LISTENING') do taskkill /F /PID %%a 2>nul
for /f "tokens=5" %%a in ('netstat -aon ^| findstr :6001 ^| findstr LISTENING') do taskkill /F /PID %%a 2>nul
for /f "tokens=5" %%a in ('netstat -aon ^| findstr :6002 ^| findstr LISTENING') do taskkill /F /PID %%a 2>nul
for /f "tokens=5" %%a in ('netstat -aon ^| findstr :6003 ^| findstr LISTENING') do taskkill /F /PID %%a 2>nul
for /f "tokens=5" %%a in ('netstat -aon ^| findstr :8000 ^| findstr LISTENING') do taskkill /F /PID %%a 2>nul
for /f "tokens=5" %%a in ('netstat -aon ^| findstr :3000 ^| findstr LISTENING') do taskkill /F /PID %%a 2>nul

echo.
echo ============================================================
echo All MAHALO services stopped!
echo ============================================================
echo.
pause

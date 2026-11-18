@echo off
title PartKeeper Stopper
cd /d "%~dp0"

echo ============================================
echo  PartKeeper - Stop Frontend, Backend and MCP
echo ============================================
echo.

call :killport 5173 Frontend
call :killport 5000 Backend
call :killport 8000 MCP

echo.
echo All done.
pause
exit /b

:killport
setlocal EnableDelayedExpansion
set PORT=%1
set NAME=%2
set PID=
rem 双重过滤：先限定 LISTENING 行，再匹配本地地址端口，避免误杀其他连接
for /f "tokens=5" %%a in ('netstat -ano ^| findstr /R "LISTENING" ^| findstr ":%PORT% "') do set PID=%%a
if defined PID (
    taskkill /PID %PID% /F >nul 2>&1
    if !ERRORLEVEL! EQU 0 (
        echo  %NAME% ^(port %PORT%^) stopped, PID %PID%
    ) else (
        echo  %NAME% ^(port %PORT%^) FAILED to stop, PID %PID%
    )
) else (
    echo  %NAME% ^(port %PORT%^) not running
)
endlocal
exit /b

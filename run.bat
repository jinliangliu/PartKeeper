@echo off
title PartKeeper Launcher
cd /d "%~dp0"

echo ============================================
echo  PartKeeper - Start Frontend, Backend and MCP
echo ============================================
echo.

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0start.ps1" %*

echo.
echo ============================================
echo  Launcher finished.
echo  Frontend : http://localhost:5173
echo  Backend  : http://localhost:5000
echo  MCP      : http://localhost:8000/mcp
echo ============================================
echo.
pause

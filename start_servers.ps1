$ErrorActionPreference = 'Stop'

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$backend = Join-Path $root 'backend'
$frontend = Join-Path $root 'frontend'
$logDir = Join-Path $backend 'logs'
$instanceDir = Join-Path $backend 'instance'
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
New-Item -ItemType Directory -Force -Path $instanceDir | Out-Null

# 后端（本机无 MySQL，使用 SQLite 临时数据库；正式环境请在 backend/.env 配置 MySQL）
$env:DATABASE_URL = 'sqlite:///app.db'
$env:FLASK_DEBUG = '0'
$backendOut = Join-Path $logDir 'backend.out.log'
$backendErr = Join-Path $logDir 'backend.err.log'
$backendProcess = Start-Process -FilePath 'python' `
    -ArgumentList 'app.py' `
    -WorkingDirectory $backend `
    -WindowStyle Hidden `
    -RedirectStandardOutput $backendOut `
    -RedirectStandardError $backendErr `
    -PassThru

# 前端（Vite 开发服务器，已配置 /api 代理到后端）
$frontendOut = Join-Path $logDir 'frontend.out.log'
$frontendErr = Join-Path $logDir 'frontend.err.log'
$frontendProcess = Start-Process -FilePath 'cmd.exe' `
    -ArgumentList '/c', 'npm run dev' `
    -WorkingDirectory $frontend `
    -WindowStyle Hidden `
    -RedirectStandardOutput $frontendOut `
    -RedirectStandardError $frontendErr `
    -PassThru

Write-Output ("backend_pid=" + $backendProcess.Id)
Write-Output ("frontend_pid=" + $frontendProcess.Id)

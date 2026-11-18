# PartKeeper 一键启动脚本（Windows PowerShell）
# 用法：powershell -ExecutionPolicy Bypass -File .\start.ps1 [-NoBrowser]

param(
    [switch]$NoBrowser
)

# 原生命令（python/node）向 stderr 写的环境噪音不应终止脚本；throw 仍会正常中断
$ErrorActionPreference = 'Continue'

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Backend = Join-Path $Root 'backend'
$Frontend = Join-Path $Root 'frontend'
$Logs = Join-Path $Backend 'logs'
$Instance = Join-Path $Backend 'instance'
New-Item -ItemType Directory -Force -Path $Logs, $Instance | Out-Null

function Step([string]$Message) { Write-Host "==> $Message" -ForegroundColor Cyan }
function Ok([string]$Message) { Write-Host "    $Message" -ForegroundColor Green }
function Warn([string]$Message) { Write-Host "    [warn] $Message" -ForegroundColor Yellow }

# 宿主会同时注入 http_proxy/HTTP_PROXY 等大小写别名；Start-Process 构造环境字典时
# 因键大小写不敏感而抛 "Item has already been added"，故统一清除小写别名，只留大写
foreach ($alias in @('http_proxy', 'https_proxy', 'all_proxy', 'no_proxy')) {
    if ($null -ne [System.Environment]::GetEnvironmentVariable($alias, 'Process')) {
        [System.Environment]::SetEnvironmentVariable($alias, $null, 'Process')
    }
}

# 快速探测本机端口（比 Test-NetConnection 快）
function Test-Port([int]$Port) {
    $Tcp = New-Object System.Net.Sockets.TcpClient
    try {
        $Async = $Tcp.BeginConnect('127.0.0.1', $Port, $null, $null)
        if ($Async.AsyncWaitHandle.WaitOne(500)) {
            $Tcp.EndConnect($Async)
            return $true
        }
        return $false
    }
    catch {
        return $false
    }
    finally {
        $Tcp.Close()
    }
}

Step 'Checking runtime'
$Python = $null
foreach ($Name in @('python', 'py')) {
    if (Get-Command $Name -ErrorAction SilentlyContinue) { $Python = $Name; break }
}
if (-not $Python) { throw 'Python 3.10+ not found in PATH.' }
if (-not (Get-Command node -ErrorAction SilentlyContinue)) { throw 'Node.js not found in PATH.' }
if (-not (Get-Command npm -ErrorAction SilentlyContinue)) { throw 'npm not found in PATH.' }
Ok "Python: $Python ; Node: $(node --version)"

Step 'Preparing backend'
$EnvFile = Join-Path $Backend '.env'
if (-not (Test-Path $EnvFile)) {
    # 首次启动：生成一份带随机 SECRET_KEY 的 .env（此文件已 gitignore，不提交）
    $Secret = -join (1..32 | ForEach-Object { '{0:x}' -f (Get-Random -Maximum 16) })
    $EnvContent = @"
DATABASE_URL=sqlite:///app.db
APP_HOST=0.0.0.0
APP_PORT=5000
SECRET_KEY=$Secret
JWT_EXPIRATION_HOURS=24
ADMIN_USERNAME=admin
ADMIN_PASSWORD=admin123
ADMIN_EMAIL=admin@example.com
"@
    Set-Content -Path $EnvFile -Value $EnvContent -Encoding Ascii
    Ok 'Generated backend/.env (random SECRET_KEY)'
}
else {
    Ok 'backend/.env already exists'
}

# 后端 Python：优先使用已建好的 .venv（依赖齐全且隔离），避免系统 Python 的环境噪音
$VenvPython = Join-Path $Backend '.venv\Scripts\python.exe'
if (Test-Path $VenvPython) {
    $BackendPython = $VenvPython
    Ok "Using venv python: $BackendPython"
}
else {
    Ok 'venv 不存在，创建并安装依赖...'
    & $Python -m venv $VenvPython 2>$null
    $BackendPython = $VenvPython
    & $BackendPython -m pip install -r (Join-Path $Backend 'requirements.txt')
}
# 若 venv 存在但缺 MCP 依赖（旧版本升级场景），补装缺失项，静默其 stderr 噪音
& $BackendPython -c 'import mcp, uvicorn' 2>$null
if ($LASTEXITCODE -ne 0) {
    Ok '补齐 MCP 依赖...'
    & $BackendPython -m pip install -r (Join-Path $Backend 'requirements.txt') 2>$null
}

Step 'Starting backend'
if (Test-Port 5000) {
    Ok 'Backend already running on :5000'
}
else {
    $env:DATABASE_URL = 'sqlite:///app.db'
    $env:FLASK_DEBUG = '0'
    Start-Process -FilePath $BackendPython -ArgumentList 'app.py' -WorkingDirectory $Backend -WindowStyle Hidden `
        -RedirectStandardOutput (Join-Path $Logs 'backend.out.log') `
        -RedirectStandardError (Join-Path $Logs 'backend.err.log') | Out-Null
    Ok 'Backend started'
}

Step 'Starting frontend'
if (-not (Test-Path (Join-Path $Frontend 'node_modules'))) {
    Ok 'Installing frontend dependencies (npm install)...'
    & npm --prefix $Frontend install
}
if (Test-Port 5173) {
    Ok 'Frontend already running on :5173'
}
else {
    Start-Process -FilePath 'cmd.exe' -ArgumentList '/c', 'npm run dev' -WorkingDirectory $Frontend -WindowStyle Hidden `
        -RedirectStandardOutput (Join-Path $Logs 'frontend.out.log') `
        -RedirectStandardError (Join-Path $Logs 'frontend.err.log') | Out-Null
    Ok 'Frontend started'
}

Step 'Waiting for services'
$Deadline = (Get-Date).AddSeconds(60)
$BackendUp = $false
$FrontendUp = $false
while ((Get-Date) -lt $Deadline -and -not ($BackendUp -and $FrontendUp)) {
    $BackendUp = Test-Port 5000
    $FrontendUp = Test-Port 5173
    if (-not ($BackendUp -and $FrontendUp)) { Start-Sleep -Seconds 1 }
}
if (-not $BackendUp) { Warn 'Backend not ready; check backend/logs/backend.err.log' }
if (-not $FrontendUp) { Warn 'Frontend not ready; check backend/logs/frontend.err.log' }
Ok 'Frontend : http://localhost:5173'
Ok 'Backend  : http://localhost:5000'

Step 'Starting MCP Server (for WorkBuddy Connector)'
if (Test-Port 8000) {
    Ok 'MCP Server already running on :8000'
}
else {
    Start-Process -FilePath $BackendPython -ArgumentList 'mcp_server.py' -WorkingDirectory $Backend -WindowStyle Hidden `
        -RedirectStandardOutput (Join-Path $Logs 'mcp.out.log') `
        -RedirectStandardError (Join-Path $Logs 'mcp.err.log') | Out-Null
    Ok 'MCP Server started'
}
Ok 'MCP      : http://localhost:8000/mcp'

Ok 'Default admin: admin / admin123'

if (-not $NoBrowser -and $FrontendUp) {
    Start-Process 'http://localhost:5173'
    Ok 'Opened browser at http://localhost:5173'
}

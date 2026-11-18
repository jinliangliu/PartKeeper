# PartKeeper MCP Server 启动脚本（Windows PowerShell）
# 供 WorkBuddy 自定义连接器访问；默认监听 0.0.0.0:8000，端点 /mcp
# 用法：powershell -ExecutionPolicy Bypass -File .\start_mcp.ps1

$ErrorActionPreference = 'Continue'

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Backend = Join-Path $Root 'backend'
$Logs = Join-Path $Backend 'logs'
New-Item -ItemType Directory -Force -Path $Logs | Out-Null

# 清除宿主注入的小写代理别名，避免 Start-Process 环境字典键冲突
foreach ($alias in @('http_proxy', 'https_proxy', 'all_proxy', 'no_proxy')) {
    if ($null -ne [System.Environment]::GetEnvironmentVariable($alias, 'Process')) {
        [System.Environment]::SetEnvironmentVariable($alias, $null, 'Process')
    }
}

function Test-Port([int]$Port) {
    $Tcp = New-Object System.Net.Sockets.TcpClient
    try {
        $Async = $Tcp.BeginConnect('127.0.0.1', $Port, $null, $null)
        if ($Async.AsyncWaitHandle.WaitOne(500)) { $Tcp.EndConnect($Async); return $true }
        return $false
    } catch { return $false }
    finally { $Tcp.Close() }
}

# 选择 Python：优先 backend/.venv，其次系统 python
$BackendPython = Join-Path $Backend '.venv\Scripts\python.exe'
if (-not (Test-Path $BackendPython)) { $BackendPython = 'python' }

# 确认 mcp 依赖可用，否则安装
& $BackendPython -c 'import mcp, uvicorn' 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host '==> 安装 MCP 依赖...' -ForegroundColor Cyan
    & $BackendPython -m pip install -r (Join-Path $Backend 'requirements.txt')
}

if (Test-Port 8000) {
    Write-Host 'MCP Server 已在 :8000 运行' -ForegroundColor Green
    exit 0
}

Start-Process -FilePath $BackendPython -ArgumentList 'mcp_server.py' `
    -WorkingDirectory $Backend -WindowStyle Hidden `
    -RedirectStandardOutput (Join-Path $Logs 'mcp.out.log') `
    -RedirectStandardError (Join-Path $Logs 'mcp.err.log') | Out-Null

$Deadline = (Get-Date).AddSeconds(20)
while ((Get-Date) -lt $Deadline -and -not (Test-Port 8000)) { Start-Sleep -Milliseconds 500 }

if (Test-Port 8000) {
    Write-Host 'MCP Server 启动成功: http://localhost:8000/mcp' -ForegroundColor Green
    Write-Host '认证: Authorization: Bearer <MCP_API_KEY>' -ForegroundColor Green
} else {
    Write-Host '启动失败，请查看 backend/logs/mcp.err.log' -ForegroundColor Red
    exit 1
}

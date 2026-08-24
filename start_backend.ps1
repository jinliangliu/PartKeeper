$ErrorActionPreference = 'Stop'

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$backend = Join-Path $root 'backend'
$logDir = Join-Path $backend 'logs'
$instanceDir = Join-Path $backend 'instance'
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
New-Item -ItemType Directory -Force -Path $instanceDir | Out-Null

$env:DATABASE_URL = 'sqlite:///app.db'
$env:FLASK_DEBUG = '0'

$backendProcess = Start-Process -FilePath 'python' `
    -ArgumentList 'app.py' `
    -WorkingDirectory $backend `
    -WindowStyle Hidden `
    -RedirectStandardOutput (Join-Path $logDir 'backend.out.log') `
    -RedirectStandardError (Join-Path $logDir 'backend.err.log') `
    -PassThru

Write-Output ("backend_pid=" + $backendProcess.Id)

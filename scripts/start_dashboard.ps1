$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$Port = 8787
$HostName = "127.0.0.1"
$LogDir = Join-Path $ProjectRoot "data"
$LogPath = Join-Path $LogDir "startup.log"

New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

function Write-StartupLog {
    param([string]$Message)
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    Add-Content -Path $LogPath -Encoding UTF8 -Value "$timestamp $Message"
}

$existing = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
if ($existing) {
    Write-StartupLog "Dashboard already running on port $Port."
    exit 0
}

$pythonCommand = Get-Command python -ErrorAction Stop
$arguments = @(
    "src/main.py",
    "serve",
    "--host", $HostName,
    "--port", "$Port",
    "--refresh-on-start"
)

Write-StartupLog "Starting dashboard on http://$HostName`:$Port"
Start-Process `
    -FilePath $pythonCommand.Source `
    -ArgumentList $arguments `
    -WorkingDirectory $ProjectRoot `
    -WindowStyle Hidden

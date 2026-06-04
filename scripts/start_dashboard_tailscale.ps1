param(
    [string]$Profile = "son",
    [switch]$NoOpen
)
$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$Port = 8787
$LogDir = Join-Path $ProjectRoot "data"
$LogPath = Join-Path $LogDir "tailscale_startup.log"
$StdOutPath = Join-Path $LogDir "server.out.log"
$StdErrPath = Join-Path $LogDir "server.err.log"

New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

function Write-TailscaleLog {
    param([string]$Message)
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    Add-Content -Path $LogPath -Encoding UTF8 -Value "$timestamp $Message"
}

function Get-TailscaleCommand {
    $cmd = Get-Command tailscale -ErrorAction SilentlyContinue
    if ($cmd) {
        return $cmd.Source
    }

    $candidates = @(
        "$env:ProgramFiles\Tailscale\tailscale.exe",
        "${env:ProgramFiles(x86)}\Tailscale\tailscale.exe"
    )
    foreach ($candidate in $candidates) {
        if (Test-Path $candidate) {
            return $candidate
        }
    }

    throw "tailscale.exe not found. Install Tailscale and sign in first."
}

$tailscale = Get-TailscaleCommand
$tailscaleIp = (& $tailscale ip -4 2>$null | Select-Object -First 1).Trim()
if (-not $tailscaleIp) {
    throw "No Tailscale IPv4 found. Make sure Tailscale is running and this PC is logged in."
}

$url = "http://$tailscaleIp`:$Port/$Profile"
$existing = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
    Where-Object { $_.LocalAddress -eq $tailscaleIp -or $_.LocalAddress -eq "0.0.0.0" }
if ($existing) {
    Write-TailscaleLog "Dashboard already running on $tailscaleIp`:$Port. Opening $url"
    if (-not $NoOpen) {
        Start-Process $url
    }
    exit 0
}

$pythonCommand = Get-Command "C:\Python314\python.exe" -ErrorAction SilentlyContinue
if (-not $pythonCommand) {
    $pythonCommand = Get-Command python -ErrorAction Stop
}
$arguments = @(
    "src/main.py",
    "serve",
    "--host", $tailscaleIp,
    "--port", "$Port",
    "--refresh-on-start"
)

Write-TailscaleLog "Starting dashboard on http://$tailscaleIp`:$Port"
Start-Process `
    -FilePath $pythonCommand.Source `
    -ArgumentList $arguments `
    -WorkingDirectory $ProjectRoot `
    -RedirectStandardOutput $StdOutPath `
    -RedirectStandardError $StdErrPath `
    -WindowStyle Hidden

$deadline = (Get-Date).AddSeconds(25)
do {
    Start-Sleep -Milliseconds 500
    $listener = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
        Where-Object { $_.LocalAddress -eq $tailscaleIp -or $_.LocalAddress -eq "0.0.0.0" } |
        Select-Object -First 1
} while (-not $listener -and (Get-Date) -lt $deadline)

if (-not $listener) {
    Write-TailscaleLog "Dashboard start timed out. See $StdErrPath"
    throw "Dashboard start timed out. See $StdErrPath"
}

Write-TailscaleLog "Dashboard ready on $url"
if (-not $NoOpen) {
    Start-Process $url
}

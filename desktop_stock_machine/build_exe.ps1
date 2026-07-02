$ErrorActionPreference = "Stop"

$ScriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Resolve-Path (Join-Path $ScriptRoot "..")
$OutputRoot = Join-Path $ProjectRoot "output\desktop_exe"
$LogRoot = Join-Path $ProjectRoot "output\build_logs"
$FrontendRoot = Resolve-Path (Join-Path $ProjectRoot "desktop_stock_machine\frontend")
$Timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$LogPath = Join-Path $LogRoot "desktop_exe_build_$Timestamp.log"
$ExePath = Join-Path $OutputRoot "dist\DesktopStockMachine.exe"

New-Item -ItemType Directory -Force -Path $OutputRoot | Out-Null
New-Item -ItemType Directory -Force -Path $LogRoot | Out-Null

function Write-BuildLog {
  param([string]$Message)
  $Line = "[$(Get-Date -Format "yyyy-MM-dd HH:mm:ss")] $Message"
  $Line | Tee-Object -FilePath $LogPath -Append
}

function Run-AndLog {
  param(
    [string]$FilePath,
    [string[]]$Arguments
  )

  Write-BuildLog "RUN: $FilePath $($Arguments -join ' ')"

  $CommandLog = Join-Path $OutputRoot "last_command_output.txt"
  $PreviousErrorActionPreference = $ErrorActionPreference
  $ErrorActionPreference = "Continue"
  try {
    & $FilePath @Arguments > $CommandLog 2>&1
    $ExitCode = $LASTEXITCODE
  } finally {
    $ErrorActionPreference = $PreviousErrorActionPreference
  }

  if (Test-Path $CommandLog) {
    Get-Content -LiteralPath $CommandLog | Tee-Object -FilePath $LogPath -Append
  }

  if ($ExitCode -ne 0) {
    throw "Command failed with exit code $ExitCode"
  }
}

Set-Location $ProjectRoot

Write-BuildLog "Desktop Stock Machine EXE build started"
Write-BuildLog "Project root: $ProjectRoot"
Write-BuildLog "Output root: $OutputRoot"
Write-BuildLog "Frontend root: $FrontendRoot"
Write-BuildLog "Expected exe: $ExePath"
Write-BuildLog "Packaged assets: desktop_stock_machine\frontend only"
Write-BuildLog "Excluded data roots: data, demo_runtime, app_data, backups, output, config/providers.local.json"
Write-BuildLog "app_data exists before build: $(Test-Path (Join-Path $ProjectRoot "app_data"))"

Run-AndLog "python" @("desktop_stock_machine\desktop_entry.py", "--check")

$PyInstallerArgs = @(
  "-m", "PyInstaller",
  "--noconfirm",
  "--clean",
  "--onefile",
  "--windowed",
  "--name", "DesktopStockMachine",
  "--distpath", "output\desktop_exe\dist",
  "--workpath", "output\desktop_exe\build",
  "--specpath", "output\desktop_exe\spec",
  "--add-data", "$FrontendRoot;frontend",
  "desktop_stock_machine\desktop_entry.py"
)

Run-AndLog "python" $PyInstallerArgs

if (-not (Test-Path $ExePath)) {
  throw "Expected EXE was not created: $ExePath"
}

Run-AndLog $ExePath @("--check")

Write-BuildLog "app_data exists after build: $(Test-Path (Join-Path $ProjectRoot "app_data"))"
Write-BuildLog "Build succeeded"
Write-BuildLog "EXE: $ExePath"
Write-BuildLog "Log: $LogPath"

Write-Host ""
Write-Host "Desktop Stock Machine EXE created:"
Write-Host $ExePath
Write-Host ""
Write-Host "Build log:"
Write-Host $LogPath

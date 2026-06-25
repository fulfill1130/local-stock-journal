param(
    [Parameter(Mandatory = $true)]
    [string]$TailscaleIp,
    [int]$Port = 8787,
    [string]$DisplayName = "StockDailyHelper Tailscale"
)

$ErrorActionPreference = "Stop"

$existing = Get-NetFirewallRule -DisplayName $DisplayName -ErrorAction SilentlyContinue
if ($existing) {
    Remove-NetFirewallRule -DisplayName $DisplayName
}

New-NetFirewallRule `
    -DisplayName $DisplayName `
    -Direction Inbound `
    -Action Allow `
    -Protocol TCP `
    -LocalAddress $TailscaleIp `
    -LocalPort $Port `
    -Profile Any `
    -Description "Allow Stock Daily Helper only on the provided Tailscale private IP."

$ErrorActionPreference = "Stop"
$displayName = "StockDailyHelper Tailscale 8787"
$tailscaleIp = "100.70.96.67"
$existing = Get-NetFirewallRule -DisplayName $displayName -ErrorAction SilentlyContinue
if ($existing) {
    Remove-NetFirewallRule -DisplayName $displayName
}
New-NetFirewallRule `
    -DisplayName $displayName `
    -Direction Inbound `
    -Action Allow `
    -Protocol TCP `
    -LocalAddress $tailscaleIp `
    -LocalPort 8787 `
    -Profile Any `
    -Description "Allow Stock Daily Helper only on the Tailscale private IP."

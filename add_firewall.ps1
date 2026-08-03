[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = New-Object Security.Principal.WindowsPrincipal($identity)
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Write-Host "[INFO] Requesting Administrator privileges for Windows Firewall..." -ForegroundColor Yellow
    Start-Process powershell -ArgumentList "-NoProfile -ExecutionPolicy Bypass -File ""$PSCommandPath""" -Verb RunAs
    exit
}

Write-Host "========================================================" -ForegroundColor Cyan
Write-Host "               MOPS Windows Firewall Setup" -ForegroundColor Cyan
Write-Host "========================================================" -ForegroundColor Cyan
Write-Host ""

Write-Host "[1/3] Cleaning all existing mops firewall rules..." -ForegroundColor White
$existingRules = Get-NetFirewallRule | Where-Object { $_.DisplayName -like "*mops*" -or $_.Name -like "*mops*" }
if ($existingRules) {
    $existingRules | Remove-NetFirewallRule -ErrorAction SilentlyContinue
    Write-Host "     [+] All existing mops firewall rules removed successfully!" -ForegroundColor Green
} else {
    Write-Host "     [+] No existing mops firewall rules found." -ForegroundColor Green
}

Write-Host "[2/3] Adding TCP Firewall Rule (Ports: 10080, 10081)..." -ForegroundColor White
New-NetFirewallRule -DisplayName "MOPS Proxy Ports (TCP)" -Direction Inbound -LocalPort 10080,10081 -Protocol TCP -Action Allow | Out-Null
Write-Host "     [+] TCP Ports 10080, 10081 Allowed successfully!" -ForegroundColor Green

Write-Host "[3/3] Adding UDP Firewall Rule (Port: 5353)..." -ForegroundColor White
New-NetFirewallRule -DisplayName "MOPS mDNS Port (UDP)" -Direction Inbound -LocalPort 5353 -Protocol UDP -Action Allow | Out-Null
Write-Host "     [+] UDP Port 5353 Allowed successfully!" -ForegroundColor Green

Write-Host ""
Write-Host "========================================================" -ForegroundColor Cyan
Write-Host "Setup Complete! Pure port rules (TCP 10080, 10081 & UDP 5353) allowed." -ForegroundColor Green
Write-Host "========================================================" -ForegroundColor Cyan
Write-Host ""

Read-Host "Press Enter to exit..."

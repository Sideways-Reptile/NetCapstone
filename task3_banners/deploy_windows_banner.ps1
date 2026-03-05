# ============================================================
# Bigfork IT — Windows Login Banner Deployment
# Task 3 — Security Compliance Banners
#
# Run as Administrator:
#   Right-click > Run with PowerShell
#   OR from Admin PowerShell: .\deploy_windows_banner.ps1
#
# What this does:
#   Sets legalnoticecaption and legalnoticetext registry keys
#   that display a banner popup before the Windows login screen.
#   No reboot required — lock screen (Win+L) to test immediately.
# ============================================================

$ErrorActionPreference = "Stop"

$bannerTitle = "AUTHORIZED ACCESS ONLY"
$bannerText  = @"
This system is the property of Bigfork IT.

All activity on this system is monitored and logged.
Unauthorized access is strictly prohibited and will be
prosecuted to the fullest extent of the law.

If you are not an authorized user, disconnect NOW.
"@

$regPath = "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\System"

Write-Host ""
Write-Host "=============================================" -ForegroundColor Cyan
Write-Host "  Bigfork IT — Windows Login Banner Deploy" -ForegroundColor Cyan
Write-Host "=============================================" -ForegroundColor Cyan
Write-Host ""

try {
    # Ensure registry path exists
    if (-not (Test-Path $regPath)) {
        New-Item -Path $regPath -Force | Out-Null
        Write-Host "  Created registry path." -ForegroundColor Yellow
    }

    # Set banner title
    Set-ItemProperty -Path $regPath -Name "legalnoticecaption" -Value $bannerTitle -Type String
    Write-Host "  [OK] legalnoticecaption set: $bannerTitle" -ForegroundColor Green

    # Set banner body text
    Set-ItemProperty -Path $regPath -Name "legalnoticetext" -Value $bannerText -Type String
    Write-Host "  [OK] legalnoticetext set." -ForegroundColor Green

    Write-Host ""
    Write-Host "  Banner deployed successfully." -ForegroundColor Green
    Write-Host "  To verify: Press Win+L to lock screen, click user." -ForegroundColor White
    Write-Host "  The banner popup should appear before the password prompt." -ForegroundColor White
    Write-Host ""

} catch {
    Write-Host ""
    Write-Host "  [ERROR] Failed to set registry keys:" -ForegroundColor Red
    Write-Host "  $_" -ForegroundColor Red
    Write-Host ""
    Write-Host "  Make sure you are running as Administrator." -ForegroundColor Yellow
    Write-Host ""
    exit 1
}

# Verify keys were set
Write-Host "  Verifying registry values..." -ForegroundColor Cyan
$caption = Get-ItemPropertyValue -Path $regPath -Name "legalnoticecaption"
$text    = Get-ItemPropertyValue -Path $regPath -Name "legalnoticetext"

if ($caption -eq $bannerTitle) {
    Write-Host "  [OK] Caption verified." -ForegroundColor Green
} else {
    Write-Host "  [WARN] Caption mismatch — check registry manually." -ForegroundColor Yellow
}

if ($text.Length -gt 10) {
    Write-Host "  [OK] Banner text verified ($($text.Length) chars)." -ForegroundColor Green
} else {
    Write-Host "  [WARN] Banner text appears empty — check registry manually." -ForegroundColor Yellow
}

Write-Host ""
Write-Host "  Registry path for manual verification:" -ForegroundColor White
Write-Host "  $regPath" -ForegroundColor Gray
Write-Host ""

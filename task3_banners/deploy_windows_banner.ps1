# deploy_windows_banner.ps1
# Bigfork IT Capstone Lab — Task 3 — Windows Login Banner
# RIGHT-CLICK this file and select "Run with PowerShell" as Administrator

$title = "AUTHORIZED ACCESS ONLY"
$body  = "This system is property of Bigfork IT. All activity is monitored and logged. Unauthorized access is prohibited and will be prosecuted to the full extent of applicable law. Disconnect now if you are not an authorized user."

$reg = "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\System"
Set-ItemProperty -Path $reg -Name "legalnoticecaption" -Value $title -Type String
Set-ItemProperty -Path $reg -Name "legalnoticetext"    -Value $body  -Type String

Write-Host "Banner set successfully." -ForegroundColor Green
Write-Host "Lock screen (Win+L) then click your user to verify popup appears."

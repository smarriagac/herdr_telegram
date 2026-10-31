# Herdr Telegram Bridge Windows Uninstaller
# Run in PowerShell: powershell -ExecutionPolicy Bypass -File .\uninstall.ps1

$ErrorActionPreference = "Stop"

Write-Host "=== Herdr Telegram Bridge Windows Uninstaller ===" -ForegroundColor Cyan

$taskName = "HerdrTelegramBridge"
$existingTask = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue

if ($existingTask) {
    Write-Host "[+] Stopping and unregistering Scheduled Task '$taskName'..." -ForegroundColor Cyan
    Stop-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
    Write-Host "[+] Scheduled Task removed." -ForegroundColor Green
} else {
    Write-Host "[*] Scheduled Task '$taskName' not found." -ForegroundColor Gray
}

$configDir = Join-Path $env:APPDATA "herdr-telegram"
if (Test-Path $configDir) {
    $choice = Read-Host "Do you want to delete configuration and history in '$configDir'? (y/N)"
    if ($choice -match "^[yY]$") {
        Remove-Item -Path $configDir -Recurse -Force
        Write-Host "[+] Removed $configDir" -ForegroundColor Green
    } else {
        Write-Host "[*] Preserving $configDir" -ForegroundColor Cyan
    }
}

Write-Host "=== Uninstallation Complete ===" -ForegroundColor Cyan

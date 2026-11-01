# Herdr Telegram Bridge Windows Installer
# Run in PowerShell: powershell -ExecutionPolicy Bypass -File .\install.ps1

$ErrorActionPreference = "Stop"

Write-Host "=== Herdr Telegram Bridge Windows Installer ===" -ForegroundColor Cyan

# 1. Locate Python executable (prefer pythonw.exe to avoid command prompt popup)
$pythonExe = (Get-Command python -ErrorAction SilentlyContinue).Source
if (-not $pythonExe) {
    $pythonExe = (Get-Command python3 -ErrorAction SilentlyContinue).Source
}

if (-not $pythonExe) {
    Write-Error "[-] Python was not found in PATH. Please install Python 3.8+ and add it to PATH."
    exit 1
}

$pythonDir = Split-Path $pythonExe
$pythonwExe = Join-Path $pythonDir "pythonw.exe"
if (-not (Test-Path $pythonwExe)) {
    # If pythonw.exe is not found, fallback to standard python.exe
    $pythonwExe = $pythonExe
}

Write-Host "[+] Using Python interpreter: $pythonwExe" -ForegroundColor Green

# 2. Check for Herdr
$herdrCmd = (Get-Command herdr -ErrorAction SilentlyContinue).Source
if (-not $herdrCmd) {
    Write-Host "[!] Warning: 'herdr' executable was not found in PATH." -ForegroundColor Yellow
    Write-Host "    Make sure Herdr is installed before starting the service." -ForegroundColor Yellow
}

# 3. Setup directories in %APPDATA%\herdr-telegram
$configDir = Join-Path $env:APPDATA "herdr-telegram"
if (-not (Test-Path $configDir)) {
    New-Item -ItemType Directory -Path $configDir -Force | Out-Null
}

$scriptDir = $PSScriptRoot
Copy-Item -Path (Join-Path $scriptDir "src\*") -Destination $configDir -Recurse -Force
$destScript = Join-Path $configDir "bot.py"
Write-Host "[+] Installed bot package and daemon to: $destScript" -ForegroundColor Green

# 4. Handle configuration
$destConfig = Join-Path $configDir "config.json"
$configIsNew = $false
if (-not (Test-Path $destConfig)) {
    Copy-Item -Path (Join-Path $scriptDir "config.example.json") -Destination $destConfig
    Write-Host "[+] Created configuration template: $destConfig" -ForegroundColor Green
    $configIsNew = $true
} else {
    Write-Host "[*] Preserving existing configuration at: $destConfig" -ForegroundColor Cyan
}

# 5. Register Scheduled Task
$taskName = "HerdrTelegramBridge"

# Remove existing task if already registered
$existingTask = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
if ($existingTask) {
    Write-Host "[+] Updating existing Scheduled Task '$taskName'..." -ForegroundColor Cyan
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
}

$action = New-ScheduledTaskAction -Execute $pythonwExe -Argument "`"$destScript`"" -WorkingDirectory $configDir
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1) -ExecutionTimeLimit 0

Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Settings $settings -Description "Herdr Telegram Bridge Background Daemon" | Out-Null
Write-Host "[+] Registered Windows Scheduled Task '$taskName'" -ForegroundColor Green

Write-Host ""
Write-Host "=== Installation Complete ===" -ForegroundColor Cyan
if ($configIsNew) {
    Write-Host "[!] Action required:" -ForegroundColor Yellow
    Write-Host "    1. Open and edit '$destConfig' with your Telegram Bot Token and Chat ID."
    Write-Host "    2. Start the daemon with: Start-ScheduledTask -TaskName '$taskName'"
} else {
    Write-Host "[+] Starting Scheduled Task '$taskName'..." -ForegroundColor Green
    Start-ScheduledTask -TaskName $taskName
    Start-Sleep -Seconds 1
    $taskState = (Get-ScheduledTask -TaskName $taskName).State
    Write-Host "[+] Task status: $taskState" -ForegroundColor Green
}
Write-Host "Stop anytime with: Stop-ScheduledTask -TaskName '$taskName'" -ForegroundColor Gray

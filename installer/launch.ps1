# Launch Walk to Mordor after install.
# Stops any existing tasks, kills running widgets, then starts fresh:
# daemon first, 2s pause, then the widget. Falls back to starting the exe
# directly when a scheduled task is missing (e.g. source installs).

$ErrorActionPreference = 'SilentlyContinue'

function Start-OrRun($taskName, $exeName) {
    if (Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue) {
        schtasks /run /tn $taskName | Out-Null
    } elseif (Test-Path (Join-Path $PSScriptRoot $exeName)) {
        Start-Process -FilePath (Join-Path $PSScriptRoot $exeName)
    }
}

# Stop existing daemon task (if running)
schtasks /end /tn "WalkToMordor" /f | Out-Null

# Kill any running widget exes (installed or dev)
Get-Process WalkToMordorWidget -ErrorAction SilentlyContinue | Stop-Process -Force

# Start the daemon, give it 2s to come up (BLE + API), then the widget.
Start-OrRun "WalkToMordor" "WalkToMordorDaemon.exe"
Start-Sleep -Seconds 2
Start-OrRun "WalkToMordorWidget" "WalkToMordorWidget.exe"

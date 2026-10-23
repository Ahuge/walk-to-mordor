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

# Stop the old daemon/widget, including a source-run pythonw daemon.
$stop = Join-Path $PSScriptRoot "stop_daemon.ps1"
if (Test-Path $stop) {
    & $stop
} else {
    schtasks /end /tn "WalkToMordor" | Out-Null
    Get-Process WalkToMordorWidget | Stop-Process -Force
}

# Start the daemon, give it 2s to come up (BLE + API), then the widget.
Start-OrRun "WalkToMordor" "WalkToMordorDaemon.exe"
Start-Sleep -Seconds 2
Start-OrRun "WalkToMordorWidget" "WalkToMordorWidget.exe"

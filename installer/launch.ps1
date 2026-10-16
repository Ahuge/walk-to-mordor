# Launch Walk to Mordor after install.
# Stops any existing tasks, kills running widgets, then starts fresh:
# daemon task first, 2s pause, then the widget.

$ErrorActionPreference = 'SilentlyContinue'

# Stop existing daemon task (if running)
schtasks /end /tn "WalkToMordor" /f | Out-Null

# Kill any running widget exes (installed or dev)
Get-Process WalkToMordorWidget -ErrorAction SilentlyContinue | Stop-Process -Force

# Start the daemon task
schtasks /run /tn "WalkToMordor" | Out-Null

# Give the daemon 2s to come up (BLE + API)
Start-Sleep -Seconds 2

# Start the widget task
schtasks /run /tn "WalkToMordorWidget" | Out-Null

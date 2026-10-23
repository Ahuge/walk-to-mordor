# Stop the daemon and widget before an upgrade or uninstall.
#
# Windows will not replace a running .exe, and a source-run daemon holds
# the BLE link and the API port. Stop both the registered task and any
# stray process (including `pythonw bridge\daemon.py` from a dev checkout)
# so the installer never leaves old code running.

$ErrorActionPreference = 'SilentlyContinue'

schtasks /end /tn "WalkToMordor" | Out-Null
schtasks /end /tn "WalkToMordorWidget" | Out-Null

Get-Process WalkToMordorDaemon, WalkToMordorWidget |
    Stop-Process -Force

Get-CimInstance Win32_Process -Filter "Name='pythonw.exe' OR Name='python.exe'" |
    Where-Object { $_.CommandLine -like '*bridge\daemon.py*' } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force }

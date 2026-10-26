# Stop the daemon and related background processes before an upgrade,
# reinstall, or uninstall.
#
# Windows will not replace a running .exe, and a source-run daemon holds
# the BLE link and the API port. Stop both the registered tasks and any
# stray process (including `pythonw bridge\daemon.py` from a dev checkout)
# and wait for it to actually exit before the installer touches the exes.

$ErrorActionPreference = 'SilentlyContinue'

foreach ($task in @('WalkToMordor', 'WalkToMordorWidget',
                    'WalkToMordorNudge', 'WalkToMordorMinimap')) {
    schtasks /end /tn $task | Out-Null
}

$names = @('WalkToMordorDaemon', 'WalkToMordorWidget',
           'WalkToMordorNudge', 'WalkToMordorMinimap')
$procs = Get-Process -Name $names -ErrorAction SilentlyContinue
if ($procs) {
    $procs | Stop-Process -Force -PassThru |
        Wait-Process -Timeout 10 -ErrorAction SilentlyContinue
}

$dev = Get-CimInstance Win32_Process -Filter "Name='pythonw.exe' OR Name='python.exe'" |
    Where-Object { $_.CommandLine -like '*bridge*daemon.py*' }
if ($dev) {
    $dev | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -PassThru } |
        Wait-Process -Timeout 10 -ErrorAction SilentlyContinue
}

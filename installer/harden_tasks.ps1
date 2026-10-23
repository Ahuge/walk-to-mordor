# Apply stable settings to the Walk to Mordor scheduled tasks.
#
# schtasks /create cannot express restart-on-failure, battery, or runtime
# limits, so run this after the tasks exist (installer and
# tools/install_windows.py both do). Missing tasks are ignored, which lets
# source installs harden only the tasks they actually created.
#
# Settings:
#   * restart on failure after 1 minute (the daemon logs and exits nonzero)
#   * keep running on battery
#   * no 72-hour execution limit
#   * start when a missed logon trigger becomes available
#   * never run two copies of the same task

$ErrorActionPreference = 'Stop'
$names = @(
    'WalkToMordor',
    'WalkToMordorWidget',
    'WalkToMordorNudge',
    'WalkToMordorMinimap'
)

$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -DontStopOnIdleEnd `
    -ExecutionTimeLimit ([TimeSpan]::Zero) `
    -RestartCount 999 `
    -RestartInterval (New-TimeSpan -Minutes 1) `
    -MultipleInstances IgnoreNew

$found = 0
foreach ($name in $names) {
    $task = Get-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue
    if ($null -eq $task) { continue }
    try {
        Set-ScheduledTask -TaskName $name -Settings $settings | Out-Null
        Write-Host "hardened: $name (restart on failure, no battery stop, unlimited runtime)"
        $found++
    } catch {
        Write-Warning "could not harden ${name}: $_"
    }
}

if ($found -eq 0) {
    Write-Host "no Walk to Mordor tasks found; nothing to harden"
}

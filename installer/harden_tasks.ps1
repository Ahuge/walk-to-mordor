# Apply stable settings to the Walk to Mordor scheduled tasks.
#
# schtasks /create cannot express restart-on-failure, battery, or runtime
# limits, so run this after the tasks exist (installer and
# tools/install_windows.py both do). Missing tasks are ignored, which lets
# source installs harden only the tasks they actually created.
#
# Settings:
#   * daemon/widget/minimap restart on failure after 1 minute
#   * the daily nudge does not restart or fire late (no notification spam)
#   * all tasks keep running on battery and have no 72-hour limit
#   * logon tasks start when a missed trigger becomes available
#   * never run two copies of the same task

$ErrorActionPreference = 'Stop'
$serviceNames = @('WalkToMordor', 'WalkToMordorWidget', 'WalkToMordorMinimap')

$serviceSettings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -DontStopOnIdleEnd `
    -ExecutionTimeLimit ([TimeSpan]::Zero) `
    -RestartCount 999 `
    -RestartInterval (New-TimeSpan -Minutes 1) `
    -MultipleInstances IgnoreNew

$dailySettings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -DontStopOnIdleEnd `
    -ExecutionTimeLimit ([TimeSpan]::Zero) `
    -RestartCount 0 `
    -MultipleInstances IgnoreNew

$found = 0
foreach ($name in ($serviceNames + 'WalkToMordorNudge')) {
    $task = Get-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue
    if ($null -eq $task) { continue }
    if ($name -eq 'WalkToMordorNudge') {
        $settings = $dailySettings
    } else {
        $settings = $serviceSettings
    }
    try {
        Set-ScheduledTask -TaskName $name -Settings $settings | Out-Null
        Write-Host "hardened: $name"
        $found++
    } catch {
        Write-Warning "could not harden ${name}: $_"
    }
}

if ($found -eq 0) {
    Write-Host "no Walk to Mordor tasks found; nothing to harden"
}

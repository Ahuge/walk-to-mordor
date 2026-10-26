# Register (or replace) the Walk to Mordor scheduled tasks.
#
# schtasks /sc onlogon needs an elevated shell on some machines, and a
# task created by an elevated installer is not writable by the normal
# user, so plain `schtasks /create /f` silently leaves stale actions.
# PowerShell's Register-ScheduledTask handles both cases in one step.
#
# Run from the installer (elevated) with -AppDir pointing at the installed
# folder. Also safe to run by hand to repair auto-start.

param(
    [string]$AppDir = $PSScriptRoot
)

$ErrorActionPreference = 'Stop'
$user = "$env:USERDOMAIN\$env:USERNAME"
$names = @('WalkToMordor', 'WalkToMordorWidget', 'WalkToMordorNudge')

foreach ($name in $names) {
    # Old tasks may belong to an elevated install; the installer itself is
    # elevated, so this can replace them cleanly.
    Stop-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue
    Unregister-ScheduledTask -TaskName $name -Confirm:$false `
        -ErrorAction SilentlyContinue
}

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

$principal = New-ScheduledTaskPrincipal -UserId $user `
    -LogonType Interactive -RunLevel Limited

function Register-LogonTask {
    param(
        [string]$Name,
        [string]$Exe,
        [int]$DelaySeconds = 0,
        [string]$Description
    )
    if (-not (Test-Path $Exe)) {
        throw "missing executable: $Exe"
    }
    $action = New-ScheduledTaskAction -Execute $Exe -WorkingDirectory $AppDir
    $trigger = New-ScheduledTaskTrigger -AtLogOn -User $user
    if ($DelaySeconds -gt 0) {
        $trigger.Delay = "PT${DelaySeconds}S"
    }
    Register-ScheduledTask -TaskName $Name -Action $action -Trigger $trigger `
        -Principal $principal -Settings $serviceSettings `
        -Description $Description -Force | Out-Null
    Write-Host "registered: $Name"
}

Register-LogonTask -Name 'WalkToMordor' `
    -Exe (Join-Path $AppDir 'WalkToMordorDaemon.exe') `
    -Description 'Walk to Mordor background daemon'
Register-LogonTask -Name 'WalkToMordorWidget' `
    -Exe (Join-Path $AppDir 'WalkToMordorWidget.exe') `
    -DelaySeconds 30 `
    -Description 'Walk to Mordor floating widget'

$nudge = Join-Path $AppDir 'WalkToMordorNudge.exe'
if (Test-Path $nudge) {
    $action = New-ScheduledTaskAction -Execute $nudge -WorkingDirectory $AppDir
    $trigger = New-ScheduledTaskTrigger -Daily -At '11:00'
    Register-ScheduledTask -TaskName 'WalkToMordorNudge' -Action $action `
        -Trigger $trigger -Principal $principal -Settings $dailySettings `
        -Description 'Daily Walk to Mordor reminder' -Force | Out-Null
    Write-Host 'registered: WalkToMordorNudge'
}

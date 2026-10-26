; Walk to Mordor installer script for Inno Setup 6.
; Build with: tools/build_installer.py (runs ISCC automatically)
; Or manually: "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" installer/walk-to-mordor.iss

#define MyAppName "Walk to Mordor"
#define MyAppVersion "1.1.0"
#define MyAppPublisher "Alex Hughes"

[Setup]
AppId={{8F4E3B2A-1C5D-4E7F-9A8B-3D2C1E0F5A6B}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppSupportURL=https://github.com/Ahuge/walk-to-mordor
DefaultDirName={localappdata}\Programs\WalkToMordor
DefaultGroupName=Walk to Mordor
OutputDir=..\dist
OutputBaseFilename=WalkToMordorSetup-{#MyAppVersion}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
; Logon tasks must be created/replaced reliably; some machines deny
; schtasks /sc onlogon (and writes to old task files) to normal users.
PrivilegesRequired=admin
DisableDirPage=no

[Files]
Source: "..\dist\WalkToMordorDaemon.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\dist\WalkToMordorWidget.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\dist\WalkToMordorNudge.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "launch.ps1"; DestDir: "{app}"; Flags: ignoreversion
Source: "register_tasks.ps1"; DestDir: "{app}"; Flags: ignoreversion
Source: "harden_tasks.ps1"; DestDir: "{app}"; Flags: ignoreversion
Source: "stop_daemon.ps1"; DestDir: "{app}"; Flags: ignoreversion
Source: "stop_daemon.ps1"; DestDir: "{tmp}"; Flags: dontcopy

[Icons]
Name: "{userprograms}\Walk to Mordor\Walk to Mordor Dashboard"; Filename: "http://127.0.0.1:8471/"
Name: "{userprograms}\Walk to Mordor\Walk to Mordor Widget"; Filename: "{app}\WalkToMordorWidget.exe"
Name: "{userprograms}\Walk to Mordor\Uninstall Walk to Mordor"; Filename: "{uninstallexe}"

[Run]
; Recreate daemon/widget/nudge tasks with their installed exe paths. This
; replaces stale source-run tasks and applies restart/battery settings.
Filename: "powershell"; \
  Parameters: "-NoProfile -ExecutionPolicy Bypass -File ""{app}\register_tasks.ps1"""; \
  Flags: runhidden waituntilterminated; StatusMsg: "Registering background tasks…"
; Safety net for tasks created by older/source installs.
Filename: "powershell"; \
  Parameters: "-NoProfile -ExecutionPolicy Bypass -File ""{app}\harden_tasks.ps1"""; \
  Flags: runhidden waituntilterminated; StatusMsg: "Hardening background tasks…"
; Silent upgrades stop the old daemon in PrepareToInstall; restart it.
Filename: "schtasks"; Parameters: "/run /tn ""WalkToMordor"""; \
  Flags: runhidden; Check: IsSilent

[UninstallRun]
Filename: "powershell"; \
  Parameters: "-NoProfile -ExecutionPolicy Bypass -File ""{app}\stop_daemon.ps1"""; \
  Flags: runhidden waituntilterminated
Filename: "schtasks"; Parameters: "/delete /tn ""WalkToMordor"" /f"; Flags: runhidden
Filename: "schtasks"; Parameters: "/delete /tn ""WalkToMordorWidget"" /f"; Flags: runhidden
Filename: "schtasks"; Parameters: "/delete /tn ""WalkToMordorNudge"" /f"; Flags: runhidden

[Run]
; Offer to launch after install. The script stops old tasks, kills stray
; widgets, starts the daemon, waits 2s, then starts the widget.
Filename: "powershell"; \
  Parameters: "-NoProfile -ExecutionPolicy Bypass -File ""{app}\launch.ps1"""; \
  Description: "Launch Walk To Mordor"; \
  Flags: postinstall skipifsilent runhidden

[Code]
function IsSilent: Boolean;
begin
  Result := WizardSilent;
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  ResultCode: Integer;
  Params: String;
begin
  { Stop the old daemon before [Files] tries to replace its exe, otherwise
    Windows keeps the old binary locked and the upgrade silently runs old
    code. This also stops a source-run `pythonw bridge\daemon.py`. }
  ExtractTemporaryFile('stop_daemon.ps1');
  Params := '-NoProfile -ExecutionPolicy Bypass -File "' +
            ExpandConstant('{tmp}\stop_daemon.ps1') + '"';
  if not Exec('powershell.exe', Params, '', SW_HIDE,
              ewWaitUntilTerminated, ResultCode) then
  begin
    Result := 'Could not run PowerShell to stop the old daemon. ' +
              'Close Walk to Mordor and run the installer again.';
    Exit;
  end;
  if ResultCode <> 0 then
  begin
    Result := 'Could not stop the old daemon (exit code ' +
              IntToStr(ResultCode) + '). Close it and run the installer again.';
    Exit;
  end;
  Result := '';
end;

function InitializeSetup(): Boolean;
begin
  Result := True;
end;

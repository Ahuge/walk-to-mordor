; Walk to Mordor installer script for Inno Setup 6.
; Build with: tools/build_installer.py (runs ISCC automatically)
; Or manually: "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" installer/walk-to-mordor.iss

#define MyAppName "Walk to Mordor"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "Alex Hughes"

[Setup]
AppId={{8F4E3B2A-1C5D-4E7F-9A8B-3D2C1E0F5A6B}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppSupportURL=https://github.com/Ahuge/walk-to-mordor
DefaultDirName={autopf}\WalkToMordor
DefaultGroupName=Walk to Mordor
OutputDir=..\dist
OutputBaseFilename=WalkToMordorSetup-{#MyAppVersion}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
DisableDirPage=no

[Files]
Source: "..\dist\WalkToMordorDaemon.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\dist\WalkToMordorWidget.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\dist\WalkToMordorNudge.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "launch.ps1"; DestDir: "{app}"; Flags: ignoreversion
Source: "harden_tasks.ps1"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\Walk to Mordor Dashboard"; Filename: "http://127.0.0.1:8471/"
Name: "{group}\Walk to Mordor Widget"; Filename: "{app}\WalkToMordorWidget.exe"
Name: "{group}\Uninstall Walk to Mordor"; Filename: "{uninstallexe}"

[Run]
; Register the daemon as a logon task (starts the BLE bridge + API).
Filename: "schtasks"; \
  Parameters: "/create /tn ""WalkToMordor"" /tr ""\""{app}\WalkToMordorDaemon.exe\"""" /sc onlogon /rl limited /f"; \
  Flags: runhidden; StatusMsg: "Registering background service…"
; Register the widget as a logon task with a 30s delay (daemon first).
Filename: "schtasks"; \
  Parameters: "/create /tn ""WalkToMordorWidget"" /tr ""\""{app}\WalkToMordorWidget.exe\"""" /sc onlogon /delay 0000:30 /rl limited /f"; \
  Flags: runhidden; StatusMsg: "Registering widget…"
; Daily nudge at 11am if no walk yet.
Filename: "schtasks"; \
  Parameters: "/create /tn ""WalkToMordorNudge"" /tr ""\""{app}\WalkToMordorNudge.exe\"""" /sc daily /st 11:00 /rl limited /f"; \
  Flags: runhidden; StatusMsg: "Registering daily reminder…"
; schtasks cannot set restart-on-failure or battery options; apply them now.
Filename: "powershell"; \
  Parameters: "-NoProfile -ExecutionPolicy Bypass -File ""{app}\harden_tasks.ps1"""; \
  Flags: runhidden; StatusMsg: "Hardening background tasks…"

[UninstallRun]
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
function InitializeSetup(): Boolean;
begin
  Result := True;
end;

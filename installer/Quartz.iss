#define MyAppName "Quartz"
#ifndef MyAppVersion
#define MyAppVersion "1.0.0"
#endif
#ifndef PackageDir
  #error PackageDir is required; use build_installer.ps1 with a clean audited package.
#endif
#ifndef ReleaseOutput
  #error ReleaseOutput is required.
#endif
#define MyAppPublisher "Ali Mehdi"
#define MyAppExeName "Quartz.exe"
; Require the approved Q rather than silently falling back to legacy ring art.
#define BrandIcon "..\assets\branding\quartz-q.ico"

[Setup]
AppId={{7EC663D2-123D-4DBD-9C6B-7C3A2F8B0E42}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
VersionInfoCompany={#MyAppPublisher}
VersionInfoDescription=Quartz Desktop Assistant Setup
VersionInfoProductName={#MyAppName}
VersionInfoProductVersion={#MyAppVersion}
DefaultDirName={localappdata}\Programs\Quartz
DefaultGroupName=Quartz
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
OutputDir={#ReleaseOutput}
OutputBaseFilename=QuartzSetup-{#MyAppVersion}
SetupIconFile={#BrandIcon}
UninstallDisplayIcon={app}\{#MyAppExeName}
UninstallDisplayName=Quartz {#MyAppVersion}
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
RestartApplications=no
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0.17763

[Languages]
Name: "turkish"; MessagesFile: "compiler:Languages\Turkish.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: checkedonce
Name: "startup"; Description: "Quartz'ı Windows açılışında başlat"; GroupDescription: "Başlangıç"; Flags: unchecked

[Files]
Source: "{#PackageDir}\Quartz.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#PackageDir}\_internal\*"; DestDir: "{app}\_internal"; Flags: ignoreversion recursesubdirs createallsubdirs
; README is optional documentation; EXE, runtime resources and brand ICO remain required.
Source: "{#PackageDir}\README.txt"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#PackageDir}\release-manifest.json"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\Quartz"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; IconFilename: "{app}\{#MyAppExeName}"; AppUserModelID: "AliMehdi.Quartz.Workspace"
Name: "{autodesktop}\Quartz"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; IconFilename: "{app}\{#MyAppExeName}"; AppUserModelID: "AliMehdi.Quartz.Workspace"; Tasks: desktopicon
Name: "{userstartup}\Quartz"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; IconFilename: "{app}\{#MyAppExeName}"; AppUserModelID: "AliMehdi.Quartz.Workspace"; Tasks: startup
Name: "{group}\Quartz'ı Kaldır"; Filename: "{uninstallexe}"

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Quartz'ı şimdi başlat"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: files; Name: "{app}\assistant.log"
Type: files; Name: "{app}\quartz_entry.log"
Type: files; Name: "{app}\*.log.*"
Type: filesandordirs; Name: "{app}\vision_captures"

[Code]
procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssInstall then
  begin
    RegDeleteValue(HKCU, 'Software\Microsoft\Windows\CurrentVersion\Run', 'Quartz');
  end;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if CurUninstallStep = usUninstall then
  begin
    RegDeleteValue(HKCU, 'Software\Microsoft\Windows\CurrentVersion\Run', 'Quartz');
    if SuppressibleMsgBox(
      'Sohbet geçmişi, hafıza ve API ayarları da silinsin mi?',
      mbConfirmation, MB_YESNO, IDNO) = IDYES then
    begin
      DeleteFile(ExpandConstant('{app}\chat_history.json'));
      DeleteFile(ExpandConstant('{app}\quartz_memory.json'));
      DeleteFile(ExpandConstant('{app}\quartz_tasks.json'));
      DeleteFile(ExpandConstant('{app}\quartz_operation.json'));
      DeleteFile(ExpandConstant('{app}\quartz_workflows.json'));
      DeleteFile(ExpandConstant('{app}\local_search_index.json'));
      DeleteFile(ExpandConstant('{app}\.env'));
    end;
  end;
end;

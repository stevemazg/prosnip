; ProSnip-Bob installer. The version and the onedir folder are passed in:
;   ISCC /DAppVersion=1.8.5.0 /DSourceDir=...\dist\ProSnip-Bob-1.8.5.0-win64 prosnip.iss

#ifndef AppVersion
  #define AppVersion "1.8.5.0"
#endif
#ifndef SourceDir
  #define SourceDir "..\dist\ProSnip-Bob"
#endif

#define AppName "ProSnip-Bob"
#define AppExe "ProSnip-Bob.exe"
#define AppPublisher "Steve Maz"

[Setup]
AppId={{7B2E9C41-5A18-4F6D-9E33-1C8A6D4F2B70}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher={#AppPublisher}
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
OutputDir=..\dist
OutputBaseFilename={#AppName}-{#AppVersion}-Setup
SetupIconFile=..\assets\prosnip-bob.ico
WizardImageFile=..\assets\wizard-image.bmp
WizardSmallImageFile=..\assets\wizard-small.bmp
UninstallDisplayIcon={app}\{#AppExe}
UninstallDisplayName={#AppName}
VersionInfoVersion={#AppVersion}
VersionInfoCompany={#AppPublisher}
VersionInfoProductName={#AppName}
VersionInfoDescription=ProSnip-Bob screen capture and annotation tool
LicenseFile=..\LICENSE
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
CloseApplications=yes
RestartApplications=no
AppMutex=ProSnipBobSetup
ArchitecturesAllowed=x64
ArchitecturesInstallIn64BitMode=x64
Compression=lzma2
SolidCompression=yes

[Languages]
Name: "en"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; Flags: unchecked
Name: "startup"; Description: "Start ProSnip-Bob when Windows starts"; Flags: unchecked

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\THIRD_PARTY_NOTICES"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon
Name: "{commonstartup}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: startup; Check: IsAdminInstallMode
Name: "{userstartup}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: startup; Check: not IsAdminInstallMode

[Run]
Filename: "{app}\{#AppExe}"; Description: "Launch ProSnip-Bob"; Flags: nowait postinstall skipifsilent

[Code]
procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then
    SaveStringToFile(ExpandConstant('{app}\installed.txt'), 'ProSnip-Bob' + Chr(13) + Chr(10), False);
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if (CurUninstallStep = usUninstall) and (not UninstallSilent) then
  begin
    if MsgBox('Remove ProSnip-Bob captures and settings from your user folder as well? They are kept if you choose No.', mbConfirmation, MB_YESNO) = IDYES then
    begin
      DelTree(ExpandConstant('{localappdata}\ProSnip-Bob'), True, True, True);
      DelTree(ExpandConstant('{localappdata}\ProSnip'), True, True, True);
      DelTree(ExpandConstant('{userappdata}\ProSnip-Bob'), True, True, True);
    end;
  end;
end;

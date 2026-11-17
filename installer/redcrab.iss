; Red Crab: the installer.  Built by build.py (it passes AppVersion, Stage, OutDir, SmallImage); see README.
; Per user by default (no admin), the folder can be chosen; "for all users" (Program Files) asks for admin.
; Updates: the same AppId installs over the old one in its folder: the pets quit first (and the album and Connect AI
; windows close: they hold the embedded Python's files) and start after; the save
; (%APPDATA%\Clawd) and the hooks are left alone.  Uninstall: clawd uninstall (pets quit, hooks out, start with
; Windows off, the one backup kept beside each agent's settings removed), then a question whether to delete the save
; too (no by default).

#ifndef AppVersion
  #define AppVersion "1.0.0"
#endif

[Setup]
AppId={{6C7E2A51-4B0F-4D8E-9F3A-2D5C1B7E9A40}
AppName={cm:AppName}
AppVersion={#AppVersion}
AppVerName={cm:AppName} {#AppVersion}
AppPublisher=BigBrother
AppCopyright=Copyright (C) 2026 BigBrother
VersionInfoVersion={#AppVersion}
DefaultDirName={autopf}\RedCrab
DisableDirPage=no
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
OutputDir={#OutDir}
OutputBaseFilename=RedCrab-Setup-{#AppVersion}
SetupIconFile={#Stage}\clawd.ico
WizardSmallImageFile={#SmallImage}
UninstallDisplayIcon={app}\clawd.ico
UninstallDisplayName={cm:AppName}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ShowLanguageDialog=auto
LanguageDetectionMethod=uilanguage
CloseApplications=yes
RestartApplications=no

[Languages]
Name: "en"; MessagesFile: "compiler:Default.isl"
Name: "zh"; MessagesFile: "ChineseSimplified.isl"

[CustomMessages]
en.AppName=Red Crab
zh.AppName=红螃蟹
en.RunNow=Start Red Crab now
zh.RunNow=现在启动红螃蟹
en.DeleteSave=Delete Red Crab's save too (levels, treasures, the album)?%n%nIt is in %1.%nKeep it, and installing again picks up where you left off.
zh.DeleteSave=把红螃蟹的存档（等级、宝贝、图鉴）也删掉吗？%n%n存档在 %1。%n留着的话，以后重新安装还能接着玩。

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[InstallDelete]
; frames of an older version: a clip that was dropped does not linger
Type: files; Name: "{app}\frames\*.frames"
Type: files; Name: "{app}\frames_hi\*.frames"

[Files]
Source: "{#Stage}\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{autoprograms}\{cm:AppName}"; Filename: "{app}\python\pythonw.exe"; Parameters: """{app}\clawd.py"""; WorkingDir: "{app}"; IconFilename: "{app}\clawd.ico"
Name: "{autodesktop}\{cm:AppName}"; Filename: "{app}\python\pythonw.exe"; Parameters: """{app}\clawd.py"""; WorkingDir: "{app}"; IconFilename: "{app}\clawd.ico"; Tasks: desktopicon

[Run]
Filename: "{app}\python\pythonw.exe"; Parameters: """{app}\clawd.py"""; WorkingDir: "{app}"; Description: "{cm:RunNow}"; Flags: postinstall nowait skipifsilent runasoriginaluser

[UninstallDelete]
; made while running: the sets scaled to other sizes, their log, Python's caches, the whole embedded Python
Type: filesandordirs; Name: "{app}\frames_custom*"
Type: files; Name: "{app}\render.log*"
Type: files; Name: "{app}\clawd-write-test.tmp"
Type: filesandordirs; Name: "{app}\__pycache__"
Type: filesandordirs; Name: "{app}\python"
Type: dirifempty; Name: "{app}\frames"
Type: dirifempty; Name: "{app}\frames_hi"
Type: dirifempty; Name: "{app}"

[Code]
var
  DeleteSave: Boolean;

{ clawd.py <args> with the installed Python, hidden, waited for }
procedure RunClawd(const App, Args: String);
var
  Code: Integer;
begin
  if FileExists(App + '\clawd.py') and FileExists(App + '\python\python.exe') then
    Exec(App + '\python\python.exe', '-I "' + App + '\clawd.py" ' + Args, App, SW_HIDE, ewWaitUntilTerminated, Code);
end;

{ the pets hold the mutex until they are gone (at most 10 s) }
procedure WaitPetsGone;
var
  I: Integer;
begin
  for I := 1 to 50 do
  begin
    if not CheckForMutexes('Local\ClawdDesktopPet') then
      Exit;
    Sleep(200);
  end;
end;

{ an update: the pets of the old version quit before its files are replaced }
function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  App: String;
begin
  Result := '';
  App := ExpandConstant('{app}');
  if FileExists(App + '\clawd.py') then
  begin
    RunClawd(App, 'off --all --quiet');
    WaitPetsGone;
  end;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  Save: String;
begin
  Save := ExpandConstant('{userappdata}\Clawd');
  if CurUninstallStep = usUninstall then
  begin
    RunClawd(ExpandConstant('{app}'), 'uninstall --quiet');
    WaitPetsGone;
    if DirExists(Save) and not UninstallSilent then
      DeleteSave := MsgBox(FmtMessage(CustomMessage('DeleteSave'), [Save]), mbConfirmation,
                           MB_YESNO or MB_DEFBUTTON2) = IDYES;
  end;
  if CurUninstallStep = usPostUninstall then
  begin
    { the sets scaled for an install the user could not write to (Program Files) }
    DelTree(ExpandConstant('{localappdata}\Clawd'), True, True, True);
    if DeleteSave then
      DelTree(Save, True, True, True);
  end;
end;

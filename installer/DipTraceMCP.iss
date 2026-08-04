#ifndef AppVersion
  #define AppVersion "0.2.1"
#endif
#ifndef StageDir
  #define StageDir "..\dist\windows-installer-stage"
#endif
#ifndef OutputDir
  #define OutputDir "..\dist\windows-installer"
#endif

[Setup]
AppId={{8A6BC0A8-DA77-4C95-8D3B-2A43A1B04D55}
AppName=DipTrace MCP
AppVersion={#AppVersion}
AppVerName=DipTrace MCP {#AppVersion}
AppPublisher=DipTrace MCP contributors
AppPublisherURL=https://github.com/fireostendere/mcp_diptrace
AppSupportURL=https://github.com/fireostendere/mcp_diptrace/issues
DefaultDirName={localappdata}\Programs\DipTraceMCP
DefaultGroupName=DipTrace MCP
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir={#OutputDir}
OutputBaseFilename=DipTrace-MCP-Setup-{#AppVersion}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
Uninstallable=yes
CloseApplications=yes
RestartApplications=no
SetupLogging=yes
LicenseFile={#StageDir}\LICENSE
AppReadmeFile={app}\README_FIRST.txt
UninstallDisplayIcon={app}\app\diptrace_mcp_server.exe

[Types]
Name: full; Description: Full install (server, bridge, DipTrace settings, client configuration)
Name: server; Description: Server only (no DipTrace plug-in integration)

[Components]
Name: server; Description: Standalone MCP server; Types: full server; Flags: fixed
Name: bridge; Description: DipTrace live bridge and settings; Types: full
Name: client; Description: Optional MCP client configuration; Types: full server

[Tasks]
Name: "configurecodex"; Description: "Configure Codex CLI"; Components: client; Flags: unchecked
Name: "configureclaude"; Description: "Configure Claude Desktop"; Components: client; Flags: unchecked

[Files]
Source: "{#StageDir}\app\*"; DestDir: "{app}\app"; Flags: ignoreversion recursesubdirs createallsubdirs; Components: server
Source: "{#StageDir}\bridge\diptrace_mcp_bridge.exe"; DestDir: "{app}\bridge"; Flags: ignoreversion; Components: bridge
Source: "{#StageDir}\settings-templates\*.xml"; DestDir: "{app}\settings-templates"; Flags: ignoreversion; Components: bridge
Source: "{#StageDir}\tools\*"; DestDir: "{app}\tools"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "{#StageDir}\docs\*"; DestDir: "{app}\docs"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "{#StageDir}\README_FIRST.txt"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#StageDir}\LICENSE"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#StageDir}\SHA256SUMS.txt"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\Configure DipTrace MCP"; Filename: "{app}\tools\diptrace_mcp_configure\diptrace_mcp_configure.exe"; Components: client
Name: "{group}\DipTrace MCP documentation"; Filename: "{app}\README_FIRST.txt"

[Run]
Filename: "powershell.exe"; Parameters: "-NoProfile -ExecutionPolicy Bypass -File ""{app}\tools\install_plugin.ps1"" -DipTraceDir ""{code:GetDipTraceDir}"" -BridgePath ""{app}\bridge\diptrace_mcp_bridge.exe"" -SettingsSourceDir ""{app}\settings-templates"""; StatusMsg: "Installing the DipTrace plug-in..."; Flags: runhidden waituntilterminated; Components: bridge; Check: ShouldInstallBridge
Filename: "{app}\tools\diptrace_mcp_configure\diptrace_mcp_configure.exe"; Parameters: "--client codex --server ""{app}\app\diptrace_mcp_server.exe"" --workspace ""{code:GetWorkspaceDir}"" --state-dir ""{code:GetStateDir}"""; StatusMsg: "Configuring Codex..."; Flags: runhidden waituntilterminated; Tasks: configurecodex
Filename: "{app}\tools\diptrace_mcp_configure\diptrace_mcp_configure.exe"; Parameters: "--client claude --server ""{app}\app\diptrace_mcp_server.exe"" --workspace ""{code:GetWorkspaceDir}"" --state-dir ""{code:GetStateDir}"""; StatusMsg: "Configuring Claude Desktop..."; Flags: runhidden waituntilterminated; Tasks: configureclaude
Filename: "{app}\app\diptrace_mcp_server.exe"; Parameters: "--help"; Description: "Verify the installed MCP server"; Flags: postinstall nowait skipifsilent unchecked; Components: server

[UninstallRun]
Filename: "powershell.exe"; Parameters: "-NoProfile -ExecutionPolicy Bypass -File ""{app}\tools\uninstall_plugin.ps1"" -DipTraceDir ""{code:GetDipTraceDir}"""; Flags: runhidden waituntilterminated; Components: bridge
Filename: "powershell.exe"; Parameters: "-NoProfile -ExecutionPolicy Bypass -File ""{app}\tools\remove_owned_state.ps1"" -StateDir ""{code:GetStateDir}"" -InstallDir ""{app}"" -RemoveState={code:GetRemoveStateFlag}"; Flags: runhidden waituntilterminated

[Code]
var
  DipTracePage: TInputDirWizardPage;
  WorkspacePage: TInputDirWizardPage;
  StatePage: TInputDirWizardPage;
  RemoveState: Boolean;

function ResolveDefaultDipTraceDir(): String;
begin
  if DirExists(ExpandConstant('{pf}\DipTrace')) then
    Result := ExpandConstant('{pf}\DipTrace')
  else if DirExists(ExpandConstant('{pf32}\DipTrace')) then
    Result := ExpandConstant('{pf32}\DipTrace')
  else
    Result := ExpandConstant('{pf}\DipTrace');
end;

function NormalizeDir(Value: String): String;
begin
  Result := RemoveBackslashUnlessRoot(ExpandFileName(Value));
end;

function GetDipTraceDir(Param: String): String;
begin
  if Assigned(DipTracePage) then
    Result := NormalizeDir(DipTracePage.Values[0])
  else
    Result := NormalizeDir(ExpandConstant('{param:DIPTRACE|' + ResolveDefaultDipTraceDir() + '}'));
end;

function GetWorkspaceDir(Param: String): String;
begin
  if Assigned(WorkspacePage) then
    Result := NormalizeDir(WorkspacePage.Values[0])
  else
    Result := NormalizeDir(ExpandConstant('{param:WORKSPACE|{userdocs}\DipTrace}'));
end;

function GetStateDir(Param: String): String;
begin
  if Assigned(StatePage) then
    Result := NormalizeDir(StatePage.Values[0])
  else
    Result := NormalizeDir(ExpandConstant('{param:STATEDIR|{localappdata}\DipTraceMCP}'));
end;

function GetRemoveStateFlag(Param: String): String;
begin
  if RemoveState then
    Result := 'true'
  else
    Result := 'false';
end;

function ShouldInstallBridge(): Boolean;
begin
  Result := WizardIsComponentSelected('bridge') and DirExists(GetDipTraceDir(''));
end;

procedure InitializeWizard();
begin
  DipTracePage := CreateInputDirPage(wpSelectComponents,
    'DipTrace installation',
    'Choose the DipTrace installation directory.',
    'The plug-in will be installed only when the bridge component is selected.');
  DipTracePage.Add('');
  DipTracePage.Values[0] := ResolveDefaultDipTraceDir();

  WorkspacePage := CreateInputDirPage(DipTracePage.ID,
    'Project workspace',
    'Choose the allowed DipTrace project workspace.',
    'The MCP server will use this directory as its default workspace.');
  WorkspacePage.Add('');
  WorkspacePage.Values[0] := ExpandConstant('{userdocs}\DipTrace');

  StatePage := CreateInputDirPage(WorkspacePage.ID,
    'Local state directory',
    'Choose where DipTrace MCP stores local records and live-session state.',
    'This directory is preserved by default during uninstall.');
  StatePage.Add('');
  StatePage.Values[0] := ExpandConstant('{localappdata}\DipTraceMCP');
end;

function InitializeSetup(): Boolean;
begin
  Result := True;
end;

function NextButtonClick(CurPageID: Integer): Boolean;
begin
  Result := True;
  if Assigned(DipTracePage) and (CurPageID = DipTracePage.ID) and WizardIsComponentSelected('bridge') then
  begin
    if not DirExists(GetDipTraceDir('')) then
    begin
      MsgBox('The selected DipTrace directory does not exist.', mbError, MB_OK);
      Result := False;
      exit;
    end;
  end;
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  ManifestTool: String;
  Args: String;
  ResultCode: Integer;
begin
  Result := '';
  ManifestTool := ExpandConstant('{app}\tools\write_installation_manifest.ps1');
  if not FileExists(ManifestTool) then
    exit;
  Args := '-NoProfile -ExecutionPolicy Bypass -File "' + ManifestTool + '"' +
    ' -InstallDir "' + ExpandConstant('{app}') + '"' +
    ' -StateDir "' + GetStateDir('') + '"' +
    ' -Workspace "' + GetWorkspaceDir('') + '"' +
    ' -DipTraceDir "' + GetDipTraceDir('') + '"' +
    ' -Version "{#AppVersion}"';
  if not Exec('powershell.exe', Args, '', SW_HIDE, ewWaitUntilTerminated, ResultCode) then
    Result := 'Could not start installation manifest writer.'
  else if ResultCode <> 0 then
    Result := 'Installation manifest writer failed with code ' + IntToStr(ResultCode) + '.';
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  Marker: String;
begin
  if CurStep = ssPostInstall then
  begin
    Marker := ExpandConstant('{app}\state-dir.txt');
    SaveStringToFile(Marker, GetStateDir('') + #13#10, False);
  end;
end;

function InitializeUninstall(): Boolean;
begin
  RemoveState := ExpandConstant('{param:REMOVE_STATE|false}') = 'true';
  Result := True;
end;

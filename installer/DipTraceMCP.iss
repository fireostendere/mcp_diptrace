#ifndef AppVersion
  #define AppVersion "0.2.0"
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
Name: custom; Description: Custom install; Flags: iscustom

[Components]
Name: server; Description: Standalone MCP server and runtime; Types: full server custom; Flags: fixed
Name: plugin; Description: DipTrace bridge and four settings profiles; Types: full custom

[Files]
Source: "{#StageDir}\app\*"; DestDir: "{app}\app"; Components: server; Flags: recursesubdirs createallsubdirs ignoreversion
Source: "{#StageDir}\bridge\*"; DestDir: "{app}\bridge"; Components: plugin; Flags: recursesubdirs createallsubdirs ignoreversion
Source: "{#StageDir}\settings-templates\*"; DestDir: "{app}\settings-templates"; Components: plugin; Flags: recursesubdirs createallsubdirs ignoreversion
Source: "{#StageDir}\tools\*"; DestDir: "{app}\tools"; Flags: recursesubdirs createallsubdirs ignoreversion
Source: "{#StageDir}\LICENSE"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#StageDir}\README_FIRST.txt"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#StageDir}\VERSION"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#StageDir}\artifact-inventory.json"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#StageDir}\installation-manifest.template.json"; DestDir: "{app}"; DestName: "installation-manifest.json"; Flags: ignoreversion

[Icons]
Name: "{group}\DipTrace MCP README"; Filename: "{app}\README_FIRST.txt"
Name: "{group}\DipTrace MCP Configurator"; Filename: "{app}\tools\diptrace_mcp_configure\diptrace_mcp_configure.exe"

[UninstallDelete]
Type: files; Name: "{app}\plugin-targets.txt"
Type: files; Name: "{app}\state-dir.txt"
Type: dirifempty; Name: "{app}"

[Code]
const
  ClientCodex = 0;
  ClientClaude = 1;
  ClientBoth = 2;
  ClientNone = 3;
  UninstallRoot = 'Software\Microsoft\Windows\CurrentVersion\Uninstall';

var
  DipTracePage: TInputOptionWizardPage;
  DipTraceBrowsePage: TInputDirWizardPage;
  WorkspacePage: TInputDirWizardPage;
  StatePage: TInputDirWizardPage;
  ClientPage: TInputOptionWizardPage;
  DetectedDipTrace: array of string;
  SelectedDipTrace: string;
  RemoveClientCheck: TNewCheckBox;
  RemoveStateCheck: TNewCheckBox;
  InstallLogPath: string;
  InstallationFinalized: Boolean;
  PluginSelection: Boolean;
  ResolvedStateDir: string;
  ResolvedWorkspaceDir: string;

function IsDipTraceLayout(const Root: string): Boolean;
begin
  Result :=
    FileExists(AddBackslash(Root) + 'Pcb.exe') or
    FileExists(AddBackslash(Root) + 'Schematic.exe') or
    FileExists(AddBackslash(Root) + 'CompEdit.exe') or
    FileExists(AddBackslash(Root) + 'PattEdit.exe') or
    DirExists(AddBackslash(Root) + 'Plugins\Pcb') or
    DirExists(AddBackslash(Root) + 'Plugins\Schematic') or
    DirExists(AddBackslash(Root) + 'Plugins\CompEdit') or
    DirExists(AddBackslash(Root) + 'Plugins\PattEdit');
end;

function HasCommandLineParam(const Name: string): Boolean;
var
  I: Integer;
begin
  Result := False;
  for I := 1 to ParamCount do
    if CompareText(ParamStr(I), Name) = 0 then begin
      Result := True;
      Exit;
    end;
end;

function IsSamePath(const Left, Right: string): Boolean;
begin
  Result := CompareText(Trim(AddBackslash(Left)), Trim(AddBackslash(Right))) = 0;
end;

function IsPathUnder(const Path, Root: string): Boolean;
var
  NormalPath, NormalRoot: string;
begin
  NormalPath := RemoveBackslash(ExpandFileName(Path));
  NormalRoot := RemoveBackslash(ExpandFileName(Root));
  Result := IsSamePath(NormalPath, NormalRoot) or
    (CompareText(Copy(NormalPath, 1, Length(NormalRoot) + 1), AddBackslash(NormalRoot)) = 0);
end;

procedure AddDipTraceCandidate(const Candidate: string; const Source: string);
var
  I: Integer;
  Root: string;
begin
  if not IsDipTraceLayout(Candidate) then Exit;
  Root := ExpandFileName(Candidate);
  for I := 0 to GetArrayLength(DetectedDipTrace) - 1 do
    if IsSamePath(DetectedDipTrace[I], Root) then Exit;
  SetArrayLength(DetectedDipTrace, GetArrayLength(DetectedDipTrace) + 1);
  DetectedDipTrace[GetArrayLength(DetectedDipTrace) - 1] := Root;
  DipTracePage.Add(ExtractFileName(RemoveBackslash(Root)) + ' — ' + Root + ' [' + Source + ']');
end;

procedure AddRegistryDipTraceCandidates(const Hive: Integer);
var
  Names: TArrayOfString;
  I: Integer;
  Key: string;
  DisplayName, InstallLocation: string;
begin
  if not RegGetSubkeyNames(Hive, UninstallRoot, Names) then Exit;
  for I := 0 to GetArrayLength(Names) - 1 do begin
    Key := UninstallRoot + '\' + Names[I];
    DisplayName := '';
    InstallLocation := '';
    if RegQueryStringValue(Hive, Key, 'DisplayName', DisplayName) and
       RegQueryStringValue(Hive, Key, 'InstallLocation', InstallLocation) and
       (Pos('diptrace', Lowercase(DisplayName)) > 0) then
      AddDipTraceCandidate(InstallLocation, 'registry');
  end;
end;

function IsPluginSelected: Boolean;
begin
  Result := PluginSelection;
end;

function SelectedClientName: string;
begin
  case ClientPage.SelectedValueIndex of
    ClientCodex: Result := 'codex';
    ClientClaude: Result := 'claude';
    ClientBoth: Result := 'both';
  else
    Result := 'none';
  end;
end;

function ParameterValue(const Name, DefaultValue: string): string;
var
  I: Integer;
  Argument: string;
  Prefix: string;
begin
  Result := ExpandConstant('{param:' + Name + '|' + DefaultValue + '}');
  Prefix := '/' + Lowercase(Name) + '=';
  for I := 1 to ParamCount do begin
    Argument := ParamStr(I);
    if CompareText(Copy(Argument, 1, Length(Prefix)), Prefix) = 0 then begin
      Result := Copy(Argument, Length(Prefix) + 1, Length(Argument));
      if Length(Result) >= 2 then
        if (Result[1] = '"') and (Result[Length(Result)] = '"') then
          Result := Copy(Result, 2, Length(Result) - 2);
      Exit;
    end;
  end;
end;

function SelectedStateDir: string;
begin
  Result := Trim(ResolvedStateDir);
  if Result = '' then Result := ExpandConstant('{localappdata}\DipTraceMCP');
end;

function SelectedWorkspaceDir: string;
begin
  Result := Trim(ResolvedWorkspaceDir);
  if Result = '' then Result := ExpandConstant('{userdocs}\DipTrace');
end;

procedure AppendInstallLog(const Line: string);
begin
  if InstallLogPath = '' then Exit;
  if not SaveStringToFile(InstallLogPath, GetDateTimeString('yyyy-mm-dd hh:nn:ss', '-', ':') + ' ' + Line + #13#10, True) then
    RaiseException('Unable to write the installation log');
end;

procedure SaveUtf8Line(const FileName, Line: string);
var
  Lines: TArrayOfString;
begin
  SetArrayLength(Lines, 1);
  Lines[0] := Line;
  SaveStringsToUTF8FileWithoutBOM(FileName, Lines, False);
end;

function RunPowerShell(const Parameters: string; const Elevated: Boolean; var ResultCode: Integer): Boolean;
var
  PowerShell: string;
begin
  PowerShell := ExpandConstant('{sys}\WindowsPowerShell\v1.0\powershell.exe');
  if Elevated then
    Result := ShellExec('runas', PowerShell, Parameters, '', SW_HIDE, ewWaitUntilTerminated, ResultCode)
  else
    Result := Exec(PowerShell, Parameters, '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
end;

function RunServerHelp: Boolean;
var
  ResultCode: Integer;
begin
  Result := Exec(ExpandConstant('{app}\app\diptrace_mcp_server.exe'), '--help', '', SW_HIDE, ewWaitUntilTerminated, ResultCode) and (ResultCode = 0);
end;

function CheckServerProcess: Boolean;
var
  ResultCode: Integer;
begin
  Result := RunPowerShell('-NoProfile -NonInteractive -Command "if (Get-Process -Name diptrace_mcp_server -ErrorAction SilentlyContinue) { exit 1 } else { exit 0 }"', False, ResultCode) and (ResultCode = 0);
end;

procedure CreateInstallationManifest;
var
  Parameters: string;
  ResultCode: Integer;
begin
  Parameters := '-NoProfile -NonInteractive -ExecutionPolicy Bypass -File "' + ExpandConstant('{app}\tools\write_installation_manifest.ps1') +
    '" -ManifestPath "' + ExpandConstant('{app}\installation-manifest.json') +
    '" -AppRoot "' + ExpandConstant('{app}') +
    '" -Version "' + ExpandConstant('{#AppVersion}') +
    '" -StateDir "' + SelectedStateDir + '"';
  if IsPluginSelected then
    Parameters := Parameters + ' -PluginRoots "' + SelectedDipTrace + '"';
  if not RunPowerShell(Parameters, False, ResultCode) or (ResultCode <> 0) then
    RaiseException('Unable to create installation-manifest.json');
  SaveUtf8Line(ExpandConstant('{app}\state-dir.txt'), SelectedStateDir);
  SaveUtf8Line(ExpandConstant('{app}\plugin-targets.txt'), SelectedDipTrace);
end;

procedure InstallDipTracePlugin;
var
  Parameters: string;
  ResultCode: Integer;
  NeedsElevation: Boolean;
begin
  if not IsPluginSelected then Exit;
  Parameters := '-NoProfile -NonInteractive -ExecutionPolicy Bypass -File "' + ExpandConstant('{app}\tools\install_plugin.ps1') +
    '" -DipTraceDir "' + SelectedDipTrace +
    '" -Mode All -BridgeExe "' + ExpandConstant('{app}\bridge\diptrace_mcp_bridge.exe') + '"';
  NeedsElevation := IsPathUnder(SelectedDipTrace, ExpandConstant('{commonpf}')) or
    IsPathUnder(SelectedDipTrace, ExpandConstant('{commonpf32}'));
  AppendInstallLog('DipTrace plugin integration requested; elevation may be required.');
  if not RunPowerShell(Parameters, NeedsElevation, ResultCode) or (ResultCode <> 0) then
    RaiseException('DipTrace plug-in installation failed. No client configuration was attempted.');
  AppendInstallLog('DipTrace plugin integration completed.');
end;

procedure RollbackDipTracePlugin;
var
  Parameters: string;
  ResultCode: Integer;
  NeedsElevation: Boolean;
begin
  if not IsPluginSelected or (SelectedDipTrace = '') then Exit;
  Parameters := '-NoProfile -NonInteractive -ExecutionPolicy Bypass -File "' + ExpandConstant('{app}\tools\uninstall_plugin.ps1') +
    '" -DipTraceDir "' + SelectedDipTrace + '" -InstallScript "' + ExpandConstant('{app}\tools\install_plugin.ps1') + '"';
  NeedsElevation := IsPathUnder(SelectedDipTrace, ExpandConstant('{commonpf}')) or
    IsPathUnder(SelectedDipTrace, ExpandConstant('{commonpf32}'));
  if not RunPowerShell(Parameters, NeedsElevation, ResultCode) or (ResultCode <> 0) then
    AppendInstallLog('WARNING: automatic DipTrace plug-in rollback failed.')
  else
    AppendInstallLog('DipTrace plug-in rollback completed.');
end;

procedure ConfigureMcpClient;
var
  Parameters: string;
  ResultCode: Integer;
begin
  if ClientPage.SelectedValueIndex = ClientNone then begin
    AppendInstallLog('MCP client configuration skipped by user.');
    Exit;
  end;
  Parameters := '--client ' + SelectedClientName + ' --workspace "' + SelectedWorkspaceDir +
    '" --state-dir "' + SelectedStateDir + '" --server "' +
    ExpandConstant('{app}\app\diptrace_mcp_server.exe') + '" --json';
  if not Exec(ExpandConstant('{app}\tools\diptrace_mcp_configure\diptrace_mcp_configure.exe'), Parameters, '', SW_HIDE, ewWaitUntilTerminated, ResultCode) or (ResultCode <> 0) then
    RaiseException('MCP client configuration failed closed. The original client configuration was preserved.');
  AppendInstallLog('MCP client configuration completed or deferred with a manual command.');
end;

procedure FinalizeInstallation;
var
  StateDir: string;
  InstallStamp: string;
begin
  if InstallationFinalized then Exit;
  InstallationFinalized := True;
  StateDir := ResolvedStateDir;
  if StateDir = '' then
    StateDir := ExpandConstant('{localappdata}\DipTraceMCP');
  CreateInstallationManifest;
  InstallStamp := GetDateTimeString('yyyymmdd-hhnnss', '-', '-');
  InstallLogPath := AddBackslash(StateDir) + 'logs\install-' + InstallStamp + '.log';
  if not ForceDirectories(ExtractFileDir(InstallLogPath)) then
    RaiseException('Unable to create the installation log directory');
  AppendInstallLog('Installation started. No secrets or client-config contents are logged.');
  if not RunServerHelp then
    RaiseException('Standalone server verification failed: diptrace_mcp_server.exe --help');
  AppendInstallLog('Standalone server --help smoke passed.');
  try
    InstallDipTracePlugin;
    ConfigureMcpClient;
  except
    RollbackDipTracePlugin;
    RaiseException('Installation failed; DipTrace plugin rollback was attempted.');
  end;
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  { ssDone is retained as a defensive fallback for silent bootstrapper runs. }
  if (CurStep = ssPostInstall) or (CurStep = ssDone) then
    FinalizeInstallation;
end;

function PrepareToInstall(var NeedsRestart: Boolean): string;
begin
  Result := '';
  NeedsRestart := False;
  if not CheckServerProcess then begin
    Result := 'Close diptrace_mcp_server.exe and retry. An active server/session is not terminated automatically.';
    Exit;
  end;
  if IsPluginSelected and (SelectedDipTrace = '') then
    Result := 'Select a validated DipTrace installation or choose Server only.';
end;

function ShouldSkipPage(PageID: Integer): Boolean;
begin
  Result := False;
  if (PageID = DipTracePage.ID) or (PageID = DipTraceBrowsePage.ID) then
    Result := not IsPluginSelected;
  if PageID = DipTraceBrowsePage.ID then
    Result := Result or (DipTracePage.SelectedValueIndex < GetArrayLength(DetectedDipTrace));
end;

function NextButtonClick(CurPageID: Integer): Boolean;
var
  Index: Integer;
begin
  Result := True;
  if CurPageID = DipTracePage.ID then begin
    Index := DipTracePage.SelectedValueIndex;
    if Index < GetArrayLength(DetectedDipTrace) then
      SelectedDipTrace := DetectedDipTrace[Index]
    else if Index = GetArrayLength(DetectedDipTrace) then
      SelectedDipTrace := ExpandFileName(DipTraceBrowsePage.Values[0])
    else if Index = GetArrayLength(DetectedDipTrace) + 1 then
      SelectedDipTrace := '';
  end;
  if CurPageID = wpSelectComponents then
    PluginSelection := WizardIsComponentSelected('plugin');
  if CurPageID = DipTraceBrowsePage.ID then begin
    SelectedDipTrace := ExpandFileName(DipTraceBrowsePage.Values[0]);
    if not IsDipTraceLayout(SelectedDipTrace) then begin
      MsgBox('The selected directory is not a recognized DipTrace installation. Select a root containing a known module executable or Plugins module directory.', mbError, MB_OK);
      Result := False;
    end;
  end;
  if CurPageID = WorkspacePage.ID then begin
    ResolvedWorkspaceDir := Trim(WorkspacePage.Values[0]);
    if WorkspacePage.Values[0] = '' then begin
      MsgBox('Choose a DipTrace workspace directory.', mbError, MB_OK);
      Result := False;
    end else if not DirExists(WorkspacePage.Values[0]) and not ForceDirectories(WorkspacePage.Values[0]) then begin
      MsgBox('The workspace directory could not be created.', mbError, MB_OK);
      Result := False;
    end;
  end;
  if CurPageID = StatePage.ID then begin
    ResolvedStateDir := Trim(StatePage.Values[0]);
    if IsPathUnder(StatePage.Values[0], ExpandConstant('{app}')) or
       IsPathUnder(StatePage.Values[0], ExpandConstant('{commonpf}')) or
       IsPathUnder(StatePage.Values[0], ExpandConstant('{commonpf32}')) then begin
      MsgBox('State must remain outside the installed application and Program Files.', mbError, MB_OK);
      Result := False;
    end else if not ForceDirectories(StatePage.Values[0]) then begin
      MsgBox('The state directory could not be created.', mbError, MB_OK);
      Result := False;
    end;
  end;
end;

procedure InitializeWizard;
var
  Root: string;
  ClientParam: string;
begin
  PluginSelection := not HasCommandLineParam('/SERVERONLY');
  DipTracePage := CreateInputOptionPage(wpSelectComponents, 'DipTrace installation', 'Choose DipTrace integration', 'Only a validated installation is offered for plug-in integration.', True, True);
  AddDipTraceCandidate(ExpandConstant('{commonpf}\DipTrace5'), 'Program Files');
  AddDipTraceCandidate(ExpandConstant('{commonpf}\DipTrace'), 'Program Files');
  AddDipTraceCandidate(ExpandConstant('{commonpf32}\DipTrace5'), 'Program Files (x86)');
  AddDipTraceCandidate(ExpandConstant('{commonpf32}\DipTrace'), 'Program Files (x86)');
  AddRegistryDipTraceCandidates(HKCU);
  AddRegistryDipTraceCandidates(HKLM);
  DipTracePage.Add('Browse for another validated DipTrace installation');
  DipTracePage.Add('Server only — do not install DipTrace integration');
  if GetArrayLength(DetectedDipTrace) = 0 then DipTracePage.SelectedValueIndex := 1
  else DipTracePage.SelectedValueIndex := 0;

  DipTraceBrowsePage := CreateInputDirPage(DipTracePage.ID, 'Browse for DipTrace', 'Select the DipTrace root', 'The directory must contain a known module executable or Plugins module directory.', False, '');
  DipTraceBrowsePage.Add('DipTrace root:');
  Root := ParameterValue('DIPTRACE', '');
  if Root <> '' then DipTraceBrowsePage.Values[0] := Root;

  WorkspacePage := CreateInputDirPage(DipTraceBrowsePage.ID, 'Project workspace', 'Choose DipTrace project workspace', 'The server will be restricted to this directory unless additional roots are configured later.', False, '');
  WorkspacePage.Add('Workspace:');
  ResolvedWorkspaceDir := ParameterValue('WORKSPACE', ExpandConstant('{userdocs}\DipTrace'));
  WorkspacePage.Values[0] := ResolvedWorkspaceDir;

  StatePage := CreateInputDirPage(WorkspacePage.ID, 'Local writable state', 'Choose local MCP state directory', 'Runtime state and logs are kept here, never under Program Files.', False, '');
  StatePage.Add('State directory:');
  ResolvedStateDir := ParameterValue('STATEDIR', ExpandConstant('{localappdata}\DipTraceMCP'));
  StatePage.Values[0] := ResolvedStateDir;

  ClientPage := CreateInputOptionPage(StatePage.ID, 'MCP client', 'Choose client configuration', 'Existing entries are updated idempotently and other servers are preserved.', True, True);
  ClientPage.Add('Configure Codex');
  ClientPage.Add('Configure Claude Desktop');
  ClientPage.Add('Configure both');
  ClientPage.Add('Skip client configuration');
  ClientPage.SelectedValueIndex := ClientNone;
  ClientParam := Lowercase(ParameterValue('CLIENT', ''));
  if ClientParam = 'codex' then ClientPage.SelectedValueIndex := ClientCodex
  else if ClientParam = 'claude' then ClientPage.SelectedValueIndex := ClientClaude
  else if ClientParam = 'both' then ClientPage.SelectedValueIndex := ClientBoth;
  Root := ParameterValue('DIPTRACE', '');
  if Root <> '' then begin
    DipTracePage.SelectedValueIndex := GetArrayLength(DetectedDipTrace);
    DipTraceBrowsePage.Values[0] := Root;
  end;
end;

procedure InitializeUninstallProgressForm;
begin
  RemoveClientCheck := TNewCheckBox.Create(UninstallProgressForm);
  RemoveClientCheck.Parent := UninstallProgressForm;
  RemoveClientCheck.Left := 16;
  RemoveClientCheck.Top := UninstallProgressForm.ClientHeight - 76;
  RemoveClientCheck.Width := UninstallProgressForm.ClientWidth - 32;
  RemoveClientCheck.Caption := 'Remove DipTrace MCP entries from Codex and Claude Desktop';
  RemoveClientCheck.Checked := HasCommandLineParam('/REMOVE_CLIENT_CONFIG');
  RemoveStateCheck := TNewCheckBox.Create(UninstallProgressForm);
  RemoveStateCheck.Parent := UninstallProgressForm;
  RemoveStateCheck.Left := 16;
  RemoveStateCheck.Top := UninstallProgressForm.ClientHeight - 52;
  RemoveStateCheck.Width := UninstallProgressForm.ClientWidth - 32;
  RemoveStateCheck.Caption := 'Remove local DipTrace MCP state and logs (projects are never removed)';
  RemoveStateCheck.Checked := HasCommandLineParam('/REMOVE_STATE');
end;

function UninstallStateDir: string;
var
  Lines: TArrayOfString;
begin
  Result := '';
  if LoadStringsFromFile(ExpandConstant('{app}\state-dir.txt'), Lines) and (GetArrayLength(Lines) > 0) then
    Result := Lines[0];
end;

function RemoveClientConfiguration: Boolean;
var
  ResultCode: Integer;
  StateDir: string;
  Parameters: string;
begin
  Result := True;
  StateDir := UninstallStateDir;
  Parameters := '--client both --unconfigure --state-dir "' + StateDir + '" --json';
  if not Exec(ExpandConstant('{app}\tools\diptrace_mcp_configure\diptrace_mcp_configure.exe'), Parameters, '', SW_HIDE, ewWaitUntilTerminated, ResultCode) or (ResultCode <> 0) then begin
    MsgBox('Client configuration was not changed because it was invalid or unavailable. The original files remain for manual recovery.', mbError, MB_OK);
    Result := False;
  end;
end;

function RemoveLocalState: Boolean;
var
  ResultCode: Integer;
  StateDir: string;
  Parameters: string;
begin
  Result := True;
  StateDir := UninstallStateDir;
  if StateDir = '' then Exit;
  Log('DipTrace MCP uninstall: removing owned local state');
  Parameters := '-NoProfile -NonInteractive -ExecutionPolicy Bypass -File "' + ExpandConstant('{app}\tools\remove_owned_state.ps1') + '" -ManifestPath "' + ExpandConstant('{app}\installation-manifest.json') + '"';
  if not RunPowerShell(Parameters, False, ResultCode) or (ResultCode <> 0) then begin
    Log('DipTrace MCP uninstall: owned state removal failed with code ' + IntToStr(ResultCode));
    if not UninstallSilent then
      MsgBox('Owned local state was not removed; projects and unknown files were preserved.', mbError, MB_OK);
    Result := False;
  end else
    Log('DipTrace MCP uninstall: owned local state removal completed');
end;

procedure RemoveDipTracePlugins;
var
  Lines: TArrayOfString;
  I, ResultCode: Integer;
  Parameters: string;
  NeedsElevation: Boolean;
begin
  if not LoadStringsFromFile(ExpandConstant('{app}\plugin-targets.txt'), Lines) then Exit;
  Log('DipTrace MCP uninstall: removing DipTrace plug-in targets');
  for I := 0 to GetArrayLength(Lines) - 1 do begin
    if Trim(Lines[I]) = '' then Continue;
    Parameters := '-NoProfile -NonInteractive -ExecutionPolicy Bypass -File "' + ExpandConstant('{app}\tools\uninstall_plugin.ps1') + '" -DipTraceDir "' + Trim(Lines[I]) + '" -InstallScript "' + ExpandConstant('{app}\tools\install_plugin.ps1') + '"';
    NeedsElevation := IsPathUnder(Trim(Lines[I]), ExpandConstant('{commonpf}')) or
      IsPathUnder(Trim(Lines[I]), ExpandConstant('{commonpf32}'));
    if not RunPowerShell(Parameters, NeedsElevation, ResultCode) or (ResultCode <> 0) then begin
      Log('DipTrace MCP uninstall: plug-in removal failed with code ' + IntToStr(ResultCode));
      if not UninstallSilent then
        MsgBox('A DipTrace plug-in directory could not be removed: ' + Trim(Lines[I]) + '. Remove only the listed DipTraceMCP folders manually.', mbError, MB_OK);
    end else
      Log('DipTrace MCP uninstall: plug-in removal completed');
  end;
end;

function InitializeUninstall: Boolean;
begin
  Result := True;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if CurUninstallStep <> usUninstall then Exit;
  if RemoveClientCheck.Checked and not RemoveClientConfiguration then Abort;
  RemoveDipTracePlugins;
  if RemoveStateCheck.Checked and not RemoveLocalState then Abort;
end;

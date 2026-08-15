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
#ifdef PluginOnly
AppId={{2B8F7A98-8744-4ED1-A2C5-31A827DF74C1}
AppName=DipTrace MCP Plug-in
AppVersion={#AppVersion}
AppVerName=DipTrace MCP Plug-in {#AppVersion}
DefaultDirName={autopf}\DipTraceMCPPlugin
DefaultGroupName=DipTrace MCP
PrivilegesRequired=admin
OutputBaseFilename=DipTrace-MCP-Plugin-Setup-{#AppVersion}
UninstallDisplayName=DipTrace MCP Plug-in {#AppVersion}
#else
AppId={{8A6BC0A8-DA77-4C95-8D3B-2A43A1B04D55}
AppName=DipTrace MCP
AppVersion={#AppVersion}
AppVerName=DipTrace MCP {#AppVersion}
DefaultDirName={localappdata}\Programs\DipTraceMCP
DefaultGroupName=DipTrace MCP
PrivilegesRequired=lowest
OutputBaseFilename=DipTrace-MCP-Setup-{#AppVersion}
AppReadmeFile={app}\README_FIRST.txt
UninstallDisplayIcon={app}\app\diptrace_mcp_server.exe
#endif
AppPublisher=DipTrace MCP contributors
AppPublisherURL=https://github.com/fireostendere/mcp_diptrace
AppSupportURL=https://github.com/fireostendere/mcp_diptrace/issues
DisableProgramGroupPage=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir={#OutputDir}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
Uninstallable=yes
CloseApplications=yes
RestartApplications=no
SetupLogging=yes
LicenseFile={#StageDir}\LICENSE

#ifndef PluginOnly
[Types]
Name: full; Description: Full user install (server and MCP client configuration)
Name: server; Description: Server only (skip MCP client configuration)
Name: custom; Description: Custom install; Flags: iscustom

[Components]
Name: server; Description: Standalone MCP server and runtime; Types: full server custom; Flags: fixed
#endif

[Files]
#ifdef PluginOnly
; The elevated installer is self-contained. It never reads executable/script
; payload from the per-user DipTrace MCP installation or LocalAppData.
Source: "{#StageDir}\bridge\diptrace_mcp_bridge.exe"; DestDir: "{app}\payload"; Flags: ignoreversion
Source: "{#StageDir}\settings-templates\pcb.settings.xml"; DestDir: "{app}\payload\settings"; Flags: ignoreversion
Source: "{#StageDir}\settings-templates\schematic.settings.xml"; DestDir: "{app}\payload\settings"; Flags: ignoreversion
Source: "{#StageDir}\settings-templates\component.settings.xml"; DestDir: "{app}\payload\settings"; Flags: ignoreversion
Source: "{#StageDir}\settings-templates\pattern.settings.xml"; DestDir: "{app}\payload\settings"; Flags: ignoreversion
Source: "{#StageDir}\LICENSE"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#StageDir}\VERSION"; DestDir: "{app}"; Flags: ignoreversion
#else
; The per-user installer contains no bridge/settings/install-plugin payload and
; never invokes an elevated child process.
Source: "{#StageDir}\app\*"; DestDir: "{app}\app"; Components: server; Flags: recursesubdirs createallsubdirs ignoreversion
Source: "{#StageDir}\tools\diptrace_mcp_configure\*"; DestDir: "{app}\tools\diptrace_mcp_configure"; Flags: recursesubdirs createallsubdirs ignoreversion
Source: "{#StageDir}\tools\write_installation_manifest.ps1"; DestDir: "{app}\tools"; Flags: ignoreversion
Source: "{#StageDir}\tools\remove_owned_state.ps1"; DestDir: "{app}\tools"; Flags: ignoreversion
Source: "{#StageDir}\LICENSE"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#StageDir}\README_FIRST.txt"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#StageDir}\VERSION"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#StageDir}\artifact-inventory.json"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#StageDir}\installation-manifest.template.json"; DestDir: "{app}"; DestName: "installation-manifest.json"; Flags: ignoreversion
#endif

#ifndef PluginOnly
[Icons]
Name: "{group}\DipTrace MCP README"; Filename: "{app}\README_FIRST.txt"
Name: "{group}\DipTrace MCP Configurator"; Filename: "{app}\tools\diptrace_mcp_configure\diptrace_mcp_configure.exe"

[UninstallDelete]
Type: files; Name: "{app}\state-dir.txt"
Type: dirifempty; Name: "{app}"
#endif

[Code]
#ifdef PluginOnly
const
  UninstallRoot = 'Software\Microsoft\Windows\CurrentVersion\Uninstall';

var
  DipTracePage: TInputOptionWizardPage;
  DipTraceBrowsePage: TInputDirWizardPage;
  DetectedDipTrace: array of string;
  SelectedDipTrace: string;
  PluginInstalled: Boolean;

function ParameterValue(const Name, DefaultValue: string): string;
var
  I: Integer;
  Argument, Prefix: string;
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

function IsSamePath(const Left, Right: string): Boolean;
begin
  Result := CompareText(Trim(AddBackslash(Left)), Trim(AddBackslash(Right))) = 0;
end;

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

procedure AddDipTraceCandidate(const Candidate, Source: string);
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
  Key, DisplayName, InstallLocation: string;
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

procedure SaveUtf8Line(const FileName, Line: string);
var
  Lines: TArrayOfString;
begin
  SetArrayLength(Lines, 1);
  Lines[0] := Line;
  SaveStringsToUTF8FileWithoutBOM(FileName, Lines, False);
end;

function ModuleTarget(const ModuleName: string): string;
begin
  Result := AddBackslash(SelectedDipTrace) + 'Plugins\' + ModuleName + '\DipTraceMCP';
end;

procedure RemovePluginTargets;
var
  Target: string;
begin
  if SelectedDipTrace = '' then Exit;
  Target := ModuleTarget('Pcb');
  DelTree(Target, True, True, True, False);
  Target := ModuleTarget('Schematic');
  DelTree(Target, True, True, True, False);
  Target := ModuleTarget('CompEdit');
  DelTree(Target, True, True, True, False);
  Target := ModuleTarget('PattEdit');
  DelTree(Target, True, True, True, False);
end;

procedure InstallModule(const ModuleName, SettingsName: string);
var
  Target, BridgeSource, SettingsSource, BridgeDest, SettingsDest: string;
begin
  Target := ModuleTarget(ModuleName);
  if not ForceDirectories(Target) then
    RaiseException('Unable to create DipTrace plug-in directory: ' + Target);
  BridgeSource := ExpandConstant('{app}\payload\diptrace_mcp_bridge.exe');
  SettingsSource := ExpandConstant('{app}\payload\settings\' + SettingsName);
  BridgeDest := AddBackslash(Target) + 'diptrace_mcp_bridge.exe';
  SettingsDest := AddBackslash(Target) + 'settings.xml';
  if not FileCopy(BridgeSource, BridgeDest, False) then
    RaiseException('Unable to copy the DipTrace MCP bridge to ' + Target);
  if not FileCopy(SettingsSource, SettingsDest, False) then
    RaiseException('Unable to copy DipTrace MCP settings to ' + Target);
  if CompareText(GetSHA256OfFile(BridgeSource), GetSHA256OfFile(BridgeDest)) <> 0 then
    RaiseException('Bridge SHA-256 verification failed at ' + Target);
  if CompareText(GetSHA256OfFile(SettingsSource), GetSHA256OfFile(SettingsDest)) <> 0 then
    RaiseException('Settings SHA-256 verification failed at ' + Target);
end;

procedure InstallPluginPayload;
begin
  if not IsDipTraceLayout(SelectedDipTrace) then
    RaiseException('Selected directory is not a recognized DipTrace installation.');
  try
    InstallModule('Pcb', 'pcb.settings.xml');
    InstallModule('Schematic', 'schematic.settings.xml');
    InstallModule('CompEdit', 'component.settings.xml');
    InstallModule('PattEdit', 'pattern.settings.xml');
    SaveUtf8Line(ExpandConstant('{app}\diptrace-root.txt'), SelectedDipTrace);
    PluginInstalled := True;
  except
    RemovePluginTargets;
    RaiseException('DipTrace MCP plug-in installation failed; owned plug-in directories were rolled back.');
  end;
end;

procedure InitializeWizard;
var
  Root: string;
begin
  DipTracePage := CreateInputOptionPage(
    wpSelectDir,
    'DipTrace installation',
    'Choose the DipTrace installation to integrate',
    'This administrator-only installer writes only DipTrace MCP plug-in folders.',
    True,
    True
  );
  AddDipTraceCandidate(ExpandConstant('{commonpf}\DipTrace5'), 'Program Files');
  AddDipTraceCandidate(ExpandConstant('{commonpf}\DipTrace'), 'Program Files');
  AddDipTraceCandidate(ExpandConstant('{commonpf32}\DipTrace5'), 'Program Files (x86)');
  AddDipTraceCandidate(ExpandConstant('{commonpf32}\DipTrace'), 'Program Files (x86)');
  AddRegistryDipTraceCandidates(HKLM);
  AddRegistryDipTraceCandidates(HKCU);
  DipTracePage.Add('Browse for another validated DipTrace installation');
  DipTracePage.SelectedValueIndex := 0;

  DipTraceBrowsePage := CreateInputDirPage(
    DipTracePage.ID,
    'Browse for DipTrace',
    'Select the DipTrace root',
    'The directory must contain a known DipTrace module executable or Plugins directory.',
    False,
    ''
  );
  DipTraceBrowsePage.Add('DipTrace root:');
  Root := ParameterValue('DIPTRACE', '');
  if Root <> '' then begin
    SelectedDipTrace := ExpandFileName(Root);
    DipTraceBrowsePage.Values[0] := SelectedDipTrace;
    DipTracePage.SelectedValueIndex := GetArrayLength(DetectedDipTrace);
  end;
end;

function ShouldSkipPage(PageID: Integer): Boolean;
begin
  Result := False;
  if PageID = DipTraceBrowsePage.ID then
    Result := (DipTracePage.SelectedValueIndex < GetArrayLength(DetectedDipTrace));
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
    else
      SelectedDipTrace := ExpandFileName(DipTraceBrowsePage.Values[0]);
  end;
  if CurPageID = DipTraceBrowsePage.ID then begin
    SelectedDipTrace := ExpandFileName(DipTraceBrowsePage.Values[0]);
    if not IsDipTraceLayout(SelectedDipTrace) then begin
      MsgBox('The selected directory is not a recognized DipTrace installation.', mbError, MB_OK);
      Result := False;
    end;
  end;
end;

function PrepareToInstall(var NeedsRestart: Boolean): string;
var
  Root: string;
begin
  Result := '';
  NeedsRestart := False;
  Root := ParameterValue('DIPTRACE', '');
  if Root <> '' then
    SelectedDipTrace := ExpandFileName(Root);
  if (SelectedDipTrace = '') or not IsDipTraceLayout(SelectedDipTrace) then
    Result := 'Select a validated DipTrace installation. The plug-in installer does not install the MCP server or modify MCP client profiles.';
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if (CurStep = ssPostInstall) and not PluginInstalled then
    InstallPluginPayload;
end;

function LoadInstalledDipTraceRoot: string;
var
  Lines: TArrayOfString;
begin
  Result := '';
  if LoadStringsFromFile(ExpandConstant('{app}\diptrace-root.txt'), Lines) and
     (GetArrayLength(Lines) > 0) then
    Result := Trim(Lines[0]);
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if CurUninstallStep <> usUninstall then Exit;
  SelectedDipTrace := LoadInstalledDipTraceRoot;
  RemovePluginTargets;
end;
#else
const
  ClientCodex = 0;
  ClientClaude = 1;
  ClientBoth = 2;
  ClientNone = 3;

var
  WorkspacePage: TInputDirWizardPage;
  StatePage: TInputDirWizardPage;
  ClientPage: TInputOptionWizardPage;
  RemoveClientCheck: TNewCheckBox;
  RemoveStateCheck: TNewCheckBox;
  InstallLogPath: string;
  InstallationFinalized: Boolean;
  ResolvedStateDir: string;
  ResolvedWorkspaceDir: string;

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

function ParameterValue(const Name, DefaultValue: string): string;
var
  I: Integer;
  Argument, Prefix: string;
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
  if not SaveStringToFile(
    InstallLogPath,
    GetDateTimeString('yyyy-mm-dd hh:nn:ss', '-', ':') + ' ' + Line + #13#10,
    True
  ) then
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

function RunPowerShell(const Parameters: string; var ResultCode: Integer): Boolean;
var
  PowerShell: string;
begin
  PowerShell := ExpandConstant('{sys}\WindowsPowerShell\v1.0\powershell.exe');
  Result := Exec(PowerShell, Parameters, '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
end;

function RunServerHelp: Boolean;
var
  ResultCode: Integer;
begin
  Result := Exec(
    ExpandConstant('{app}\app\diptrace_mcp_server.exe'),
    '--help',
    '',
    SW_HIDE,
    ewWaitUntilTerminated,
    ResultCode
  ) and (ResultCode = 0);
end;

function CheckServerProcess: Boolean;
var
  ResultCode: Integer;
begin
  Result := RunPowerShell(
    '-NoProfile -NonInteractive -Command "if (Get-Process -Name diptrace_mcp_server -ErrorAction SilentlyContinue) { exit 1 } else { exit 0 }"',
    ResultCode
  ) and (ResultCode = 0);
end;

procedure CreateInstallationManifest;
var
  Parameters: string;
  ResultCode: Integer;
begin
  Parameters :=
    '-NoProfile -NonInteractive -ExecutionPolicy Bypass -File "' +
    ExpandConstant('{app}\tools\write_installation_manifest.ps1') +
    '" -ManifestPath "' + ExpandConstant('{app}\installation-manifest.json') +
    '" -AppRoot "' + ExpandConstant('{app}') +
    '" -Version "' + ExpandConstant('{#AppVersion}') +
    '" -StateDir "' + SelectedStateDir + '"';
  if not RunPowerShell(Parameters, ResultCode) or (ResultCode <> 0) then
    RaiseException('Unable to create installation-manifest.json');
  SaveUtf8Line(ExpandConstant('{app}\state-dir.txt'), SelectedStateDir);
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
  Parameters :=
    '--client ' + SelectedClientName +
    ' --workspace "' + SelectedWorkspaceDir +
    '" --state-dir "' + SelectedStateDir +
    '" --server "' + ExpandConstant('{app}\app\diptrace_mcp_server.exe') +
    '" --json';
  if not Exec(
    ExpandConstant('{app}\tools\diptrace_mcp_configure\diptrace_mcp_configure.exe'),
    Parameters,
    '',
    SW_HIDE,
    ewWaitUntilTerminated,
    ResultCode
  ) or (ResultCode <> 0) then
    RaiseException(
      'MCP client configuration failed closed. The original client configuration was preserved.'
    );
  AppendInstallLog('MCP client configuration completed or deferred with a manual command.');
end;

procedure FinalizeInstallation;
var
  StateDir, InstallStamp: string;
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
  AppendInstallLog('Per-user installation started. No secrets or client-config contents are logged.');
  if not RunServerHelp then
    RaiseException('Standalone server verification failed: diptrace_mcp_server.exe --help');
  AppendInstallLog('Standalone server --help smoke passed.');
  ConfigureMcpClient;
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if (CurStep = ssPostInstall) or (CurStep = ssDone) then
    FinalizeInstallation;
end;

function PrepareToInstall(var NeedsRestart: Boolean): string;
begin
  Result := '';
  NeedsRestart := False;
  if not CheckServerProcess then
    Result := 'Close diptrace_mcp_server.exe and retry. An active server/session is not terminated automatically.';
end;

function NextButtonClick(CurPageID: Integer): Boolean;
begin
  Result := True;
  if CurPageID = WorkspacePage.ID then begin
    ResolvedWorkspaceDir := Trim(WorkspacePage.Values[0]);
    if WorkspacePage.Values[0] = '' then begin
      MsgBox('Choose a DipTrace workspace directory.', mbError, MB_OK);
      Result := False;
    end else if not DirExists(WorkspacePage.Values[0]) and
                not ForceDirectories(WorkspacePage.Values[0]) then begin
      MsgBox('The workspace directory could not be created.', mbError, MB_OK);
      Result := False;
    end;
  end;
  if CurPageID = StatePage.ID then begin
    ResolvedStateDir := Trim(StatePage.Values[0]);
    if IsPathUnder(StatePage.Values[0], ExpandConstant('{app}')) then begin
      MsgBox('State must remain outside the installed application.', mbError, MB_OK);
      Result := False;
    end else if not ForceDirectories(StatePage.Values[0]) then begin
      MsgBox('The state directory could not be created.', mbError, MB_OK);
      Result := False;
    end;
  end;
end;

procedure InitializeWizard;
var
  ClientParam: string;
begin
  WorkspacePage := CreateInputDirPage(
    wpSelectComponents,
    'Project workspace',
    'Choose DipTrace project workspace',
    'The server will be restricted to this directory unless additional roots are configured later.',
    False,
    ''
  );
  WorkspacePage.Add('Workspace:');
  ResolvedWorkspaceDir := ParameterValue(
    'WORKSPACE',
    ExpandConstant('{userdocs}\DipTrace')
  );
  WorkspacePage.Values[0] := ResolvedWorkspaceDir;

  StatePage := CreateInputDirPage(
    WorkspacePage.ID,
    'Local writable state',
    'Choose local MCP state directory',
    'Runtime state and logs are kept outside the installed application.',
    False,
    ''
  );
  StatePage.Add('State directory:');
  ResolvedStateDir := ParameterValue(
    'STATEDIR',
    ExpandConstant('{localappdata}\DipTraceMCP')
  );
  StatePage.Values[0] := ResolvedStateDir;

  ClientPage := CreateInputOptionPage(
    StatePage.ID,
    'MCP client',
    'Choose client configuration',
    'Existing entries are updated idempotently and other servers are preserved.',
    True,
    True
  );
  ClientPage.Add('Configure Codex');
  ClientPage.Add('Configure Claude Desktop');
  ClientPage.Add('Configure both');
  ClientPage.Add('Skip client configuration');
  ClientPage.SelectedValueIndex := ClientNone;
  ClientParam := Lowercase(ParameterValue('CLIENT', ''));
  if ClientParam = 'codex' then ClientPage.SelectedValueIndex := ClientCodex
  else if ClientParam = 'claude' then ClientPage.SelectedValueIndex := ClientClaude
  else if ClientParam = 'both' then ClientPage.SelectedValueIndex := ClientBoth;
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
  RemoveStateCheck.Caption :=
    'Remove local DipTrace MCP state and logs (projects are never removed)';
  RemoveStateCheck.Checked := HasCommandLineParam('/REMOVE_STATE');
end;

function UninstallStateDir: string;
var
  Lines: TArrayOfString;
begin
  Result := '';
  if LoadStringsFromFile(
    ExpandConstant('{app}\state-dir.txt'),
    Lines
  ) and (GetArrayLength(Lines) > 0) then
    Result := Lines[0];
end;

function RemoveClientConfiguration: Boolean;
var
  ResultCode: Integer;
  StateDir, Parameters: string;
begin
  Result := True;
  StateDir := UninstallStateDir;
  Parameters :=
    '--client both --unconfigure --state-dir "' + StateDir + '" --json';
  if not Exec(
    ExpandConstant('{app}\tools\diptrace_mcp_configure\diptrace_mcp_configure.exe'),
    Parameters,
    '',
    SW_HIDE,
    ewWaitUntilTerminated,
    ResultCode
  ) or (ResultCode <> 0) then begin
    MsgBox(
      'Client configuration was not changed because it was invalid or unavailable. ' +
      'The original files remain for manual recovery.',
      mbError,
      MB_OK
    );
    Result := False;
  end;
end;

function RemoveLocalState: Boolean;
var
  ResultCode: Integer;
  StateDir, Parameters: string;
begin
  Result := True;
  StateDir := UninstallStateDir;
  if StateDir = '' then Exit;
  Log('DipTrace MCP uninstall: removing owned local state');
  Parameters :=
    '-NoProfile -NonInteractive -ExecutionPolicy Bypass -File "' +
    ExpandConstant('{app}\tools\remove_owned_state.ps1') +
    '" -ManifestPath "' + ExpandConstant('{app}\installation-manifest.json') + '"';
  if not RunPowerShell(Parameters, ResultCode) or (ResultCode <> 0) then begin
    Log('DipTrace MCP uninstall: owned state removal failed with code ' + IntToStr(ResultCode));
    if not UninstallSilent then
      MsgBox(
        'Owned local state was not removed; projects and unknown files were preserved.',
        mbError,
        MB_OK
      );
    Result := False;
  end else
    Log('DipTrace MCP uninstall: owned local state removal completed');
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if CurUninstallStep <> usUninstall then Exit;
  if RemoveClientCheck.Checked and not RemoveClientConfiguration then Abort;
  if RemoveStateCheck.Checked and not RemoveLocalState then Abort;
end;
#endif

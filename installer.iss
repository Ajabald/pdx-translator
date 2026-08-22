; The PDX Translator installer (Inno Setup 6).
;
;   iscc /DAppVersion=0.1.0 installer.iss
;
; The version comes from the command line rather than being written here: it is
; set already in `pdxloc/__init__.py`, and a third copy would part ways with the
; first two. Built in CI after PyInstaller — see .github/workflows/ci.yml.

#ifndef AppVersion
  #error Pass the version: iscc /DAppVersion=0.1.0 installer.iss
#endif

#define AppName "PDX Translator"
#define AppExe "pdx-translator.exe"
#define AppUrl "https://github.com/Ajabald/pdx-translator"

[Setup]
; The identifier does not change between releases — an update finds the previous
; installation by it and replaces it instead of putting a second copy alongside.
AppId={{D6243354-FC2A-4B41-ABE1-7DC4DDD9D4A0}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher=Ajabald
AppPublisherURL={#AppUrl}
AppSupportURL={#AppUrl}/issues
AppUpdatesURL={#AppUrl}/releases
VersionInfoVersion={#AppVersion}

; --- THE MAIN DECISION: install for the user, not into Program Files -------
;
; The application writes next to itself: `Bdd`, `Projects`, `backups`,
; `qa_rules.json` and `pdx-translator.log` (see `settings.app_root`). An
; ordinary user cannot write into Program Files, and all of that would break
; silently — or demand administrator rights at every start.
;
; `PrivilegesRequired=lowest` installs into `%LOCALAPPDATA%\Programs`, where
; writing is allowed, and the installation asks for no rights at all. For those
; who want otherwise, `PrivilegesRequiredOverridesAllowed=dialog` offers the
; choice of installing for everyone.
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes

OutputDir=.
OutputBaseFilename=pdx-translator-setup-{#AppVersion}
SetupIconFile=pdx-translator.ico
UninstallDisplayIcon={app}\{#AppExe}
LicenseFile=LICENSE
WizardStyle=modern
Compression=lzma2/max
SolidCompression=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "en"; MessagesFile: "compiler:Default.isl"
Name: "ru"; MessagesFile: "compiler:Languages\Russian.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; \
    GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
; The whole tree of the PyInstaller onedir build.
Source: "dist\pdx-translator\*"; DestDir: "{app}"; \
    Flags: ignoreversion recursesubdirs createallsubdirs
; The licences are not listed here: PyInstaller already puts `LICENSE`,
; `LICENSE.LGPL-3.0.txt` and `THIRD-PARTY.md` into the build (see the `datas` of
; `pdx-translator.spec`), so the line above carries them. One source for both the
; installer and the portable archive — listing them twice is how the archive came
; to have none of them while the installer had two of the three.

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExe}"; Description: "{cm:LaunchProgram,{#AppName}}"; \
    Flags: nowait postinstall skipifsilent

; Uninstalling touches only what the installer put there. The folders `Bdd`,
; `Projects` and `backups` stay: that is the translator's work — memory
; databases, project files and backups of translations. Sweeping them away with
; the program would erase months of somebody's labour, and there would be
; nowhere to get it back from.
;
; But keeping quiet about it will not do: a folder left behind looks like an
; unfinished uninstall. So at the end we say what exactly was kept, and where.

[CustomMessages]
en.DataKept=Your work has been kept and not deleted:
en.DataKeptHint=Delete the folder by hand if you no longer need any of it.
ru.DataKept=Ваша работа сохранена и не удалена:
ru.DataKeptHint=Удалите папку вручную, если ничего из этого больше не нужно.

[Code]
function KeptFolders(): String;
var
  Names: array[0..2] of String;
  I: Integer;
begin
  Names[0] := 'Bdd';
  Names[1] := 'Projects';
  Names[2] := 'backups';
  Result := '';
  for I := 0 to 2 do
    if DirExists(ExpandConstant('{app}\') + Names[I]) then
      Result := Result + #13#10 + '    ' + Names[I];
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  Kept: String;
begin
  // Only after the uninstall and only in the ordinary mode: in the silent one
  // (/VERYSILENT) there is nobody to close the window, and the uninstall would
  // hang forever.
  if (CurUninstallStep = usPostUninstall) and (not UninstallSilent) then
  begin
    Kept := KeptFolders();
    if Kept <> '' then
      MsgBox(CustomMessage('DataKept') + #13#10 + ExpandConstant('{app}')
             + Kept + #13#10#13#10 + CustomMessage('DataKeptHint'),
             mbInformation, MB_OK);
  end;
end;

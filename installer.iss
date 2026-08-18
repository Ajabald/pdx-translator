; Установщик PDX Translator (Inno Setup 6).
;
;   iscc /DAppVersion=0.1.0 installer.iss
;
; Версия приходит из командной строки, а не пишется здесь: она уже задана в
; `pdxloc/__init__.py`, и третья копия разъехалась бы с первыми двумя.
; Собирается в CI после PyInstaller — см. .github/workflows/ci.yml.

#ifndef AppVersion
  #error Передайте версию: iscc /DAppVersion=0.1.0 installer.iss
#endif

#define AppName "PDX Translator"
#define AppExe "pdx-translator.exe"
#define AppUrl "https://github.com/Ajabald/pdx-translator"

[Setup]
; Идентификатор не меняется между выпусками — по нему обновление находит
; предыдущую установку и заменяет её, а не ставит вторую копию рядом.
AppId={{D6243354-FC2A-4B41-ABE1-7DC4DDD9D4A0}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher=Ajabald
AppPublisherURL={#AppUrl}
AppSupportURL={#AppUrl}/issues
AppUpdatesURL={#AppUrl}/releases
VersionInfoVersion={#AppVersion}

; --- ГЛАВНОЕ РЕШЕНИЕ: установка для пользователя, а не в Program Files ------
;
; Приложение пишет рядом с собой: `Bdd`, `Projects`, `backups`,
; `qa_rules.json` и `pdx-translator.log` (см. `settings.app_root`). В
; Program Files обычному пользователю писать нельзя, и всё это молча
; сломалось бы — либо потребовало прав администратора на каждый запуск.
;
; `PrivilegesRequired=lowest` ставит в `%LOCALAPPDATA%\Programs`, куда писать
; можно, и установка проходит без запроса прав вовсе. Кому нужно иначе —
; `PrivilegesRequiredOverridesAllowed=dialog` даёт выбрать установку для всех.
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
; Всё дерево onedir-сборки PyInstaller целиком.
Source: "dist\pdx-translator\*"; DestDir: "{app}"; \
    Flags: ignoreversion recursesubdirs createallsubdirs
; Лицензии кладём рядом с приложением, а не только в мастер: LGPL требует
; сообщить получателю про Qt, а мастер закрывают и забывают.
Source: "LICENSE"; DestDir: "{app}"; Flags: ignoreversion
Source: "THIRD-PARTY.md"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExe}"; Description: "{cm:LaunchProgram,{#AppName}}"; \
    Flags: nowait postinstall skipifsilent

; Удаление трогает только то, что положил установщик. Папки `Bdd`, `Projects`
; и `backups` остаются: это работа переводчика — базы памяти, файлы проектов и
; резервные копии переводов. Снести их вместе с программой значило бы стереть
; месяцы чужого труда, и вернуть его будет неоткуда.

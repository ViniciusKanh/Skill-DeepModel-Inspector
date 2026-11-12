; Instalador Windows do DeepModel Inspector (Inno Setup 6).
; Instala por usuario (sem administrador) em %LOCALAPPDATA%\Programs\DeepModel Inspector.
; Os dados do usuario ficam em %LOCALAPPDATA%\DeepModelInspector e NAO sao removidos na desinstalacao.
; Gerado por scripts/Build-Installer.ps1 (ou pelo workflow .github/workflows/release.yml).

#ifndef AppVersion
  #define AppVersion "1.0.0"
#endif
#define AppName "DeepModel Inspector"
#define SourceDir "..\build\pyinstaller\dist\DeepModelInspector"

[Setup]
AppId={{6C1E5D0B-6F0E-4B57-9F43-2D7A0B9D1E11}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=Vinicius de Souza Santos
AppPublisherURL=https://github.com/ViniciusKanh
DefaultDirName={localappdata}\Programs\{#AppName}
DefaultGroupName={#AppName}
PrivilegesRequired=lowest
DisableProgramGroupPage=yes
OutputDir=..\build\release
OutputBaseFilename=DeepModelInspector-Setup-{#AppVersion}
SetupIconFile=icon.ico
UninstallDisplayIcon={app}\DeepModelInspector.exe
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\DeepModelInspector.exe"
Name: "{group}\Uninstall {#AppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\DeepModelInspector.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\DeepModelInspector.exe"; Description: "Launch {#AppName}"; Flags: nowait postinstall skipifsilent

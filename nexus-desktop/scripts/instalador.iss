; Instalador do Nexus Wolf's (Inno Setup 6). Compilado por build-desktop.ps1 com:
;   ISCC /DAppVersion=0.3.0 /DBuildId=AAAAMMDD-HHMMSS /DSourceDir=<pasta com NexusWolfs.exe> /DOutputDir=<release>
;        /DProjectData=<pasta de dados portatil> /DChannel=<pasta release> scripts\instalador.iss
; Instala por usuario, sem administrador, em %LOCALAPPDATA%\Programs\Nexus Wolfs. A biblioteca fica em
; %LOCALAPPDATA%\NexusWolfs e e importada da instalacao portatil na primeira abertura (ver instalado.json).
#ifndef AppVersion
  #define AppVersion "0.3.0"
#endif
#ifndef BuildId
  #define BuildId "dev"
#endif
#ifndef ProjectData
  #define ProjectData ""
#endif
#ifndef Channel
  #define Channel ""
#endif

[Setup]
AppId={{7D2C9B6E-3A41-4F0E-9C4B-2F0E6D5A1B37}
AppName=Nexus Wolf's
AppVersion={#AppVersion}
AppVerName=Nexus Wolf's {#AppVersion} ({#BuildId})
AppPublisher=Projeto-KibaGames
DefaultDirName={localappdata}\Programs\Nexus Wolfs
DefaultGroupName=Nexus Wolf's
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir={#OutputDir}
OutputBaseFilename=NexusWolfs-Setup-{#AppVersion}-{#BuildId}
SetupIconFile=..\src-tauri\icons\icon.ico
UninstallDisplayIcon={app}\NexusWolfs.exe
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
RestartApplications=no
ArchitecturesInstallIn64BitMode=x64compatible
ArchitecturesAllowed=x64compatible

[Languages]
Name: "brazilianportuguese"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"

[Tasks]
Name: "desktopicon"; Description: "Criar um atalho na área de trabalho"; GroupDescription: "Atalhos:"

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion

[Icons]
Name: "{group}\Nexus Wolf's"; Filename: "{app}\NexusWolfs.exe"
Name: "{group}\Desinstalar Nexus Wolf's"; Filename: "{uninstallexe}"
Name: "{autodesktop}\Nexus Wolf's"; Filename: "{app}\NexusWolfs.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\NexusWolfs.exe"; Description: "Abrir o Nexus Wolf's"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{app}"
Type: filesandordirs; Name: "{app}.anterior"
Type: filesandordirs; Name: "{app}.novo"

[Code]
function EscapeJson(const S: string): string;
begin
  Result := S;
  StringChangeEx(Result, '\', '\\', True);
  StringChangeEx(Result, '"', '\"', True);
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  Json: string;
begin
  if CurStep = ssPostInstall then
  begin
    // Marcador lido por NexusWolfs.exe: dados em %LOCALAPPDATA%\NexusWolfs, origem da importacao e canal de atualizacao.
    Json := '{' + #13#10 +
      '  "instalado": true,' + #13#10 +
      '  "build": "' + EscapeJson('{#BuildId}') + '",' + #13#10 +
      '  "dados_anteriores": "' + EscapeJson('{#ProjectData}') + '",' + #13#10 +
      '  "canal": "' + EscapeJson('{#Channel}') + '"' + #13#10 +
      '}' + #13#10;
    SaveStringToFile(ExpandConstant('{app}\instalado.json'), Json, False);
  end;
end;

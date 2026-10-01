; Script Inno Setup 6 — produit dist\BrikIA-Setup.exe
; Compilation : iscc /DAppVersion=1.0.0 installer\BrikIA.iss   (après build_windows.py)

#ifndef AppVersion
  #define AppVersion "1.0.0"
#endif
#define Port "8000"

[Setup]
AppId={{6F1B3C52-8E0A-4D55-9B61-2C7A4E5D1B90}
AppName=BrikIA
AppVersion={#AppVersion}
AppPublisher=BrikIA
DefaultDirName={autopf}\BrikIA
DefaultGroupName=BrikIA
DisableProgramGroupPage=yes
OutputDir=..\dist
OutputBaseFilename=BrikIA-Setup
SetupIconFile=..\build\BrikIA\brikia.ico
UninstallDisplayIcon={app}\brikia.ico
Compression=lzma2/normal
SolidCompression=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=admin
WizardStyle=modern
CloseApplications=no

[Languages]
Name: "french"; MessagesFile: "compiler:Languages\French.isl"

[Tasks]
Name: "desktopicon"; Description: "Créer une icône sur le Bureau"; GroupDescription: "Raccourcis :"
Name: "lan"; Description: "Autoriser les autres PC du réseau local à ouvrir BrikIA (règle de pare-feu Windows, port {#Port})"; GroupDescription: "Accès réseau :"; Flags: unchecked

[Dirs]
; Données (base, plans, sauvegardes, .env) : hors du dossier du programme, conservées à la désinstallation.
Name: "{commonappdata}\BrikIA"; Permissions: users-modify

[Files]
Source: "..\build\BrikIA\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{group}\BrikIA"; Filename: "{app}\python\python.exe"; Parameters: """{app}\app\launcher.py"""; WorkingDir: "{commonappdata}\BrikIA"; IconFilename: "{app}\brikia.ico"; Flags: runminimized
Name: "{group}\Sauvegarder les données BrikIA"; Filename: "{app}\python\python.exe"; Parameters: """{app}\app\launcher.py"" cli --pause backup"; WorkingDir: "{commonappdata}\BrikIA"; IconFilename: "{app}\brikia.ico"
Name: "{group}\Dossier des données BrikIA"; Filename: "{commonappdata}\BrikIA"
Name: "{group}\Désinstaller BrikIA"; Filename: "{uninstallexe}"
Name: "{autodesktop}\BrikIA"; Filename: "{app}\python\python.exe"; Parameters: """{app}\app\launcher.py"""; WorkingDir: "{commonappdata}\BrikIA"; IconFilename: "{app}\brikia.ico"; Tasks: desktopicon; Flags: runminimized

[Run]
Filename: "netsh"; Parameters: "advfirewall firewall add rule name=""BrikIA"" dir=in action=allow protocol=TCP localport={#Port} profile=private,domain"; Flags: runhidden; Tasks: lan
Filename: "{app}\python\python.exe"; Parameters: """{app}\app\launcher.py"""; WorkingDir: "{commonappdata}\BrikIA"; Description: "Lancer BrikIA maintenant"; Flags: postinstall nowait skipifsilent runminimized

[UninstallRun]
Filename: "netsh"; Parameters: "advfirewall firewall delete rule name=""BrikIA"""; Flags: runhidden; RunOnceId: "DelFirewall"

[Code]
procedure CurStepChanged(CurStep: TSetupStep);
var
  EnvFile, Content: String;
begin
  if CurStep = ssPostInstall then
  begin
    // Fichier de configuration créé une seule fois : une mise à jour ne l'écrase jamais.
    EnvFile := ExpandConstant('{commonappdata}\BrikIA\.env');
    if not FileExists(EnvFile) then
    begin
      Content := '# Configuration BrikIA (voir docs/deploiement.md). Fichier ASCII : redemarrez BrikIA apres modification.' + #13#10;
      if WizardIsTaskSelected('lan') then
        Content := Content + 'BRIKIA_HOST=0.0.0.0' + #13#10
      else
        Content := Content + 'BRIKIA_HOST=127.0.0.1' + #13#10;
      Content := Content + 'BRIKIA_PORT={#Port}' + #13#10;
      SaveStringToFile(EnvFile, Content, False);
    end;
  end;
end;

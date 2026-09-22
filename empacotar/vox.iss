; Instalador do VOX (Inno Setup). Empacota o app congelado (PyInstaller) +
; modelos embutidos + ffmpeg. Instala offline, sem Python, sem token.
; Compilar:  "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" vox.iss

#define MyAppName "VOX"
#define MyAppVersion "1.1"
#define MyAppPublisher "VOX"
#define MyAppExe "VOX.exe"

[Setup]
AppName={#MyAppName}
AppVerName={#MyAppName} {#MyAppVersion}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\VOX
DefaultGroupName=VOX
DisableProgramGroupPage=yes
OutputDir=saida_instalador
OutputBaseFilename=Instalador VOX {#MyAppVersion}
SetupIconFile=vox.ico
UninstallDisplayIcon={app}\vox.ico
Compression=lzma2/fast
SolidCompression=no
; O pacote (app + modelos) passa de 4,2 GB, acima do limite de um .exe único.
; Disk spanning divide em fatias .bin (distribuir a pasta inteira; rodar o .exe).
DiskSpanning=yes
DiskSliceSize=2100000000
ArchitecturesInstallIn64BitMode=x64compatible
ArchitecturesAllowed=x64compatible
; Sem exigir admin: instala na pasta do usuário (bom p/ máquinas corporativas
; sem privilégio). Se rodado como admin, permite instalar para todos.
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
WizardStyle=modern
DisableWelcomePage=no

[Languages]
Name: "pt"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"

[Tasks]
Name: "desktopicon"; Description: "Criar atalho na Área de Trabalho"; GroupDescription: "Atalhos adicionais:"

[Files]
; App congelado (PyInstaller onedir)
Source: "dist\VOX\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion
; Modelos embutidos (ficam ao lado do executável → modo offline)
Source: "modelos\*"; DestDir: "{app}\modelos"; Flags: recursesubdirs createallsubdirs ignoreversion
; ffmpeg embutido
Source: "ffmpeg\*"; DestDir: "{app}\ffmpeg"; Flags: ignoreversion
; Ícone
Source: "vox.ico"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\VOX"; Filename: "{app}\{#MyAppExe}"; IconFilename: "{app}\vox.ico"
Name: "{group}\Desinstalar VOX"; Filename: "{uninstallexe}"
Name: "{autodesktop}\VOX"; Filename: "{app}\{#MyAppExe}"; IconFilename: "{app}\vox.ico"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExe}"; Description: "Abrir o VOX agora"; Flags: nowait postinstall skipifsilent

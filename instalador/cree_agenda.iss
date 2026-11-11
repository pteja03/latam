; Instalador de CREE Agenda (Inno Setup 6). Se compila con instalador\construir.ps1.
; Instala por usuario, sin permisos de administrador. Los datos de la clinica viven en
; %LOCALAPPDATA%\CREE Agenda y NO se borran al desinstalar ni al actualizar.

#define Version GetEnv("CREE_VERSION")
#if Version == ""
  #define Version "0.0.0"
#endif

[Setup]
AppId={{A650423A-892B-4394-853D-EB705FA043B7}
AppName=CREE Agenda
AppVersion={#Version}
AppPublisher=Clinica CREE
DefaultDirName={autopf}\CREE Agenda
DefaultGroupName=CREE Agenda
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\dist
OutputBaseFilename=CREE-Agenda-Instalador-{#Version}
SetupIconFile=icono.ico
UninstallDisplayIcon={app}\CreeAgenda.exe
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes

[Languages]
Name: "es"; MessagesFile: "compiler:Languages\Spanish.isl"

[Tasks]
Name: "inicio"; Description: "Iniciar los servicios de la agenda al encender la PC (necesario para atender WhatsApp)"
Name: "escritorio"; Description: "Crear un acceso directo en el escritorio"

[Files]
Source: "..\dist\CreeAgenda\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion
Source: "..\build\postgres\*"; DestDir: "{app}\postgres"; Flags: recursesubdirs createallsubdirs ignoreversion
Source: "..\build\cloudflared.exe"; DestDir: "{app}"; Flags: ignoreversion skipifsourcedoesntexist

[Icons]
Name: "{group}\CREE Agenda"; Filename: "{app}\CreeAgenda.exe"
Name: "{autodesktop}\CREE Agenda"; Filename: "{app}\CreeAgenda.exe"; Tasks: escritorio
Name: "{userstartup}\CREE Agenda (servicios)"; Filename: "{app}\CreeAgenda.exe"; Parameters: "--servidor"; Tasks: inicio

[Run]
Filename: "{app}\CreeAgenda.exe"; Description: "Abrir CREE Agenda"; Flags: nowait postinstall skipifsilent

[UninstallRun]
Filename: "{app}\CreeAgenda.exe"; Parameters: "--detener"; Flags: runhidden waituntilterminated; RunOnceId: "DetenerServicios"

[Code]
// Al actualizar: detiene los servicios de la version anterior para poder reemplazar archivos.
function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  Codigo: Integer;
  Ejecutable: String;
begin
  Ejecutable := ExpandConstant('{app}\CreeAgenda.exe');
  if FileExists(Ejecutable) then
    Exec(Ejecutable, '--detener', '', SW_HIDE, ewWaitUntilTerminated, Codigo);
  Result := '';
end;

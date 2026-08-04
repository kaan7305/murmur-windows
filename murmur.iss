; Inno Setup script for Murmur.
;
; Build with build.bat, which runs PyInstaller first - this script packages
; dist\Murmur and will fail loudly if that folder is not there.
;
; Installs per-user, into LOCALAPPDATA, on purpose. Murmur has to send
; keystrokes into whatever window has focus, and a program running with
; administrator rights cannot send input to one that does not (nor the reverse),
; so installing to Program Files would buy nothing and cost a UAC prompt at
; install time. Per-user means no elevation, and an uninstall that leaves
; nothing behind in shared locations.

#define AppName        "Murmur"
#define AppVersion     "1.0.0"
#define AppPublisher   "Murmur"
#define AppExe         "Murmur.exe"

[Setup]
; Never change this GUID: it is how Windows recognises an upgrade of an
; existing installation rather than a second, parallel one.
AppId={{CDC7539A-5A67-4FB6-AC04-CF8B7E6648E2}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher={#AppPublisher}
VersionInfoVersion={#AppVersion}

DefaultDirName={localappdata}\Programs\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
DisableDirPage=auto
PrivilegesRequired=lowest

; Both of these turn a machine away at install time rather than let Murmur fail
; on it afterwards. 1809 is the floor for what Murmur freezes in - CPython 3.14
; and Qt 6 both stop there - and murmur.spec freezes windowless, so on anything
; older the process dies with no console and no window: nothing for the user to
; report but "it does nothing".
; x64os (spelled x64 before Inno 6.3) rather than x64compatible: the latter also
; matches ARM64 Windows, which would install happily and then run the whole
; transcription stack under x64 emulation, slowly enough to be useless. A
; refusal here is kinder than a first recording that never finishes.
MinVersion=10.0.17763
ArchitecturesAllowed=x64os
ArchitecturesInstallIn64BitMode=x64compatible

OutputDir=dist
OutputBaseFilename=Murmur-Setup-{#AppVersion}
SetupIconFile=murmur.ico
UninstallDisplayIcon={app}\{#AppExe}
WizardStyle=modern

; The payload is a few hundred megabytes of DLLs. Solid LZMA2 pays for itself
; several times over here; the extra minute at build time is spent once.
Compression=lzma2/max
SolidCompression=yes

; Murmur holds the microphone, a global hotkey and a named mutex. Installing
; over a running copy would leave locked files behind, so offer to close it.
CloseApplications=yes
CloseApplicationsFilter=*.exe
RestartApplications=no

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; \
    GroupDescription: "Shortcuts:"
Name: "startup"; Description: "Start Murmur when I sign in"; \
    GroupDescription: "Startup:"

[Files]
Source: "dist\Murmur\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs \
    createallsubdirs

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{group}\Uninstall {#AppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; \
    Tasks: desktopicon

[Registry]
; --hidden starts it straight to the tray, which is what someone asking for it
; at sign-in wants; without it every boot would open the window.
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; \
    ValueType: string; ValueName: "Murmur"; \
    ValueData: """{app}\{#AppExe}"" --hidden"; \
    Flags: uninsdeletevalue; Tasks: startup

; The entry above is only written when the task was ticked, and its
; uninsdeletevalue only counts for the same run. Someone who declined it and
; later turned the setting on inside Murmur (startup.py writes this very value)
; would be left, after an uninstall, with a Run entry aimed at an exe that is no
; longer there: a failed launch at every sign-in, forever. This second entry
; creates nothing (ValueType none writes no value, dontcreatekey stops it even
; creating the Run key) and exists only to have the value deleted at uninstall
; however it came to be there.
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; \
    ValueType: none; ValueName: "Murmur"; \
    Flags: dontcreatekey uninsdeletevalue

[UninstallDelete]
; Inno removes only the shortcuts it created itself, and a desktop icon can
; arrive another way - dragged out of the Start menu, or made by hand after the
; fact. Remove it unconditionally, so uninstalling never leaves an icon behind
; pointing at a folder that is no longer there.
Type: files; Name: "{autodesktop}\{#AppName}.lnk"

[Run]
Filename: "{app}\{#AppExe}"; Description: "Start Murmur"; \
    Flags: nowait postinstall skipifsilent

[Code]
{ Everything Murmur writes - the chosen model, the log, and the optional
  1.6 GB GPU pack - lives in LOCALAPPDATA\Murmur rather than beside the
  program. Uninstalling does not touch it by default, since a reinstall would
  otherwise mean downloading the GPU pack again; but leaving gigabytes behind
  silently is not acceptable either, so ask. }
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  DataDir: String;
begin
  if CurUninstallStep = usPostUninstall then
  begin
    DataDir := ExpandConstant('{localappdata}\Murmur');
    if DirExists(DataDir) then
      if MsgBox('Also remove Murmur''s settings and the downloaded GPU '
                + 'libraries?' + #13#10#13#10 + DataDir + #13#10#13#10
                + 'Choose No to keep them for a future reinstall. Speech '
                + 'models are stored separately and are not affected.',
                mbConfirmation, MB_YESNO) = IDYES then
        DelTree(DataDir, True, True, True);
  end;
end;

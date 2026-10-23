; Task알림 설치본 (사용자 단위 설치 - 관리자 권한 불필요)
;
; 먼저 standalone 빌드:  python -m nuitka TaskPin.py      -> build\TaskPin.dist\
; 그다음 설치본 빌드:    iscc installer\TaskPin.iss       -> dist\TaskPin-<버전>-setup.exe
;
; 버전은 빌드된 exe 의 제품 버전(TaskPin.py 의 --product-version)에서 읽는다.
; 사용자 데이터(%APPDATA%\TaskPin)는 제거할 때도 지우지 않는다.

#define AppName "Task알림"
#define AppExeName "Task알림.exe"
#define DistDir "..\build\TaskPin.dist"
#define AppVersion GetVersionNumbersString(AddBackslash(SourcePath) + DistDir + "\" + AppExeName)
#if AppVersion == ""
  #error "build\TaskPin.dist 에 exe 가 없습니다. 먼저 python -m nuitka TaskPin.py 를 실행하세요."
#endif
; 0.1.0.0 -> 0.1.0 (Semantic Versioning 표기)
#define AppSemVer Copy(AppVersion, 1, RPos(".", AppVersion) - 1)

[Setup]
; AppId 는 업그레이드/제거 식별자이므로 절대 바꾸지 않는다
AppId={{CE9E7FB7-A1C7-4587-B4F8-F0A289187EF7}
AppName={#AppName}
AppVersion={#AppSemVer}
AppVerName={#AppName} {#AppSemVer}
VersionInfoVersion={#AppVersion}
DefaultDirName={localappdata}\Programs\TaskPin
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
; 실행 중인 앱(os_win.create_app_mutex)이 있으면 종료하라고 안내한다
AppMutex=TaskPin
SetupIconFile=..\ico\taskpin.ico
UninstallDisplayIcon={app}\{#AppExeName}
UninstallDisplayName={#AppName}
OutputDir=..\dist
OutputBaseFilename=TaskPin-{#AppSemVer}-setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "korean"; MessagesFile: "compiler:Languages\Korean.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "{#DistDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExeName}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"; Tasks: desktopicon

[Registry]
; "윈도우 시작 시 실행"은 앱이 켜고 끈다. 제거할 때 그 값만 지운다 (설치 시에는 만들지 않음)
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: none; ValueName: "TaskPin"; Flags: uninsdeletevalue

[Run]
Filename: "{app}\{#AppExeName}"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent

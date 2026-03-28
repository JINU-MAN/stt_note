; STTNote Windows Installer — Inno Setup 6+
; build_windows.bat에서 자동 호출되거나 Inno Setup Compiler로 직접 컴파일 가능

#define AppName      "STTNote"
#define AppVersion   "1.0.0"
#define AppPublisher "STTNote"
#define AppExeName   "STTNote.exe"
#define DistDir      "..\dist"

[Setup]
AppId={{A1B2C3D4-E5F6-7890-ABCD-EF1234567890}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
OutputDir={#DistDir}
OutputBaseFilename=STTNote_Setup
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
; 설치 시 기존 버전 자동 언인스톨
CloseApplications=yes
UninstallDisplayIcon={app}\{#AppExeName}
; 최소 Windows 10
MinVersion=10.0

[Languages]
Name: "korean"; MessagesFile: "compiler:Languages\Korean.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "바탕화면에 바로가기 만들기"; GroupDescription: "추가 아이콘:"; Flags: unchecked

[Files]
; 세 실행 파일을 앱 폴더에 설치
Source: "{#DistDir}\STTNote.exe";    DestDir: "{app}"; Flags: ignoreversion
Source: "{#DistDir}\stt_script.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#DistDir}\llm_script.exe"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
; 시작 메뉴
Name: "{group}\{#AppName}";        Filename: "{app}\{#AppExeName}"
Name: "{group}\{#AppName} 제거";   Filename: "{uninstallexe}"
; 바탕화면 (선택)
Name: "{autodesktop}\{#AppName}";  Filename: "{app}\{#AppExeName}"; Tasks: desktopicon

[Run]
; 설치 완료 후 바로 실행 옵션
Filename: "{app}\{#AppExeName}"; Description: "{cm:LaunchProgram,{#AppName}}"; \
  Flags: nowait postinstall skipifsilent

[UninstallDelete]
; 앱 폴더 안에 남은 파일도 제거 (로그 등)
Type: filesandordirs; Name: "{app}"

[Code]
// 언인스톨 시 %APPDATA%\STTNote 폴더(설정 파일) 삭제 여부 확인
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  ConfigDir: String;
  MsgResult: Integer;
begin
  if CurUninstallStep = usPostUninstall then
  begin
    ConfigDir := ExpandConstant('{userappdata}\STTNote');
    if DirExists(ConfigDir) then
    begin
      MsgResult := MsgBox(
        '설정 파일과 로그를 삭제할까요?' + #13#10 +
        '(' + ConfigDir + ')' + #13#10#13#10 +
        '아니오를 선택하면 파일이 그대로 유지됩니다.',
        mbConfirmation, MB_YESNO
      );
      if MsgResult = IDYES then
        DelTree(ConfigDir, True, True, True);
    end;
  end;
end;

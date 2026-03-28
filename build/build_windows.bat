@echo off
setlocal

:: 프로젝트 루트로 이동 (이 배치 파일이 있는 폴더의 상위)
cd /d "%~dp0.."

echo ==========================================================
echo  STTNote Windows 빌드 스크립트
echo ==========================================================
echo.

:: Python / PyInstaller 확인
python --version >nul 2>&1 || (echo [오류] python 을 찾을 수 없습니다. & exit /b 1)
pyinstaller --version >nul 2>&1 || (echo [오류] pyinstaller 를 찾을 수 없습니다. pip install pyinstaller & exit /b 1)

:: 이전 빌드 결과 삭제
echo [1/4] 이전 빌드 정리...
if exist dist rmdir /s /q dist
if exist build\_pyi_cache rmdir /s /q build\_pyi_cache

:: stt_script.exe 빌드
echo [2/4] stt_script.exe 빌드 중...
pyinstaller --noconfirm build\stt_worker.spec || (echo [오류] stt_script 빌드 실패 & exit /b 1)

:: llm_script.exe 빌드
echo [3/4] llm_script.exe 빌드 중...
pyinstaller --noconfirm build\llm_worker.spec || (echo [오류] llm_script 빌드 실패 & exit /b 1)

:: STTNote.exe 빌드
echo [4/4] STTNote.exe 빌드 중...
pyinstaller --noconfirm build\main.spec || (echo [오류] STTNote 빌드 실패 & exit /b 1)

echo.
echo ==========================================================
echo  빌드 완료! dist\ 폴더를 확인하세요.
echo    dist\STTNote.exe
echo    dist\stt_script.exe
echo    dist\llm_script.exe
echo ==========================================================
echo.

:: Inno Setup 경로 탐색 (PATH 또는 기본 설치 경로)
set ISCC=
where iscc >nul 2>&1 && set ISCC=iscc
if not defined ISCC (
    if exist "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
)
if not defined ISCC (
    if exist "%ProgramFiles%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles%\Inno Setup 6\ISCC.exe"
)

if defined ISCC (
    echo Inno Setup 발견 - installer.exe 생성 중...
    "%ISCC%" build\installer.iss || (echo [경고] installer.iss 컴파일 실패 & goto :end)
    echo installer.exe 생성 완료 - dist\STTNote_Setup.exe
) else (
    echo [참고] Inno Setup 을 찾을 수 없어 installer.exe 는 생략됩니다.
    echo        https://jrsoftware.org/isinfo.php 에서 설치하세요.
)

:end
endlocal

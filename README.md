# STTNote

음성 파일을 텍스트로 변환하고 Notion에 자동 업로드하는 Windows 데스크톱 앱입니다.

[Whisper](https://github.com/SYSTRAN/faster-whisper) 기반 STT와 로컬 LLM(Gemma 3)을 활용한 AI 요약을 지원합니다.

---

## 주요 기능

- **음성 → 텍스트 변환** — faster-whisper(Whisper) 기반 한국어 최적화 STT
- **AI 요약** — 로컬 Gemma 3 1B/4B 모델로 전사 내용 자동 요약 (인터넷 불필요)
- **Notion 연동** — 변환 결과를 타임스탬프와 함께 Notion 페이지에 자동 업로드
- **로컬 저장** — Notion 없이 txt 파일로 저장 가능
- **드래그 앤 드롭** — mp3, wav, m4a, flac, aac, mp4, webm 지원
- **모델 관리** — 앱 내에서 STT / LLM 모델 다운로드 및 진행률 표시

## 스크린샷

> (추후 추가 예정)

---

## 설치

### 방법 1 — 인스톨러 사용 (권장)

[Releases](../../releases) 페이지에서 `STTNote_Setup.exe` 다운로드 후 실행

### 방법 2 — 소스에서 직접 실행

**요구사항**
- Python 3.11 이상
- Windows 10/11 (64-bit)

```bash
git clone https://github.com/<your-username>/stt_note.git
cd stt_note

python -m venv venv
venv\Scripts\activate

pip install -r requirements.txt
python main.py
```

> **llama-cpp-python** 설치 시 C++ 빌드 도구가 필요하거나, 빌드 없이 설치하려면
> [GitHub Releases](https://github.com/abetlen/llama-cpp-python/releases)에서 `.whl` 파일을 직접 받아 설치하세요.
> ```
> pip install llama_cpp_python-<version>-cp312-cp312-win_amd64.whl
> ```

---

## 사용법

### 초기 설정

**⚙ 설정** 버튼을 클릭하여:

1. **STT 모델** 선택 및 다운로드 (Base 권장)
2. **출력 방식** 선택
   - **Notion에 게시**: Notion Integration Token 입력
   - **txt 파일 저장**: 저장 폴더 선택
3. (선택) **AI 요약** 활성화 및 LLM 모델 다운로드

### 변환 실행

1. 녹음 파일을 드래그하거나 **파일 선택** 클릭
2. Notion 모드: 업로드할 페이지 검색 후 선택
3. **변환 & 업로드** (또는 **변환 & 저장**) 클릭

---

## 모델 정보

### STT 모델 (faster-whisper)

| 모델 | 크기 | 속도 | 정확도 |
|------|------|------|--------|
| Tiny | ~75 MB | 매우 빠름 | 낮음 |
| Base | ~150 MB | 빠름 | 권장 |
| Small | ~480 MB | 보통 | 양호 |
| Medium | ~1.5 GB | 느림 | 높음 |
| Large-v3 | ~3 GB | 매우 느림 | 최고 |

### LLM 모델 (llama.cpp / GGUF)

| 모델 | 크기 | 비고 |
|------|------|------|
| Gemma 3 1B | ~600 MB | 기본값, 빠름 |
| Gemma 3 4B | ~2 GB | 고품질 요약 |

모델 파일은 `~/.cache/huggingface/` 및 `~/.cache/llm/` 에 저장됩니다.

---

## 빌드 (Windows 인스톨러)

```bash
# 1. 의존성 설치
pip install pyinstaller

# 2. 빌드 (PyInstaller + Inno Setup)
build\build_windows.bat
# → dist\STTNote_Setup.exe 생성
```

Inno Setup이 없으면 [jrsoftware.org](https://jrsoftware.org/isdl.php) 에서 설치하세요.

---

## 기술 스택

- **UI** — PyQt6
- **STT** — [faster-whisper](https://github.com/SYSTRAN/faster-whisper) (CTranslate2)
- **LLM** — [llama-cpp-python](https://github.com/abetlen/llama-cpp-python) (GGUF)
- **Notion API** — [notion-client](https://github.com/ramnes/notion-sdk-py)
- **패키징** — PyInstaller + Inno Setup

## 라이선스

MIT

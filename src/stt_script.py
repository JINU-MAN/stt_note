"""
STT 독립 스크립트 — subprocess.Popen 으로 실행됩니다.
진행 상황과 결과를 JSON 라인으로 stdout 에 출력합니다.
"""
import argparse
import io
import json
import os
import sys
import traceback

# Windows stdout 기본 인코딩(CP949)을 UTF-8로 강제 설정
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")


def emit(data: dict):
    print(json.dumps(data, ensure_ascii=False), flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--audio",  required=True)
    parser.add_argument("--model",  default="base")
    parser.add_argument("--device", default="cpu")
    args = parser.parse_args()

    os.environ["OMP_NUM_THREADS"] = "1"
    os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"

    emit({"status": "progress", "pct": 0,
          "msg": f"Whisper {args.model} 모델 로딩 중..."})

    from faster_whisper import WhisperModel

    compute_type = "int8" if args.device == "cpu" else "float16"
    model = WhisperModel(args.model, device=args.device,
                         compute_type=compute_type, cpu_threads=1)

    emit({"status": "progress", "pct": -1,
          "msg": "음성 변환 중... (파일 길이에 따라 수 분 소요)"})

    segments_iter, info = model.transcribe(
        args.audio, language="ko", beam_size=5, vad_filter=True,
    )

    duration = info.duration
    segments = []
    for seg in segments_iter:
        # \ufffd(변환 불가 문자) 제거
        clean_text = seg.text.replace("\ufffd", "").strip()
        segments.append({"start": seg.start, "end": seg.end, "text": clean_text})
        if duration > 0:
            pct = min(int((seg.end / duration) * 85) + 5, 89)
            m,  s  = divmod(int(seg.end), 60)
            dm, ds = divmod(int(duration), 60)
            emit({"status": "progress", "pct": pct,
                  "msg": f"변환 중... {m:02d}:{s:02d} / {dm:02d}:{ds:02d}"})

    emit({"status": "done", "segments": segments, "duration": duration})


if __name__ == "__main__":
    try:
        main()
    except Exception:
        emit({"status": "error", "error": traceback.format_exc()})
        sys.exit(1)

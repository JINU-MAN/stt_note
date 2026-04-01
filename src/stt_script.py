"""
STT 독립 스크립트 (OpenVINO 버전) — subprocess.Popen 으로 실행됩니다.
진행 상황과 결과를 JSON 라인으로 stdout 에 출력합니다.
"""
import argparse
import io
import json
import sys
import traceback

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")


def emit(data: dict):
    print(json.dumps(data, ensure_ascii=False), flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--audio",     required=True)
    parser.add_argument("--model-dir", required=True, dest="model_dir")
    parser.add_argument("--device",    default="CPU")
    args = parser.parse_args()

    emit({"status": "progress", "pct": 0,
          "msg": f"Whisper 모델 로딩 중... (장치: {args.device})"})

    from optimum.intel import OVModelForSpeechSeq2Seq
    from transformers import AutoProcessor, pipeline

    model = OVModelForSpeechSeq2Seq.from_pretrained(args.model_dir, device=args.device)
    processor = AutoProcessor.from_pretrained(args.model_dir)

    pipe = pipeline(
        "automatic-speech-recognition",
        model=model,
        tokenizer=processor.tokenizer,
        feature_extractor=processor.feature_extractor,
        return_timestamps=True,
    )

    emit({"status": "progress", "pct": -1,
          "msg": "음성 변환 중... (파일 길이에 따라 수 분 소요)"})

    result = pipe(
        args.audio,
        generate_kwargs={"language": "ko", "task": "transcribe"},
    )

    # chunks → segments 형식 변환
    segments = []
    for chunk in result.get("chunks", []):
        ts = chunk.get("timestamp") or (0.0, 0.0)
        start = ts[0] if ts[0] is not None else 0.0
        end   = ts[1] if ts[1] is not None else start
        text  = chunk.get("text", "").replace("\ufffd", "").strip()
        if text:
            segments.append({"start": start, "end": end, "text": text})

    duration = segments[-1]["end"] if segments else 0.0

    emit({"status": "done", "segments": segments, "duration": duration})


if __name__ == "__main__":
    try:
        main()
    except Exception:
        emit({"status": "error", "error": traceback.format_exc()})
        sys.exit(1)

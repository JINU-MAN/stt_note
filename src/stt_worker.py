"""
STT 서브프로세스 진입점.
multiprocessing.Process로 실행되어 Qt와 완전히 분리된 환경에서 faster-whisper를 구동합니다.
"""
import logging
import os
import sys
from pathlib import Path


def _setup_logging():
    """서브프로세스에서도 같은 로그 파일에 기록."""
    log_dir = Path(os.environ.get("APPDATA", Path.home())) / "STTNote"
    log_dir.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s [%(levelname)s] STT-PROC: %(message)s",
        handlers=[
            logging.FileHandler(log_dir / "app.log", encoding="utf-8"),
            logging.StreamHandler(sys.stderr),
        ],
    )


def run(audio_path: str, model_size: str, device: str,
        result_queue, progress_queue) -> None:
    """별도 프로세스에서 실행되는 STT 함수."""
    _setup_logging()
    log = logging.getLogger(__name__)

    os.environ["OMP_NUM_THREADS"] = "1"
    os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"

    log.info("STT 서브프로세스 시작 — model=%s device=%s file=%s",
             model_size, device, audio_path)
    try:
        progress_queue.put((0, f"Whisper {model_size} 모델 로딩 중..."))

        log.info("faster-whisper 임포트 중...")
        from faster_whisper import WhisperModel
        log.info("faster-whisper 임포트 완료")

        compute_type = "int8" if device == "cpu" else "float16"
        log.info("WhisperModel 로딩 (compute_type=%s)...", compute_type)

        model = WhisperModel(model_size, device=device,
                             compute_type=compute_type, cpu_threads=1)
        log.info("WhisperModel 로딩 완료")

        progress_queue.put((-1, "음성 변환 중... (파일 길이에 따라 수 분 소요)"))

        log.info("transcribe 시작...")
        segments_iter, info = model.transcribe(
            audio_path, language="ko", beam_size=5, vad_filter=True,
        )

        duration = info.duration
        log.info("transcribe 완료 — 오디오 길이: %.1fs", duration)

        segments = []
        for seg in segments_iter:
            segments.append({
                "start": seg.start,
                "end": seg.end,
                "text": seg.text,
            })
            if duration > 0:
                pct = min(int((seg.end / duration) * 85) + 5, 89)
                m, s = divmod(int(seg.end), 60)
                dm, ds = divmod(int(duration), 60)
                progress_queue.put((pct, f"변환 중... {m:02d}:{s:02d} / {dm:02d}:{ds:02d}"))

        log.info("세그먼트 수집 완료 — %d개", len(segments))
        result_queue.put({"ok": True, "segments": segments, "duration": duration})

    except Exception:
        log.exception("STT 서브프로세스 예외")
        import traceback
        result_queue.put({"ok": False, "error": traceback.format_exc()})

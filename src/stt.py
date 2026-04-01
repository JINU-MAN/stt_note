from pathlib import Path

MODELS = ["tiny", "base", "small", "medium", "large-v3"]

MODEL_LABELS = {
    "tiny": "Tiny (빠름)",
    "base": "Base (권장)",
    "small": "Small",
    "medium": "Medium (정확)",
    "large-v3": "Large-v3 (최고)",
}

# OpenVINO IR 변환 후 예상 최소 크기 (bin 파일 기준, 실제 크기의 80%)
_OV_MODEL_MIN_BYTES = {
    "tiny":     80_000_000,
    "base":    150_000_000,
    "small":   500_000_000,
    "medium": 1_500_000_000,
    "large-v3": 3_000_000_000,
}

_OV_CACHE = Path.home() / ".cache" / "stt_note_ov" / "whisper"


def _model_dir(model_size: str) -> Path:
    return _OV_CACHE / model_size


def is_model_downloaded(model_size: str) -> bool:
    """OpenVINO Whisper 모델이 완전히 변환·저장됐는지 확인."""
    d = _model_dir(model_size)
    xml = d / "openvino_model.xml"
    bin_ = d / "openvino_model.bin"
    if not xml.exists() or not bin_.exists():
        return False
    return bin_.stat().st_size >= _OV_MODEL_MIN_BYTES.get(model_size, 0)


def is_model_corrupted(model_size: str) -> bool:
    """디렉터리는 있지만 모델 파일이 불완전한 상태인지 확인."""
    d = _model_dir(model_size)
    if not d.exists():
        return False
    xml = d / "openvino_model.xml"
    bin_ = d / "openvino_model.bin"
    # 디렉터리는 있는데 파일이 없거나 크기 미달
    if not xml.exists() or not bin_.exists():
        return True
    return bin_.stat().st_size < _OV_MODEL_MIN_BYTES.get(model_size, 0)


def download_model(model_size: str, device: str = "CPU") -> None:
    """HuggingFace에서 Whisper를 다운로드하고 OpenVINO IR로 변환·저장."""
    from optimum.intel import OVModelForSpeechSeq2Seq
    from transformers import AutoProcessor

    hf_id = f"openai/whisper-{model_size}"
    out_dir = _model_dir(model_size)
    out_dir.mkdir(parents=True, exist_ok=True)

    model = OVModelForSpeechSeq2Seq.from_pretrained(hf_id, export=True)
    model.save_pretrained(str(out_dir))

    processor = AutoProcessor.from_pretrained(hf_id)
    processor.save_pretrained(str(out_dir))

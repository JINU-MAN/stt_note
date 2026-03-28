from pathlib import Path

MODELS = ["tiny", "base", "small", "medium", "large-v3"]

MODEL_LABELS = {
    "tiny": "Tiny (빠름)",
    "base": "Base (권장)",
    "small": "Small",
    "medium": "Medium (정확)",
    "large-v3": "Large-v3 (최고)",
}

# CTranslate2 int8 변환 후 model.bin 최소 크기 (실제 크기의 90%)
_MODEL_MIN_BYTES = {
    "tiny":    33_000_000,
    "base":    64_000_000,
    "small":   215_000_000,
    "medium":  685_000_000,
    "large-v3": 1_380_000_000,
}


def _model_root(model_size: str) -> Path:
    cache_dir = Path.home() / ".cache" / "huggingface" / "hub"
    return cache_dir / f"models--Systran--faster-whisper-{model_size}"


def is_model_downloaded(model_size: str) -> bool:
    """faster-whisper 모델이 완전히 다운로드됐는지 확인.

    불완전한 다운로드는 False를 반환:
    - blobs/ 디렉토리에 .incomplete 파일이 존재하는 경우
    - model.bin 이 없거나 최소 크기 미달인 경우
    """
    root = _model_root(model_size)
    snapshots = root / "snapshots"
    if not snapshots.exists() or not any(snapshots.iterdir()):
        return False

    # .incomplete 파일 확인 (중단된 다운로드 마커)
    blobs = root / "blobs"
    if blobs.exists() and any(blobs.glob("*.incomplete")):
        return False

    # model.bin 크기 확인 (심볼릭 링크 → 실제 파일 따라가기)
    for snapshot_dir in snapshots.iterdir():
        model_bin = snapshot_dir / "model.bin"
        if model_bin.exists():
            actual_size = model_bin.stat().st_size
            min_size = _MODEL_MIN_BYTES.get(model_size, 0)
            return actual_size >= min_size

    return False


def is_model_corrupted(model_size: str) -> bool:
    """모델 폴더는 있지만 불완전한 다운로드 상태인지 확인."""
    root = _model_root(model_size)
    snapshots = root / "snapshots"
    if not snapshots.exists() or not any(snapshots.iterdir()):
        return False  # 아예 없는 경우 (corrupted 아님)

    blobs = root / "blobs"
    if blobs.exists() and any(blobs.glob("*.incomplete")):
        return True

    for snapshot_dir in snapshots.iterdir():
        model_bin = snapshot_dir / "model.bin"
        if model_bin.exists():
            actual_size = model_bin.stat().st_size
            min_size = _MODEL_MIN_BYTES.get(model_size, 0)
            return actual_size < min_size

    return False


def download_model(model_size: str, device: str = "cpu") -> None:
    """모델 파일을 HuggingFace hub에서 다운로드한다.
    WhisperModel을 로드하지 않으므로 QThread에서 안전하게 호출 가능.
    """
    from huggingface_hub import snapshot_download
    snapshot_download(repo_id=f"Systran/faster-whisper-{model_size}")

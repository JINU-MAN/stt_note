from pathlib import Path

LLM_MODELS = ["gemma3-1b", "gemma3-4b"]

LLM_MODEL_LABELS = {
    "gemma3-1b": "Gemma 3 1B (~770MB, 빠름)",
    "gemma3-4b": "Gemma 3 4B (~2.5GB, 정확)",
}

_SOURCES = {
    "gemma3-1b": {
        "repo_id": "bartowski/google_gemma-3-1b-it-GGUF",
        "filename": "google_gemma-3-1b-it-Q4_K_M.gguf",
        "min_bytes": 600_000_000,
    },
    "gemma3-4b": {
        "repo_id": "bartowski/google_gemma-3-4b-it-GGUF",
        "filename": "google_gemma-3-4b-it-Q4_K_M.gguf",
        "min_bytes": 2_000_000_000,
    },
}


def _model_dir() -> Path:
    return Path.home() / ".cache" / "stt_note" / "llm"


def model_path(model_size: str) -> str:
    return str(_model_dir() / _SOURCES[model_size]["filename"])


def is_llm_downloaded(model_size: str) -> bool:
    p = Path(model_path(model_size))
    if not p.exists():
        return False
    return p.stat().st_size >= _SOURCES[model_size]["min_bytes"]


def download_llm(model_size: str) -> None:
    from huggingface_hub import hf_hub_download
    src = _SOURCES[model_size]
    _model_dir().mkdir(parents=True, exist_ok=True)
    hf_hub_download(
        repo_id=src["repo_id"],
        filename=src["filename"],
        local_dir=str(_model_dir()),
        local_dir_use_symlinks=False,
    )

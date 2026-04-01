from pathlib import Path

LLM_MODELS = ["gemma3-1b", "gemma3-4b", "qwen2.5-0.5b", "qwen2.5-1.5b"]

LLM_MODEL_LABELS = {
    "gemma3-1b":   "Gemma 3 1B (~900MB, 빠름)",
    "gemma3-4b":   "Gemma 3 4B (~3GB, 정확)",
    "qwen2.5-0.5b": "Qwen2.5 0.5B (~450MB, 초경량)",
    "qwen2.5-1.5b": "Qwen2.5 1.5B (~1.4GB, 한국어 강점)",
}

_SOURCES = {
    "gemma3-1b": {
        "hf_id": "google/gemma-3-1b-it",
        "min_bytes": 800_000_000,
    },
    "gemma3-4b": {
        "hf_id": "google/gemma-3-4b-it",
        "min_bytes": 2_800_000_000,
    },
    "qwen2.5-0.5b": {
        "hf_id": "Qwen/Qwen2.5-0.5B-Instruct",
        "min_bytes": 400_000_000,
    },
    "qwen2.5-1.5b": {
        "hf_id": "Qwen/Qwen2.5-1.5B-Instruct",
        "min_bytes": 1_200_000_000,
    },
}

_OV_CACHE = Path.home() / ".cache" / "stt_note_ov" / "llm"


def model_dir(model_size: str) -> str:
    return str(_OV_CACHE / model_size)


def is_llm_downloaded(model_size: str) -> bool:
    d = Path(model_dir(model_size))
    xml = d / "openvino_model.xml"
    bin_ = d / "openvino_model.bin"
    if not xml.exists() or not bin_.exists():
        return False
    return bin_.stat().st_size >= _SOURCES[model_size]["min_bytes"]


def download_llm(model_size: str) -> None:
    """HuggingFace에서 LLM을 다운로드하고 OpenVINO IR로 변환·저장."""
    from optimum.intel import OVModelForCausalLM
    from transformers import AutoTokenizer

    hf_id = _SOURCES[model_size]["hf_id"]
    out_dir = Path(model_dir(model_size))
    out_dir.mkdir(parents=True, exist_ok=True)

    model = OVModelForCausalLM.from_pretrained(hf_id, export=True)
    model.save_pretrained(str(out_dir))

    tokenizer = AutoTokenizer.from_pretrained(hf_id)
    tokenizer.save_pretrained(str(out_dir))

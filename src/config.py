import json
import os
from pathlib import Path


class Config:
    APP_NAME = "STTNote"

    def __init__(self):
        appdata = os.environ.get("APPDATA", os.path.expanduser("~"))
        self.app_dir = Path(appdata) / self.APP_NAME
        self.app_dir.mkdir(parents=True, exist_ok=True)
        self.config_path = self.app_dir / "config.json"
        self._data: dict = {}
        self._load()

    def _load(self):
        if self.config_path.exists():
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    self._data = json.load(f)
            except Exception:
                self._data = {}

    def save(self):
        with open(self.config_path, "w", encoding="utf-8") as f:
            json.dump(self._data, f, ensure_ascii=False, indent=2)

    @property
    def notion_token(self) -> str:
        return self._data.get("notion_token", "")

    @notion_token.setter
    def notion_token(self, value: str):
        self._data["notion_token"] = value

    @property
    def model_size(self) -> str:
        return self._data.get("model_size", "base")

    @model_size.setter
    def model_size(self, value: str):
        self._data["model_size"] = value

    @property
    def device(self) -> str:
        return self._data.get("device", "CPU")

    @device.setter
    def device(self, value: str):
        self._data["device"] = value

    @property
    def notion_enabled(self) -> bool:
        return self._data.get("notion_enabled", False)

    @notion_enabled.setter
    def notion_enabled(self, value: bool):
        self._data["notion_enabled"] = value

    @property
    def output_folder(self) -> str:
        return self._data.get("output_folder", "")

    @output_folder.setter
    def output_folder(self, value: str):
        self._data["output_folder"] = value

    @property
    def llm_model_size(self) -> str:
        return self._data.get("llm_model_size", "qwen2.5-1.5b")

    @llm_model_size.setter
    def llm_model_size(self, value: str):
        self._data["llm_model_size"] = value

    @property
    def llm_summarize(self) -> bool:
        return self._data.get("llm_summarize", False)

    @llm_summarize.setter
    def llm_summarize(self, value: bool):
        self._data["llm_summarize"] = value

    @property
    def has_token(self) -> bool:
        return bool(self.notion_token.strip())

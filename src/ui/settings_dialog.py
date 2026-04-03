import threading
import time

from PyQt6.QtCore import QThread, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QRadioButton,
    QVBoxLayout,
)

from src.config import Config
from src.llm import LLM_MODELS, LLM_MODEL_LABELS, download_llm, is_llm_downloaded, model_dir as llm_model_dir, _SOURCES as _LLM_SOURCES, _clean_llm
from src.notion_api import NotionAPI
from src.stt import MODELS, MODEL_LABELS, download_model, is_model_downloaded, is_model_corrupted, _model_dir as stt_model_dir, _OV_MODEL_MIN_BYTES, _clean_model


# ---------------------------------------------------------------------------
# Background workers
# ---------------------------------------------------------------------------


class TestConnectionWorker(QThread):
    finished = pyqtSignal(bool, str)

    def __init__(self, token: str):
        super().__init__()
        self.token = token

    def run(self):
        try:
            NotionAPI(self.token).test_connection()
            self.finished.emit(True, "연결 확인됨")
        except Exception as exc:
            self.finished.emit(False, str(exc))


class DownloadModelWorker(QThread):
    progress = pyqtSignal(int, str)
    finished = pyqtSignal()
    error = pyqtSignal(str)

    def __init__(self, model_size: str, device: str):
        super().__init__()
        self.model_size = model_size
        self.device = device

    def run(self):
        from pathlib import Path
        expected = _OV_MODEL_MIN_BYTES.get(self.model_size, 0)
        model_d = stt_model_dir(self.model_size)
        monitoring = True

        def _monitor():
            while monitoring:
                if model_d.exists():
                    size = sum(
                        f.stat().st_size for f in model_d.iterdir()
                        if f.is_file()
                    )
                    if expected > 0 and size > 0:
                        denom = max(size, expected)
                        pct = min(int(size / denom * 95), 95)
                        done_mb = size / 1024 / 1024
                        total_mb = denom / 1024 / 1024
                        self.progress.emit(pct, f"변환·저장 중... {done_mb:.0f} / {total_mb:.0f} MB")
                time.sleep(1)

        threading.Thread(target=_monitor, daemon=True).start()
        try:
            download_model(self.model_size, self.device)
            if is_model_downloaded(self.model_size):
                self.finished.emit()
            else:
                self.error.emit("변환이 완료됐지만 모델 파일 검증 실패.\n재다운로드를 시도해 주세요.")
        except Exception as exc:
            self.error.emit(str(exc))
        finally:
            monitoring = False


class DownloadLLMWorker(QThread):
    progress = pyqtSignal(int, str)
    finished = pyqtSignal()
    error = pyqtSignal(str)

    def __init__(self, model_size: str):
        super().__init__()
        self.model_size = model_size

    def run(self):
        from pathlib import Path
        model_d = Path(llm_model_dir(self.model_size))
        expected = _LLM_SOURCES[self.model_size]["min_bytes"]
        monitoring = True

        def _monitor():
            while monitoring:
                if model_d.exists():
                    size = sum(
                        f.stat().st_size for f in model_d.iterdir()
                        if f.is_file()
                    )
                    if size > 0:
                        denom = max(size, expected)
                        pct = min(int(size / denom * 95), 95)
                        done_mb = size / 1024 / 1024
                        total_mb = denom / 1024 / 1024
                        self.progress.emit(pct, f"변환·저장 중... {done_mb:.0f} / {total_mb:.0f} MB")
                time.sleep(1)

        threading.Thread(target=_monitor, daemon=True).start()
        try:
            download_llm(self.model_size)
            if is_llm_downloaded(self.model_size):
                self.finished.emit()
            else:
                self.error.emit("변환이 완료됐지만 모델 파일 검증 실패.\n재다운로드를 시도해 주세요.")
        except Exception as exc:
            self.error.emit(str(exc))
        finally:
            monitoring = False


# ---------------------------------------------------------------------------
# Dialog
# ---------------------------------------------------------------------------


class SettingsDialog(QDialog):
    def __init__(self, config: Config, parent=None):
        super().__init__(parent)
        self.config = config
        self._test_worker: TestConnectionWorker | None = None
        self._dl_worker: DownloadModelWorker | None = None
        self._dl_llm_worker: DownloadLLMWorker | None = None

        self.setWindowTitle("설정")
        self.setMinimumWidth(460)
        self.setModal(True)

        self._build_ui()
        self._load_values()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(16, 16, 16, 16)

        # ── Notion API ──────────────────────────────────────────────────
        notion_group = QGroupBox("Notion API")
        ng_layout = QVBoxLayout(notion_group)

        self.notion_enable_check = QCheckBox("Notion에 게시")
        self.notion_enable_check.toggled.connect(self._on_notion_toggled)
        ng_layout.addWidget(self.notion_enable_check)

        self.token_lbl = QLabel("Integration Token")
        ng_layout.addWidget(self.token_lbl)

        token_row = QHBoxLayout()
        self.token_input = QLineEdit()
        self.token_input.setPlaceholderText("secret_...")
        self.token_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.test_btn = QPushButton("연결 테스트")
        self.test_btn.clicked.connect(self._test_connection)
        token_row.addWidget(self.token_input)
        token_row.addWidget(self.test_btn)
        ng_layout.addLayout(token_row)

        self.conn_lbl = QLabel("")
        ng_layout.addWidget(self.conn_lbl)

        layout.addWidget(notion_group)

        # ── STT 모델 ─────────────────────────────────────────────────────
        model_group = QGroupBox("STT 모델 (Whisper)")
        mg_layout = QVBoxLayout(model_group)

        self._model_radios: dict[str, QRadioButton] = {}
        self._model_btn_group = QButtonGroup(self)
        radio_row = QHBoxLayout()

        for model_id in MODELS:
            radio = QRadioButton(MODEL_LABELS.get(model_id, model_id))
            radio.setObjectName(model_id)
            radio.toggled.connect(
                lambda checked, m=model_id: self._on_model_changed(m) if checked else None
            )
            self._model_btn_group.addButton(radio)
            radio_row.addWidget(radio)
            self._model_radios[model_id] = radio

        mg_layout.addLayout(radio_row)

        status_row = QHBoxLayout()
        self.model_status_lbl = QLabel("")
        self.dl_btn = QPushButton("⬇  다운로드")
        self.dl_btn.clicked.connect(self._download_model)
        self.del_model_btn = QPushButton("🗑  삭제")
        self.del_model_btn.clicked.connect(self._delete_model)
        self.del_model_btn.setEnabled(False)
        status_row.addWidget(self.model_status_lbl)
        status_row.addStretch()
        status_row.addWidget(self.del_model_btn)
        status_row.addWidget(self.dl_btn)
        mg_layout.addLayout(status_row)

        self.model_dl_bar = QProgressBar()
        self.model_dl_bar.setRange(0, 100)
        self.model_dl_bar.setTextVisible(True)
        self.model_dl_bar.setVisible(False)
        mg_layout.addWidget(self.model_dl_bar)

        layout.addWidget(model_group)

        # ── 처리 장치 ─────────────────────────────────────────────────────
        device_group = QGroupBox("처리 장치 (OpenVINO)")
        dg_layout = QVBoxLayout(device_group)

        radio_row = QHBoxLayout()
        self._device_btn_group = QButtonGroup(self)
        self.cpu_radio = QRadioButton("CPU")
        self.gpu_radio = QRadioButton("GPU (Intel iGPU)")
        self.npu_radio = QRadioButton("NPU (Core Ultra)")
        for r in (self.cpu_radio, self.gpu_radio, self.npu_radio):
            self._device_btn_group.addButton(r)
            radio_row.addWidget(r)
        radio_row.addStretch()
        dg_layout.addLayout(radio_row)

        npu_note = QLabel("NPU는 Intel Core Ultra(Meteor Lake 이상) 탑재 기기에서만 사용 가능합니다.")
        npu_note.setStyleSheet("color: #888; font-size: 11px;")
        dg_layout.addWidget(npu_note)

        layout.addWidget(device_group)

        # ── AI 요약 ──────────────────────────────────────────────────────
        llm_group = QGroupBox("AI 요약 (OpenVINO GenAI)")
        lg_layout = QVBoxLayout(llm_group)

        self.llm_enable_check = QCheckBox("전사 완료 후 자동 요약")
        self.llm_enable_check.toggled.connect(self._on_llm_toggled)
        lg_layout.addWidget(self.llm_enable_check)

        self._llm_radios: dict[str, QRadioButton] = {}
        self._llm_btn_group = QButtonGroup(self)
        llm_radio_row = QHBoxLayout()
        for model_id in LLM_MODELS:
            radio = QRadioButton(LLM_MODEL_LABELS.get(model_id, model_id))
            radio.setObjectName(model_id)
            radio.toggled.connect(
                lambda checked, m=model_id: self._on_llm_model_changed(m) if checked else None
            )
            self._llm_btn_group.addButton(radio)
            llm_radio_row.addWidget(radio)
            self._llm_radios[model_id] = radio
        lg_layout.addLayout(llm_radio_row)

        llm_status_row = QHBoxLayout()
        self.llm_status_lbl = QLabel("")
        self.llm_dl_btn = QPushButton("⬇  다운로드")
        self.llm_dl_btn.clicked.connect(self._download_llm)
        self.del_llm_btn = QPushButton("🗑  삭제")
        self.del_llm_btn.clicked.connect(self._delete_llm)
        self.del_llm_btn.setEnabled(False)
        llm_status_row.addWidget(self.llm_status_lbl)
        llm_status_row.addStretch()
        llm_status_row.addWidget(self.del_llm_btn)
        llm_status_row.addWidget(self.llm_dl_btn)
        lg_layout.addLayout(llm_status_row)

        self.llm_dl_bar = QProgressBar()
        self.llm_dl_bar.setRange(0, 100)
        self.llm_dl_bar.setTextVisible(True)
        self.llm_dl_bar.setVisible(False)
        lg_layout.addWidget(self.llm_dl_bar)

        layout.addWidget(llm_group)

        # ── 저장 ──────────────────────────────────────────────────────────
        save_btn = QPushButton("저장")
        save_btn.setMinimumHeight(38)
        bold = QFont()
        bold.setBold(True)
        save_btn.setFont(bold)
        save_btn.setStyleSheet(
            "QPushButton { background-color: #4f46e5; color: white; border-radius: 6px; }"
            "QPushButton:hover { background-color: #4338ca; }"
        )
        save_btn.clicked.connect(self._save)
        layout.addWidget(save_btn)

    # ------------------------------------------------------------------
    # State helpers
    # ------------------------------------------------------------------

    def _load_values(self):
        self.token_input.setText(self.config.notion_token)
        self.notion_enable_check.setChecked(self.config.notion_enabled)
        self._on_notion_toggled(self.config.notion_enabled)

        model = self.config.model_size
        radio = self._model_radios.get(model) or self._model_radios["base"]
        radio.setChecked(True)
        self._update_model_status(model)

        device = self.config.device.upper()
        if device == "GPU":
            self.gpu_radio.setChecked(True)
        elif device == "NPU":
            self.npu_radio.setChecked(True)
        else:
            self.cpu_radio.setChecked(True)

        self.llm_enable_check.setChecked(self.config.llm_summarize)
        llm_model = self.config.llm_model_size
        llm_radio = self._llm_radios.get(llm_model) or self._llm_radios["qwen2.5-1.5b"]
        llm_radio.setChecked(True)
        self._update_llm_status(llm_model)
        self._on_llm_toggled(self.config.llm_summarize)

    def _on_notion_toggled(self, checked: bool):
        self.token_lbl.setEnabled(checked)
        self.token_input.setEnabled(checked)
        self.test_btn.setEnabled(checked)
        self.conn_lbl.setEnabled(checked)

    def _selected_model(self) -> str:
        for model_id, radio in self._model_radios.items():
            if radio.isChecked():
                return model_id
        return "base"

    def _selected_llm_model(self) -> str:
        for model_id, radio in self._llm_radios.items():
            if radio.isChecked():
                return model_id
        return "gemma3-1b"

    def _on_llm_toggled(self, checked: bool):
        for radio in self._llm_radios.values():
            radio.setEnabled(checked)
        self.llm_dl_btn.setEnabled(checked)
        self.llm_status_lbl.setEnabled(checked)

    def _on_llm_model_changed(self, model_id: str):
        self._update_llm_status(model_id)

    def _update_llm_status(self, model_id: str):
        downloaded = is_llm_downloaded(model_id)
        if downloaded:
            self.llm_status_lbl.setText("✅ 다운로드됨")
            self.llm_status_lbl.setStyleSheet("color: #16a34a;")
            self.llm_dl_btn.setEnabled(False)
            self.llm_dl_btn.setText("✅ 완료")
        else:
            self.llm_status_lbl.setText("❌ 다운로드 필요")
            self.llm_status_lbl.setStyleSheet("color: #dc2626;")
            self.llm_dl_btn.setEnabled(True)
            self.llm_dl_btn.setText("⬇  다운로드")
        self.del_llm_btn.setEnabled(downloaded)

    def _on_model_changed(self, model_id: str):
        self._update_model_status(model_id)

    def _update_model_status(self, model_id: str):
        downloaded = is_model_downloaded(model_id)
        corrupted = is_model_corrupted(model_id)
        if downloaded:
            self.model_status_lbl.setText("✅ 다운로드됨")
            self.model_status_lbl.setStyleSheet("color: #16a34a;")
            self.dl_btn.setEnabled(False)
            self.dl_btn.setText("✅ 완료")
        elif corrupted:
            self.model_status_lbl.setText("⚠️ 변환 실패 — 재다운로드 필요")
            self.model_status_lbl.setStyleSheet("color: #b45309;")
            self.dl_btn.setEnabled(True)
            self.dl_btn.setText("⬇  재다운로드")
        else:
            self.model_status_lbl.setText("❌ 다운로드 필요")
            self.model_status_lbl.setStyleSheet("color: #dc2626;")
            self.dl_btn.setEnabled(True)
            self.dl_btn.setText("⬇  다운로드")
        self.del_model_btn.setEnabled(downloaded or corrupted)

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def _delete_model(self):
        model_id = self._selected_model()
        reply = QMessageBox.question(
            self, "모델 삭제",
            f"Whisper {model_id} 모델을 삭제할까요?\n(재사용하려면 다시 다운로드해야 합니다)",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            _clean_model(model_id)
            self._update_model_status(model_id)

    def _delete_llm(self):
        model_id = self._selected_llm_model()
        reply = QMessageBox.question(
            self, "모델 삭제",
            f"{LLM_MODEL_LABELS.get(model_id, model_id)} 모델을 삭제할까요?\n(재사용하려면 다시 다운로드해야 합니다)",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            _clean_llm(model_id)
            self._update_llm_status(model_id)

    def _test_connection(self):
        token = self.token_input.text().strip()
        if not token:
            QMessageBox.warning(self, "경고", "API Token을 입력해주세요.")
            return

        self.test_btn.setEnabled(False)
        self.conn_lbl.setText("⏳ 연결 확인 중...")
        self.conn_lbl.setStyleSheet("color: #92400e;")

        self._test_worker = TestConnectionWorker(token)
        self._test_worker.finished.connect(self._on_test_result)
        self._test_worker.start()

    def _on_test_result(self, success: bool, message: str):
        self.test_btn.setEnabled(True)
        if success:
            self.conn_lbl.setText("✅ " + message)
            self.conn_lbl.setStyleSheet("color: #16a34a;")
        else:
            self.conn_lbl.setText(f"❌ 연결 실패: {message}")
            self.conn_lbl.setStyleSheet("color: #dc2626;")

    def _selected_device(self) -> str:
        if self.gpu_radio.isChecked():
            return "GPU"
        if self.npu_radio.isChecked():
            return "NPU"
        return "CPU"

    def _download_model(self):
        model_id = self._selected_model()
        device = self._selected_device()

        self.dl_btn.setEnabled(False)
        self.dl_btn.setText("다운로드 중...")
        self.model_status_lbl.setText("⏳ 다운로드 중... (수 분 소요될 수 있습니다)")
        self.model_status_lbl.setStyleSheet("color: #92400e;")

        self._dl_worker = DownloadModelWorker(model_id, device)
        self._dl_worker.progress.connect(self._on_model_dl_progress)
        self._dl_worker.finished.connect(lambda: self._on_download_done(model_id))
        self._dl_worker.error.connect(self._on_download_error)
        self._dl_worker.start()

    def _on_model_dl_progress(self, pct: int, msg: str):
        self.model_dl_bar.setVisible(True)
        self.model_dl_bar.setValue(pct)
        self.model_dl_bar.setFormat(f"{msg}  ({pct}%)")
        self.model_status_lbl.setText("⏳ 변환·저장 중...")
        self.model_status_lbl.setStyleSheet("color: #92400e;")

    def _on_download_done(self, model_id: str):
        self.model_dl_bar.setVisible(False)
        self._update_model_status(model_id)
        QMessageBox.information(self, "완료", f"Whisper {model_id} 모델 준비 완료!")

    def _on_download_error(self, msg: str):
        self.model_dl_bar.setVisible(False)
        self.dl_btn.setEnabled(True)
        self.dl_btn.setText("⬇  다운로드")
        self.model_status_lbl.setText("❌ 다운로드 실패")
        self.model_status_lbl.setStyleSheet("color: #dc2626;")
        QMessageBox.critical(self, "다운로드 오류", f"다운로드 실패:\n\n{msg}")

    def _download_llm(self):
        model_id = self._selected_llm_model()
        self.llm_dl_btn.setEnabled(False)
        self.llm_dl_btn.setText("다운로드 중...")
        self.llm_status_lbl.setText("⏳ 다운로드 중... (수 분 소요될 수 있습니다)")
        self.llm_status_lbl.setStyleSheet("color: #92400e;")

        self._dl_llm_worker = DownloadLLMWorker(model_id)
        self._dl_llm_worker.progress.connect(self._on_llm_dl_progress)
        self._dl_llm_worker.finished.connect(lambda: self._on_llm_download_done(model_id))
        self._dl_llm_worker.error.connect(self._on_llm_download_error)
        self._dl_llm_worker.start()

    def _on_llm_dl_progress(self, pct: int, msg: str):
        self.llm_dl_bar.setVisible(True)
        self.llm_dl_bar.setValue(pct)
        self.llm_dl_bar.setFormat(f"{msg}  ({pct}%)")
        self.llm_status_lbl.setText("⏳ 변환·저장 중...")
        self.llm_status_lbl.setStyleSheet("color: #92400e;")

    def _on_llm_download_done(self, model_id: str):
        self.llm_dl_bar.setVisible(False)
        self._update_llm_status(model_id)
        QMessageBox.information(self, "완료", f"{LLM_MODEL_LABELS.get(model_id, model_id)} 준비 완료!")

    def _on_llm_download_error(self, msg: str):
        self.llm_dl_bar.setVisible(False)
        self.llm_dl_btn.setEnabled(True)
        self.llm_dl_btn.setText("⬇  다운로드")
        self.llm_status_lbl.setText("❌ 다운로드 실패")
        self.llm_status_lbl.setStyleSheet("color: #dc2626;")
        QMessageBox.critical(self, "다운로드 오류", f"LLM 다운로드 실패:\n\n{msg}")

    def _save(self):
        notion_on = self.notion_enable_check.isChecked()
        if notion_on and not self.token_input.text().strip():
            QMessageBox.warning(self, "경고", "Notion에 게시하려면 API Token을 입력해주세요.")
            return

        self.config.notion_enabled = notion_on
        self.config.notion_token = self.token_input.text().strip()
        self.config.model_size = self._selected_model()
        self.config.device = self._selected_device()
        self.config.llm_summarize = self.llm_enable_check.isChecked()
        self.config.llm_model_size = self._selected_llm_model()
        self.config.save()
        self.accept()

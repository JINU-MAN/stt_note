import json
import logging
import subprocess
import sys
import threading
import traceback
from pathlib import Path

from PyQt6.QtCore import Qt, QThread, QTimer, pyqtSignal
from PyQt6.QtGui import QDragEnterEvent, QDropEvent, QFont

log = logging.getLogger(__name__)
from PyQt6.QtWidgets import (
    QCheckBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from src.config import Config
from src.formatter import segments_to_notion_blocks, segments_to_text, summary_to_notion_blocks
from src.llm import is_llm_downloaded, model_dir as llm_model_dir
from src.notion_api import NotionAPI
from src.stt import is_model_downloaded, is_model_corrupted, _model_dir as stt_model_dir


def _worker_cmd(name: str) -> list[str]:
    """frozen .exe이면 같은 디렉터리의 {name}.exe, 아니면 src/{name}.py를 반환."""
    if getattr(sys, "frozen", False):
        exe = Path(sys.executable).parent / f"{name}.exe"
        return [str(exe)]
    script = Path(__file__).parent.parent / f"{name}.py"
    return [sys.executable, str(script)]


# ---------------------------------------------------------------------------
# Workers
# ---------------------------------------------------------------------------


class SearchWorker(QThread):
    finished = pyqtSignal(list)

    def __init__(self, api: NotionAPI, query: str):
        super().__init__()
        self.api = api
        self.query = query

    def run(self):
        try:
            self.finished.emit(self.api.search_pages(self.query))
        except Exception:
            self.finished.emit([])


class ProcessWorker(QThread):
    """
    STT를 subprocess.Popen으로 완전히 별도 Python 인터프리터에서 실행합니다.
    stt_script.py가 JSON 라인을 stdout으로 출력하면 이 스레드가 읽어서 UI에 전달합니다.
    progress 시그널: pct=-1 이면 인디케이터(bouncing) 모드.
    """

    progress = pyqtSignal(int, str)
    finished = pyqtSignal(str, str)   # (target_page_id, full_text)
    error = pyqtSignal(str)

    def __init__(self, config: Config, audio_path: str, page_id: str,
                 create_subpage: bool, subpage_title: str, output_folder: str = ""):
        super().__init__()
        self.config = config
        self.audio_path = audio_path
        self.page_id = page_id
        self.create_subpage = create_subpage
        self.subpage_title = subpage_title
        self.output_folder = output_folder

    def run(self):
        try:
            # ── 1. STT: 별도 Python 인터프리터로 실행 ───────────────────
            proc = subprocess.Popen(
                _worker_cmd("stt_script") + [
                    "--audio",     self.audio_path,
                    "--model-dir", str(stt_model_dir(self.config.model_size)),
                    "--device",    self.config.device,
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
            )

            # stderr를 별도 스레드로 수집 (stdout 읽기와 데드락 방지)
            stderr_lines: list[str] = []
            def _read_stderr():
                for line in proc.stderr:
                    stderr_lines.append(line)
                    log.debug("STT-PROC stderr: %s", line.rstrip())
            threading.Thread(target=_read_stderr, daemon=True).start()

            # stdout JSON 라인 파싱
            segments: list | None = None
            duration: float = 0.0

            for raw in proc.stdout:
                raw = raw.strip()
                if not raw:
                    continue
                try:
                    data = json.loads(raw)
                except json.JSONDecodeError:
                    log.debug("STT-PROC non-JSON: %s", raw)
                    continue

                status = data.get("status")
                if status == "progress":
                    self.progress.emit(data["pct"], data["msg"])
                elif status == "done":
                    segments = data["segments"]
                    duration = data["duration"]
                elif status == "error":
                    log.error("STT-PROC 오류:\n%s", data["error"])
                    self.error.emit(data["error"])
                    proc.wait()
                    return

            proc.wait()
            log.info("STT 스크립트 종료 (returncode=%s)", proc.returncode)

            if proc.returncode != 0 or segments is None:
                stderr_text = "".join(stderr_lines)
                log.error("STT 스크립트 비정상 종료\nstderr:\n%s", stderr_text)
                self.error.emit(
                    f"STT 실패 (returncode={proc.returncode})\n\n{stderr_text or '오류 출력 없음'}"
                )
                return

            # dict 세그먼트 → formatter용 객체 변환
            class _Seg:
                __slots__ = ("start", "end", "text")
                def __init__(self, d):
                    self.start, self.end, self.text = d["start"], d["end"], d["text"]

            segs = [_Seg(s) for s in segments]

            filename = Path(self.audio_path).name
            full_text = " ".join(s.text.strip() for s in segs if s.text.strip())

            if self.output_folder:
                # ── 2. txt 파일 저장 ─────────────────────────────────────
                self.progress.emit(92, "텍스트 파일 저장 중...")
                stem = Path(self.audio_path).stem
                out_path = Path(self.output_folder) / f"{stem}.txt"
                text = segments_to_text(segs, filename, duration)
                with open(out_path, "w", encoding="utf-8") as f:
                    f.write(text)
                self.progress.emit(100, "완료!")
                self.finished.emit("", full_text)

            else:
                # ── 2. Notion 블록 생성 ──────────────────────────────────
                self.progress.emit(90, "Notion 블록 생성 중...")
                blocks = segments_to_notion_blocks(segs, filename, duration)

                # ── 3. Notion 업로드 ─────────────────────────────────────
                self.progress.emit(92, "Notion에 연결 중...")
                api = NotionAPI(self.config.notion_token)

                target_id = self.page_id
                if self.create_subpage:
                    self.progress.emit(93, f"하위 페이지 '{self.subpage_title}' 생성 중...")
                    target_id = api.create_child_page(self.page_id, self.subpage_title)

                total = len(blocks)
                for i in range(0, total, 100):
                    api.append_blocks(target_id, blocks[i:i + 100])
                    pct = 93 + int(((i + 100) / total) * 7)
                    self.progress.emit(min(pct, 99),
                                       f"업로드 중... ({min(i + 100, total)}/{total} 블록)")

                self.progress.emit(100, "완료!")
                self.finished.emit(target_id, full_text)

        except Exception:
            log.exception("ProcessWorker 오류")
            self.error.emit(traceback.format_exc())


class SummarizeWorker(QThread):
    """LLM 요약을 별도 subprocess에서 실행하고 결과를 Notion에 추가합니다."""

    progress = pyqtSignal(int, str)
    finished = pyqtSignal()
    error = pyqtSignal(str)

    def __init__(self, config, page_id: str, full_text: str):
        super().__init__()
        self.config = config
        self.page_id = page_id
        self.full_text = full_text

    def run(self):
        import tempfile
        import os

        tmp_path = None
        try:
            # 텍스트를 임시 파일로 저장 (커맨드라인 길이 제한 우회)
            with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", suffix=".txt", delete=False
            ) as f:
                f.write(self.full_text)
                tmp_path = f.name

            proc = subprocess.Popen(
                _worker_cmd("llm_script") + [
                    "--model-dir", llm_model_dir(self.config.llm_model_size),
                    "--device",    self.config.device,
                    "--text-file", tmp_path,
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
            )

            stderr_lines: list[str] = []
            def _read_stderr():
                for line in proc.stderr:
                    stderr_lines.append(line)
                    log.debug("LLM-PROC stderr: %s", line.rstrip())
            threading.Thread(target=_read_stderr, daemon=True).start()

            summary: str | None = None
            chunk_summaries: list[str] = []

            for raw in proc.stdout:
                raw = raw.strip()
                if not raw:
                    continue
                try:
                    data = json.loads(raw)
                except json.JSONDecodeError:
                    continue

                status = data.get("status")
                if status == "progress":
                    self.progress.emit(data["pct"], data["msg"])
                elif status == "done":
                    summary = data["summary"]
                    chunk_summaries = data.get("chunk_summaries", [])
                elif status == "error":
                    log.error("LLM-PROC 오류:\n%s", data["error"])
                    self.error.emit(data["error"])
                    proc.wait()
                    return

            proc.wait()

            if proc.returncode != 0 or summary is None:
                stderr_text = "".join(stderr_lines)
                self.error.emit(f"요약 실패 (returncode={proc.returncode})\n\n{stderr_text or '오류 출력 없음'}")
                return

            self.progress.emit(95, "요약을 Notion에 업로드 중...")
            blocks = summary_to_notion_blocks(summary, chunk_summaries)
            api = NotionAPI(self.config.notion_token)
            api.append_blocks(self.page_id, blocks)

            self.progress.emit(100, "완료!")
            self.finished.emit()

        except Exception:
            log.exception("SummarizeWorker 오류")
            self.error.emit(traceback.format_exc())
        finally:
            if tmp_path:
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass


# ---------------------------------------------------------------------------
# File drop area
# ---------------------------------------------------------------------------


class FileDropArea(QFrame):
    SUPPORTED = (".mp3", ".wav", ".m4a", ".ogg", ".flac", ".aac", ".mp4", ".webm")
    file_selected = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.setAcceptDrops(True)
        self.setMinimumHeight(110)
        self.setFrameStyle(QFrame.Shape.StyledPanel)
        self._apply_idle_style()

        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(6)

        icon = QLabel("🎙")
        icon_font = QFont()
        icon_font.setPointSize(26)
        icon.setFont(icon_font)
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)

        hint = QLabel("녹음 파일을 여기에 드래그하거나")
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hint.setStyleSheet("color: #666;")

        btn = QPushButton("파일 선택")
        btn.setMaximumWidth(110)
        btn.clicked.connect(self._open_dialog)

        layout.addWidget(icon)
        layout.addWidget(hint)
        layout.addWidget(btn, alignment=Qt.AlignmentFlag.AlignCenter)

    def _apply_idle_style(self):
        self.setStyleSheet(
            "FileDropArea { border: 2px dashed #bbb; border-radius: 8px; background: #fafafa; }"
        )

    def _apply_hover_style(self):
        self.setStyleSheet(
            "FileDropArea { border: 2px dashed #4f46e5; border-radius: 8px; background: #eef2ff; }"
        )

    def _open_dialog(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "녹음 파일 선택",
            "",
            "오디오 파일 (*.mp3 *.wav *.m4a *.ogg *.flac *.aac *.mp4 *.webm);;모든 파일 (*)",
        )
        if path:
            self.file_selected.emit(path)

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            path = event.mimeData().urls()[0].toLocalFile()
            if path.lower().endswith(self.SUPPORTED):
                event.acceptProposedAction()
                self._apply_hover_style()
                return
        event.ignore()

    def dragLeaveEvent(self, event):
        self._apply_idle_style()

    def dropEvent(self, event: QDropEvent):
        self._apply_idle_style()
        path = event.mimeData().urls()[0].toLocalFile()
        if path.lower().endswith(self.SUPPORTED):
            self.file_selected.emit(path)


# ---------------------------------------------------------------------------
# Page selector with live search
# ---------------------------------------------------------------------------


class PageSelector(QWidget):
    page_selected = pyqtSignal(str, str)  # id, title

    def __init__(self):
        super().__init__()
        self._api: NotionAPI | None = None
        self._selected_id: str | None = None
        self._worker: SearchWorker | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        row = QHBoxLayout()
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("🔍 페이지 이름으로 검색...")
        self.search_input.textChanged.connect(self._on_text_changed)

        self.refresh_btn = QPushButton("🔄")
        self.refresh_btn.setFixedWidth(38)
        self.refresh_btn.setToolTip("목록 새로고침")
        self.refresh_btn.clicked.connect(lambda: self._do_search(self.search_input.text()))

        row.addWidget(self.search_input)
        row.addWidget(self.refresh_btn)
        layout.addLayout(row)

        self.list_widget = QListWidget()
        self.list_widget.setMaximumHeight(140)
        self.list_widget.setStyleSheet(
            "QListWidget { border: 1px solid #ccc; border-radius: 4px; }"
            "QListWidget::item:selected { background: #4f46e5; color: white; }"
        )
        self.list_widget.itemClicked.connect(self._on_item_clicked)
        layout.addWidget(self.list_widget)

        self._debounce = QTimer()
        self._debounce.setSingleShot(True)
        self._debounce.timeout.connect(lambda: self._do_search(self.search_input.text()))

    def set_api(self, api: NotionAPI):
        self._api = api
        self._do_search("")

    def _on_text_changed(self, text: str):
        self._debounce.start(500)

    def _do_search(self, query: str):
        if not self._api:
            return
        self.list_widget.clear()
        self.list_widget.addItem("검색 중...")
        self.list_widget.setEnabled(False)

        self._worker = SearchWorker(self._api, query)
        self._worker.finished.connect(self._on_results)
        self._worker.start()

    def _on_results(self, pages: list):
        self.list_widget.setEnabled(True)
        self.list_widget.clear()
        if not pages:
            self.list_widget.addItem("(결과 없음)")
            return
        for page in pages:
            item = QListWidgetItem(page["title"])
            item.setData(Qt.ItemDataRole.UserRole, page["id"])
            self.list_widget.addItem(item)
        # Restore previous selection highlight
        if self._selected_id:
            for i in range(self.list_widget.count()):
                item = self.list_widget.item(i)
                if item and item.data(Qt.ItemDataRole.UserRole) == self._selected_id:
                    self.list_widget.setCurrentRow(i)
                    break

    def _on_item_clicked(self, item: QListWidgetItem):
        page_id = item.data(Qt.ItemDataRole.UserRole)
        if not page_id:
            return
        self._selected_id = page_id
        self.page_selected.emit(page_id, item.text())

    @property
    def selected_id(self) -> str | None:
        return self._selected_id


# ---------------------------------------------------------------------------
# Main window
# ---------------------------------------------------------------------------


class MainWindow(QMainWindow):
    def __init__(self, config: Config):
        super().__init__()
        self.config = config
        self._audio_path: str | None = None
        self._selected_page_id: str | None = None
        self._output_folder: str = config.output_folder
        self._worker: ProcessWorker | None = None
        self._sum_worker: SummarizeWorker | None = None
        self._prev_file_stem = ""

        self.setWindowTitle("STT Note")
        self.setMinimumSize(540, 620)

        self._build_ui()
        self._apply_output_mode()
        self._update_run_btn()

        if not self.config.notion_enabled and not self.config.output_folder:
            QTimer.singleShot(100, self._open_settings)
        elif self.config.notion_enabled and not self.config.has_token:
            QTimer.singleShot(100, self._open_settings)

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self):
        root = QWidget()
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)

        # Header
        header = QHBoxLayout()
        title_lbl = QLabel("STT Note")
        title_font = QFont()
        title_font.setPointSize(15)
        title_font.setBold(True)
        title_lbl.setFont(title_font)
        self.settings_btn = QPushButton("⚙  설정")
        self.settings_btn.clicked.connect(self._open_settings)
        header.addWidget(title_lbl)
        header.addStretch()
        header.addWidget(self.settings_btn)
        layout.addLayout(header)

        layout.addWidget(self._hline())

        # File section
        layout.addWidget(self._section_label("📁  녹음 파일"))
        self.drop_area = FileDropArea()
        self.drop_area.file_selected.connect(self._on_file_selected)
        layout.addWidget(self.drop_area)

        self.file_info_lbl = QLabel("")
        self.file_info_lbl.setStyleSheet("color: #555; font-size: 12px;")
        layout.addWidget(self.file_info_lbl)

        # Output section label (동적으로 텍스트 변경)
        self._output_section_lbl = self._section_label("📄  Notion 페이지")
        layout.addWidget(self._output_section_lbl)

        # ── Notion 위젯 ──────────────────────────────────────────────────
        self._notion_widget = QWidget()
        notion_layout = QVBoxLayout(self._notion_widget)
        notion_layout.setContentsMargins(0, 0, 0, 0)
        notion_layout.setSpacing(6)

        self.page_selector = PageSelector()
        self.page_selector.page_selected.connect(self._on_page_selected)
        notion_layout.addWidget(self.page_selector)

        self.subpage_check = QCheckBox("하위 페이지로 생성")
        self.subpage_check.toggled.connect(self._on_subpage_toggled)
        notion_layout.addWidget(self.subpage_check)

        sub_row = QHBoxLayout()
        sub_row.setContentsMargins(20, 0, 0, 0)
        sub_row.addWidget(QLabel("페이지 이름:"))
        self.subpage_name = QLineEdit()
        self.subpage_name.setEnabled(False)
        self.subpage_name.setPlaceholderText("하위 페이지 이름")
        sub_row.addWidget(self.subpage_name)
        notion_layout.addLayout(sub_row)

        layout.addWidget(self._notion_widget)

        # ── txt 저장 위젯 ────────────────────────────────────────────────
        self._txt_widget = QWidget()
        txt_layout = QHBoxLayout(self._txt_widget)
        txt_layout.setContentsMargins(0, 0, 0, 0)

        self.folder_btn = QPushButton("📁  폴더 선택")
        self.folder_btn.setFixedWidth(110)
        self.folder_btn.clicked.connect(self._select_output_folder)
        self.folder_lbl = QLabel("선택된 폴더 없음")
        self.folder_lbl.setStyleSheet("color: #555; font-size: 12px;")
        txt_layout.addWidget(self.folder_btn)
        txt_layout.addWidget(self.folder_lbl, 1)

        layout.addWidget(self._txt_widget)

        layout.addWidget(self._hline())

        # Progress
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_bar.setTextVisible(True)
        layout.addWidget(self.progress_bar)

        self.status_lbl = QLabel("")
        self.status_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_lbl.setStyleSheet("color: #555; font-size: 12px;")
        layout.addWidget(self.status_lbl)

        layout.addStretch()

        # Run button
        self.run_btn = QPushButton("변환 & 업로드")
        self.run_btn.setMinimumHeight(46)
        run_font = QFont()
        run_font.setPointSize(12)
        run_font.setBold(True)
        self.run_btn.setFont(run_font)
        self.run_btn.setStyleSheet(
            "QPushButton { background-color: #4f46e5; color: white; border-radius: 8px; }"
            "QPushButton:hover { background-color: #4338ca; }"
            "QPushButton:disabled { background-color: #d1d5db; color: #9ca3af; }"
        )
        self.run_btn.clicked.connect(self._start)
        layout.addWidget(self.run_btn)

    @staticmethod
    def _hline() -> QFrame:
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFrameShadow(QFrame.Shadow.Sunken)
        return line

    @staticmethod
    def _section_label(text: str) -> QLabel:
        lbl = QLabel(text)
        f = QFont()
        f.setBold(True)
        lbl.setFont(f)
        return lbl

    # ------------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------------

    def _apply_output_mode(self):
        notion = self.config.notion_enabled
        self._output_section_lbl.setText("📄  Notion 페이지" if notion else "💾  저장 위치")
        self._notion_widget.setVisible(notion)
        self._txt_widget.setVisible(not notion)
        self.run_btn.setText("변환 & 업로드" if notion else "변환 & 저장")
        if notion:
            self._refresh_notion()
        else:
            folder = self._output_folder
            self.folder_lbl.setText(folder if folder else "선택된 폴더 없음")

    def _refresh_notion(self):
        if self.config.has_token:
            self.page_selector.set_api(NotionAPI(self.config.notion_token))

    def _on_file_selected(self, path: str):
        self._audio_path = path
        stem = Path(path).stem
        self.file_info_lbl.setText(f"선택됨: {Path(path).name}")
        # Update subpage name only if user hasn't customised it
        if not self.subpage_name.text() or self.subpage_name.text() == self._prev_file_stem:
            self.subpage_name.setText(stem)
        self._prev_file_stem = stem
        self._update_run_btn()

    def _on_page_selected(self, page_id: str, _title: str):
        self._selected_page_id = page_id
        self._update_run_btn()

    def _on_subpage_toggled(self, checked: bool):
        self.subpage_name.setEnabled(checked)
        if checked and self._audio_path and not self.subpage_name.text():
            self.subpage_name.setText(Path(self._audio_path).stem)

    def _select_output_folder(self):
        from PyQt6.QtWidgets import QFileDialog
        folder = QFileDialog.getExistingDirectory(self, "저장 폴더 선택", self._output_folder or "")
        if folder:
            self._output_folder = folder
            self.config.output_folder = folder
            self.config.save()
            self.folder_lbl.setText(folder)
            self._update_run_btn()

    def _update_run_btn(self):
        if self.config.notion_enabled:
            enabled = (
                bool(self._audio_path)
                and bool(self._selected_page_id)
                and self.config.has_token
            )
        else:
            enabled = bool(self._audio_path) and bool(self._output_folder)
        self.run_btn.setEnabled(enabled)

    def _open_settings(self):
        from src.ui.settings_dialog import SettingsDialog

        dlg = SettingsDialog(self.config, parent=self)
        dlg.exec()
        self._output_folder = self.config.output_folder
        self._apply_output_mode()
        self._update_run_btn()

    # ------------------------------------------------------------------
    # Process
    # ------------------------------------------------------------------

    def _start(self):
        if not self._audio_path or not self._selected_page_id:
            return

        if not self.config.notion_enabled and not self._output_folder:
            QMessageBox.warning(self, "저장 위치 없음", "저장할 폴더를 선택해주세요.")
            return

        if not is_model_downloaded(self.config.model_size):
            if is_model_corrupted(self.config.model_size):
                msg = (
                    f"Whisper {self.config.model_size} 모델 다운로드가 중간에 중단되어 파일이 불완전합니다.\n"
                    "설정 화면에서 다시 다운로드해 주세요."
                )
                QMessageBox.warning(self, "모델 파일 손상", msg)
            else:
                reply = QMessageBox.question(
                    self,
                    "모델 다운로드 필요",
                    f"Whisper {self.config.model_size} 모델이 로컬에 없습니다.\n"
                    "지금 다운로드를 시작할까요? (처음 실행 시 수 분 소요)\n\n"
                    "'예'를 누르면 변환을 시작하며 다운로드가 자동으로 진행됩니다.",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                )
                if reply != QMessageBox.StandardButton.Yes:
                    return
            return

        create_sub = self.subpage_check.isChecked()
        sub_title = self.subpage_name.text().strip() if create_sub else ""
        if create_sub and not sub_title:
            sub_title = Path(self._audio_path).stem

        self.run_btn.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.status_lbl.setText("준비 중...")

        self._worker = ProcessWorker(
            config=self.config,
            audio_path=self._audio_path,
            page_id=self._selected_page_id or "",
            create_subpage=create_sub,
            subpage_title=sub_title,
            output_folder="" if self.config.notion_enabled else self._output_folder,
        )
        self._worker.progress.connect(self._on_progress)
        self._worker.finished.connect(self._on_stt_done)
        self._worker.error.connect(self._on_error)
        self._worker.start()

    def _on_progress(self, pct: int, msg: str):
        if pct == -1:
            # 인디케이터(bouncing) 모드
            self.progress_bar.setRange(0, 0)
        else:
            self.progress_bar.setRange(0, 100)
            self.progress_bar.setValue(pct)
        self.status_lbl.setText(msg)

    def _on_stt_done(self, page_id: str, full_text: str):
        if self.config.notion_enabled and self.config.llm_summarize and is_llm_downloaded(self.config.llm_model_size):
            self.status_lbl.setText("📝 요약 중...")
            self.progress_bar.setRange(0, 100)
            self.progress_bar.setValue(0)
            self._sum_worker = SummarizeWorker(self.config, page_id, full_text)
            self._sum_worker.progress.connect(self._on_progress)
            self._sum_worker.finished.connect(self._on_done)
            self._sum_worker.error.connect(self._on_summarize_error)
            self._sum_worker.start()
        else:
            self._on_done()

    def _on_done(self):
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(100)
        if self.config.notion_enabled:
            self.status_lbl.setText("✅ Notion에 업로드 완료!")
            msg = "Notion에 성공적으로 업로드되었습니다."
        else:
            self.status_lbl.setText("✅ 저장 완료!")
            msg = f"txt 파일이 저장되었습니다.\n{self._output_folder}"
        self.run_btn.setEnabled(True)
        QMessageBox.information(self, "완료", msg)

    def _on_summarize_error(self, msg: str):
        log.error("요약 오류:\n%s", msg)
        self.status_lbl.setText("⚠️ 요약 실패 (전사는 완료됨)")
        self.run_btn.setEnabled(True)
        QMessageBox.warning(self, "요약 오류",
                            f"전사 및 Notion 업로드는 완료됐지만 요약에 실패했습니다:\n\n{msg}")

    def _on_error(self, msg: str):
        log.error("처리 오류:\n%s", msg)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setVisible(False)
        self.status_lbl.setText("❌ 오류 발생")
        self.run_btn.setEnabled(True)
        QMessageBox.critical(self, "오류", f"처리 중 오류가 발생했습니다:\n\n{msg}")

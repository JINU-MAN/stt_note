import logging
import multiprocessing
import os
import sys
from pathlib import Path

# CTranslate2(faster-whisper)가 Qt 스레드 안에서 OpenMP를 쓸 때 충돌하는 문제 방지
# 반드시 다른 import보다 먼저 설정해야 함
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")

from PyQt6.QtWidgets import QApplication

from src.config import Config
from src.ui.main_window import MainWindow

# Log to %APPDATA%/STTNote/app.log
_log_dir = Path(os.environ.get("APPDATA", Path.home())) / "STTNote"
_log_dir.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler(_log_dir / "app.log", encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger(__name__)


def main():
    log.info("앱 시작")
    app = QApplication(sys.argv)
    app.setApplicationName("STT Note")
    app.setStyle("Fusion")

    config = Config()
    window = MainWindow(config)
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    # Windows에서 multiprocessing 서브프로세스가 재귀 실행되지 않도록 필수
    multiprocessing.freeze_support()
    try:
        main()
    except Exception:
        log.exception("앱 비정상 종료")
        raise

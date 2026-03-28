# -*- mode: python ; coding: utf-8 -*-
# main.py → STTNote.exe  (windowed GUI, onefile)

import os
_root = os.path.abspath(os.path.join(SPECPATH, '..'))

a = Analysis(
    [os.path.join(_root, 'main.py')],
    pathex=[_root],
    binaries=[],
    datas=[],
    hiddenimports=[
        'src.config',
        'src.formatter',
        'src.llm',
        'src.notion_api',
        'src.stt',
        'src.ui.main_window',
        'src.ui.settings_dialog',
        'PyQt6.QtCore',
        'PyQt6.QtGui',
        'PyQt6.QtWidgets',
        'huggingface_hub',
        'notion_client',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['faster_whisper', 'ctranslate2', 'llama_cpp'],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='STTNote',
    debug=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    icon=None,
)

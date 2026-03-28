# -*- mode: python ; coding: utf-8 -*-
# stt_script.py → stt_script.exe  (console subprocess, onefile)
# SPECPATH는 이 파일이 있는 build/ 디렉터리를 가리킴

import os
_root = os.path.abspath(os.path.join(SPECPATH, '..'))

a = Analysis(
    [os.path.join(_root, 'src', 'stt_script.py')],
    pathex=[_root],
    binaries=[],
    datas=[],
    hiddenimports=['faster_whisper', 'ctranslate2'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['PyQt6'],
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
    name='stt_script',
    debug=False,
    strip=False,
    upx=False,
    console=True,
    disable_windowed_traceback=False,
)

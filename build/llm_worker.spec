# -*- mode: python ; coding: utf-8 -*-
# llm_script.py → llm_script.exe  (console subprocess, onefile)

import os
_root = os.path.abspath(os.path.join(SPECPATH, '..'))

a = Analysis(
    [os.path.join(_root, 'src', 'llm_script.py')],
    pathex=[_root],
    binaries=[],
    datas=[],
    hiddenimports=['llama_cpp'],
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
    name='llm_script',
    debug=False,
    strip=False,
    upx=False,
    console=True,
    disable_windowed_traceback=False,
)

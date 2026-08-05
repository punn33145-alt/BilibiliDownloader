# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for Bilibili Video Downloader."""

import sys
from pathlib import Path

block_cipher = None
project_root = Path(SPECPATH)
app_dir = project_root / "app"

a = Analysis(
    [str(app_dir / "main.py")],
    pathex=[str(project_root)],
    binaries=[],
    datas=[
        (str(app_dir / "resources" / "icons"), "app/resources/icons"),
    ],
    hiddenimports=[
        "yt_dlp",
        "yt_dlp.extractor",
        "yt_dlp.postprocessor",
        "PIL",
        "requests",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="BilibiliVideoDownloader",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(app_dir / "resources" / "icons" / "app_icon.ico"),
)

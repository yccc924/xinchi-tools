# -*- mode: python ; coding: utf-8 -*-
#
# PyInstaller spec for 炘馳工具箱 (xinchi)
# Run from repo root:  pyinstaller xinchi.spec
#
# blog-generator/ and 價格檢查/ are NOT bundled into the exe;
# they ship as side-by-side folders next to xinchi.exe so that
# .env, output/, done.txt etc. can be edited/written at runtime.

from PyInstaller.utils.hooks import collect_all, collect_data_files
import sys

block_cipher = None

# ── collect google-genai (no built-in hook in older PyInstaller) ──────────────
_gg_datas, _gg_bins, _gg_hidden = collect_all('google.genai')
try:
    _ga_datas, _ga_bins, _ga_hidden = collect_all('google.auth')
except Exception:
    _ga_datas, _ga_bins, _ga_hidden = [], [], []
try:
    _gap_datas, _gap_bins, _gap_hidden = collect_all('google.api_core')
except Exception:
    _gap_datas, _gap_bins, _gap_hidden = [], [], []

# ── collect playwright ────────────────────────────────────────────────────────
try:
    _pw_datas, _pw_bins, _pw_hidden = collect_all('playwright')
except Exception:
    _pw_datas, _pw_bins, _pw_hidden = [], [], []

all_datas = (
    [('整合app/core/assets', 'core/assets')]   # fonts + template image for image_engine
    + _gg_datas + _ga_datas + _gap_datas
    + _pw_datas
)
all_binaries = _gg_bins + _ga_bins + _gap_bins + _pw_bins
all_hidden   = (
    _gg_hidden + _ga_hidden + _gap_hidden + _pw_hidden
    + [
        # blog-generator/main.py deps (dynamic sys.path import, not seen statically)
        'feedparser',
        'bs4', 'bs4.builder', 'bs4.formatter',
        'lxml', 'lxml.etree', 'lxml.html',
        'openai', 'openai.resources',
        'dotenv',
        # price_checker.py deps
        'pandas', 'pandas.core', 'pandas.io.excel',
        'openpyxl',
        'requests',
        # google-genai sub-packages
        'google.genai', 'google.genai.types',
        'google.generativeai',
    ]
)

a = Analysis(
    ['整合app/main.py'],
    pathex=['整合app'],          # makes 'import core.xxx' and 'import pages.xxx' work
    binaries=all_binaries,
    datas=all_datas,
    hiddenimports=all_hidden,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['customtkinter'],  # not actually used
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
    name='xinchi',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,              # no black console window (GUI app)
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)

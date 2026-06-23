# -*- mode: python ; coding: utf-8 -*-
import os

block_cipher = None

# Gói xfreerdp trong vendor/freerdp/ (tạo bởi install-linux.sh)
_freerdp_binaries = []
_freerdp_datas = []
_vendor = "vendor/freerdp"
if os.path.isdir(_vendor):
    _bin = os.path.join(_vendor, "bin")
    _lib = os.path.join(_vendor, "lib")
    if os.path.isdir(_bin):
        for name in os.listdir(_bin):
            src = os.path.join(_bin, name)
            if os.path.isfile(src):
                _freerdp_binaries.append((src, "bin"))
    if os.path.isdir(_lib):
        for name in os.listdir(_lib):
            src = os.path.join(_lib, name)
            if os.path.isfile(src):
                _freerdp_binaries.append((src, "lib"))

a = Analysis(
    ['main_gui.py'],
    pathex=[],
    binaries=_freerdp_binaries,
    datas=[('assets', 'assets')],
    hiddenimports=['freerdp_bootstrap'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='main_gui',
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
)

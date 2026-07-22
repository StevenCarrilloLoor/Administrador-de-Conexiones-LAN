# -*- mode: python ; coding: utf-8 -*-
"""Spec de PyInstaller para AdministradorLAN.

Genera un unico ejecutable onefile con FastAPI + dashboard + base OUI embebidos.

Dos variantes segun la variable de entorno ACL_BUILD_TEST:
  * (sin definir)  -> AdministradorLAN.exe      : windowed + requireAdministrator (entrega real)
  * ACL_BUILD_TEST -> AdministradorLAN-test.exe : consola + sin elevacion (para verificacion)
"""
import os
from PyInstaller.utils.hooks import collect_all, collect_submodules

TEST = bool(os.environ.get("ACL_BUILD_TEST"))

datas = [
    ("dashboard", "dashboard"),
    ("data/oui.csv", "data"),
    ("db/schema.sql", "db"),
]
binaries = []
hiddenimports = []

# Paquetes que cargan submodulos/datos dinamicamente
for pkg in ("uvicorn", "scapy", "apscheduler", "tzdata", "pystray", "fastapi", "starlette"):
    d, b, h = collect_all(pkg)
    datas += d
    binaries += b
    hiddenimports += h

hiddenimports += collect_submodules("uvicorn")
hiddenimports += [
    "anyio", "h11", "click", "websockets", "httptools", "pydantic",
    "pydantic_core", "PIL.Image", "PIL.ImageDraw",
]

a = Analysis(
    ["launcher.py"],
    pathex=["."],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib", "numpy", "pandas", "pytest"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name=("AdministradorLAN-test" if TEST else "AdministradorLAN"),
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    runtime_tmpdir=None,
    # Ambas variantes son windowed (console=False) para que la de prueba reproduzca
    # fielmente el path del .exe real (sys.stdout/stderr = None). La diferencia es solo
    # la elevacion: la de prueba NO pide UAC, para poder verificarla sin intervencion.
    console=False,
    disable_windowed_traceback=False,
    uac_admin=(not TEST),
    icon="build_assets/app.ico",
)

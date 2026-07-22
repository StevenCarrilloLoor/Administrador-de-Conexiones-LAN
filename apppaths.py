"""Resolucion de rutas consciente del empaquetado (PyInstaller / codigo fuente).

Distingue dos raices:
  * bundle_dir(): recursos de solo lectura empaquetados (dashboard/, data/oui.csv).
    - Congelado (PyInstaller onefile): sys._MEIPASS (carpeta temporal de extraccion).
    - Codigo fuente: la raiz del proyecto.
  * app_dir(): datos escribibles y persistentes (BD, logs, config.ini).
    - Congelado: la carpeta donde esta el .exe (persiste entre ejecuciones).
    - Codigo fuente: la raiz del proyecto.

Esto permite que el mismo codigo funcione ejecutado con `python main.py` y como
`AdministradorLAN.exe`, guardando la BD y los logs JUNTO al .exe (no en la carpeta
temporal que PyInstaller borra al salir).
"""
from __future__ import annotations

import sys
from pathlib import Path


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def bundle_dir() -> Path:
    """Carpeta con los recursos de solo lectura empaquetados."""
    if is_frozen():
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent))
    return Path(__file__).resolve().parent


def app_dir() -> Path:
    """Carpeta con los datos escribibles y persistentes."""
    if is_frozen():
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def resource_path(*rel: str) -> Path:
    return bundle_dir().joinpath(*rel)


def dashboard_dir() -> Path:
    return resource_path("dashboard")


def oui_csv_path() -> Path:
    return resource_path("data", "oui.csv")


def data_dir() -> Path:
    d = app_dir() / "data"
    d.mkdir(parents=True, exist_ok=True)
    return d


def db_path() -> Path:
    return data_dir() / "lanmanager.db"


def log_dir() -> Path:
    d = app_dir() / "logs"
    d.mkdir(parents=True, exist_ok=True)
    return d


def config_file() -> Path:
    return app_dir() / "config.ini"
